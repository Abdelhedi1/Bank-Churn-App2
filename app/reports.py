"""Monthly churn KPI report for management (REQ-08)."""
from __future__ import annotations

import re

from . import db

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def monthly_report(conn, month: str) -> dict:
    if not MONTH_RE.match(month):
        raise ValueError("Month must look like 2026-10.")
    like = f"{month}%"
    month_end = f"{month}-31 23:59:59"  # string compare is safe for every month length
    threshold = float(db.get_setting(conn, "alert_threshold"))

    job = conn.execute(
        "SELECT * FROM scoring_jobs WHERE status='done' AND finished_at <= ? ORDER BY id DESC LIMIT 1",
        (month_end,)).fetchone()
    snapshot = None
    if job:
        tiers = {r["risk_tier"]: r["n"] for r in conn.execute(
            "SELECT risk_tier, COUNT(*) AS n FROM scores WHERE job_id=? GROUP BY risk_tier", (job["id"],))}
        stats = conn.execute(
            "SELECT COUNT(*) AS n, AVG(probability) AS avg_p, "
            "SUM(CASE WHEN probability >= ? THEN 1 ELSE 0 END) AS high FROM scores WHERE job_id=?",
            (threshold, job["id"])).fetchone()
        if stats["n"]:  # scores of old runs are pruned; fall back to the run's own summary
            snapshot = {"scored": stats["n"], "high_risk": stats["high"] or 0,
                        "average_probability": round(stats["avg_p"] or 0, 1),
                        "tiers": {t: tiers.get(t, 0) for t in ("Low", "Medium", "High")}}
        else:
            snapshot = {"scored": job["customers_scored"], "high_risk": job["high_risk_count"],
                        "average_probability": None, "tiers": None}
        snapshot["run_finished_at"] = job["finished_at"]
        snapshot["model"] = job["model_name"]

    one = lambda sql, *a: conn.execute(sql, a).fetchone()[0]
    activity = {
        "scoring_runs": one("SELECT COUNT(*) FROM scoring_jobs WHERE status='done' AND finished_at LIKE ?", like),
        "alerts_created": one("SELECT COUNT(*) FROM alerts WHERE created_at LIKE ?", like),
        "alerts_acknowledged": one("SELECT COUNT(*) FROM alerts WHERE acknowledged_at LIKE ?", like),
        "retention_actions_logged": one("SELECT COUNT(*) FROM retention_actions WHERE created_at LIKE ?", like),
        "retention_actions_done": one(
            "SELECT COUNT(*) FROM retention_actions WHERE status='done' AND created_at LIKE ?", like),
    }
    by_type = {r["type"]: r["n"] for r in conn.execute(
        "SELECT type, COUNT(*) AS n FROM retention_actions WHERE created_at LIKE ? GROUP BY type", (like,))}

    labeled, churned = conn.execute(
        "SELECT COUNT(churn), COALESCE(SUM(churn), 0) FROM customers").fetchone()
    segments = [{"products": int(r["p"]), "customers": r["n"],
                 "churn_rate": round(100 * r["ch"] / r["lab"], 1) if r["lab"] else None}
                for r in conn.execute(
        "SELECT CAST(products_number AS INTEGER) AS p, COUNT(*) AS n, COUNT(churn) AS lab, "
        "COALESCE(SUM(churn), 0) AS ch FROM customers WHERE products_number IS NOT NULL GROUP BY p ORDER BY p")]
    return {
        "month": month, "generated_at": db.now(), "alert_threshold": threshold,
        "snapshot": snapshot, "activity": activity, "actions_by_type": by_type,
        "historical_churn_rate": round(100 * churned / labeled, 1) if labeled else None,
        "customers_total": one("SELECT COUNT(*) FROM customers"),
        "churn_by_products": segments,
    }


def report_rows(report: dict) -> list[tuple[str, str, object]]:
    """Flatten a report into (section, metric, value) rows for CSV export."""
    rows = [("report", "month", report["month"]), ("report", "generated_at", report["generated_at"]),
            ("portfolio", "customers_total", report["customers_total"]),
            ("portfolio", "historical_churn_rate_pct", report["historical_churn_rate"]),
            ("portfolio", "alert_threshold_pct", report["alert_threshold"])]
    snap = report["snapshot"]
    if snap:
        rows += [("scoring", "customers_scored", snap["scored"]), ("scoring", "high_risk", snap["high_risk"]),
                 ("scoring", "average_probability_pct", snap["average_probability"]),
                 ("scoring", "model", snap["model"])]
        for tier, n in (snap["tiers"] or {}).items():
            rows.append(("risk_tier", tier, n))
    rows += [("activity", k, v) for k, v in report["activity"].items()]
    rows += [("retention_action_type", k, v) for k, v in report["actions_by_type"].items()]
    rows += [("churn_by_products", f"{s['products']} product(s)", s["churn_rate"]) for s in report["churn_by_products"]]
    return rows
