"""Scoring Engine & Scheduler (design component C7) and Alert Service (C4).

UC-1 of the design: a batch run scores every active customer, stores the scores
and publishes `scores ready`; the Alert Service subscribes and notifies the
assigned relationship managers (design pattern: Observer, REQ-02/03).
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from . import db, ingest
from .advice import risk_tier

SCHEDULE_DAYS = 7          # REQ-02: weekly batch
KEEP_SCORED_JOBS = 4       # older scores are pruned to keep the database small
_run_lock = threading.Lock()
SUBSCRIBERS: list = []     # Observer: callables(conn, job_id)


def subscribe(fn) -> None:
    if fn not in SUBSCRIBERS:
        SUBSCRIBERS.append(fn)


# ---------------------------------------------------------------- alerts
def notify_relationship_managers(conn, job_id: int) -> int:
    """Create an in-app alert for each customer above the threshold (REQ-03).

    Delivery is in-app only; an e-mail channel is not connected in this version.
    """
    threshold = float(db.get_setting(conn, "alert_threshold"))
    cur = conn.execute(
        "INSERT INTO alerts(job_id, customer_id, rm_id, probability, threshold, created_at) "
        "SELECT s.job_id, s.customer_id, c.assigned_rm, s.probability, ?, ? "
        "FROM scores s JOIN customers c ON c.id = s.customer_id "
        "WHERE s.job_id = ? AND s.probability >= ?",
        (threshold, db.now(), job_id, threshold))
    conn.commit()
    return cur.rowcount


subscribe(notify_relationship_managers)


# ----------------------------------------------------------------- batch
def run_batch(db_path, manager, trigger: str = "manual") -> dict:
    """Score all active customers (churn not yet recorded). Returns the job summary."""
    if not _run_lock.acquire(blocking=False):
        raise RuntimeError("A scoring run is already in progress.")
    conn = db.connect(db_path)
    job_id = conn.execute(
        "INSERT INTO scoring_jobs(started_at, status, trigger, model_name) VALUES (?, 'running', ?, ?)",
        (db.now(), trigger, manager.model.name if manager.model else None)).lastrowid
    conn.commit()
    started = time.perf_counter()
    try:
        model = manager.model
        if model is None:
            raise RuntimeError("No trained model yet. Train one on the Data & Upload page.")
        frame, ids = ingest.load_model_frame(conn, "churn IS NULL OR churn = 0")
        if frame.empty:
            raise RuntimeError("No active customers to score. Load customer data first.")
        missing = [c for c in model.input_columns if c not in frame.columns]
        if missing:
            raise RuntimeError(f"Customer data lacks columns the model needs: {', '.join(missing)}")
        raw = frame[model.input_columns]
        probs = model.predict_proba(raw) * 100
        factors = model.explain(raw, top_n=3)
        ts = db.now()
        conn.executemany(
            "INSERT INTO scores(job_id, customer_id, probability, risk_tier, top_factors, computed_at) "
            "VALUES (?,?,?,?,?,?)",
            [(job_id, int(cid), round(float(p), 2), risk_tier(p), json.dumps(f), ts)
             for cid, p, f in zip(ids, probs, factors)])
        threshold = float(db.get_setting(conn, "alert_threshold"))
        high = int((probs >= threshold).sum())
        duration = round(time.perf_counter() - started, 2)
        conn.execute(
            "UPDATE scoring_jobs SET status='done', finished_at=?, customers_scored=?, "
            "high_risk_count=?, duration_s=?, model_name=? WHERE id=?",
            (db.now(), len(probs), high, duration, model.name, job_id))
        conn.commit()
        for fn in SUBSCRIBERS:
            fn(conn, job_id)
        conn.execute(
            "DELETE FROM scores WHERE job_id <= (SELECT MAX(id) FROM scoring_jobs WHERE status='done') - ?",
            (KEEP_SCORED_JOBS,))
        conn.commit()
        return {"job_id": job_id, "customers_scored": len(probs), "high_risk": high, "duration_s": duration}
    except Exception as exc:
        conn.execute("UPDATE scoring_jobs SET status='failed', finished_at=?, error=? WHERE id=?",
                     (db.now(), str(exc)[:500], job_id))
        conn.commit()
        raise
    finally:
        conn.close()
        _run_lock.release()


def latest_job_id(conn) -> int | None:
    row = conn.execute("SELECT MAX(id) AS id FROM scoring_jobs WHERE status = 'done'").fetchone()
    return row["id"]


# ------------------------------------------------------------- scheduler
def is_due(conn, now: datetime | None = None) -> bool:
    """True when no successful run exists or the last one is older than a week."""
    now = now or datetime.now(timezone.utc)
    row = conn.execute("SELECT MAX(finished_at) AS t FROM scoring_jobs WHERE status = 'done'").fetchone()
    if not row["t"]:
        return True
    last = datetime.strptime(row["t"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return now - last >= timedelta(days=SCHEDULE_DAYS)


_scheduler_started = False


def start_scheduler(app, check_every_s: int = 3600) -> None:
    """Background thread that runs the weekly batch when it is due (REQ-02)."""
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    def loop():
        while True:
            time.sleep(check_every_s)
            try:
                conn = db.connect(app.config["DB_PATH"])
                due = is_due(conn)
                has_customers = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] > 0
                conn.close()
                manager = app.extensions["models"]
                if due and has_customers and manager.model is not None:
                    run_batch(app.config["DB_PATH"], manager, trigger="scheduled")
            except Exception as exc:  # keep the scheduler alive; the failed job row records the reason
                app.logger.warning("Scheduled scoring failed: %s", exc)

    threading.Thread(target=loop, daemon=True, name="weekly-scoring").start()
