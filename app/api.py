"""JSON API behind the dashboard (design components C3 Insights API, C5 Retention Actions & Export,
plus the admin endpoints for ingestion, model training and scoring).

Every route is wrapped by `require(...)`; customer-level reads are audit-logged (REQ-14) and show
masked references only (REQ-15). Relationship managers only ever see their own customers.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime

import pandas as pd
from flask import Blueprint, Response, current_app, g, jsonify, request
from werkzeug.security import generate_password_hash

from . import db, ingest, ml, reports, scoring
from .advice import risk_tier, suggest_actions
from .auth import ROLES, audit, audit_many, require, scope_sql

bp = Blueprint("api", __name__, url_prefix="/api")

STAFF = ("rm", "retention_manager", "admin")
TIERS = ("Low", "Medium", "High")
ACTION_TYPES = ("Phone call", "Email", "Offer proposed", "Meeting", "Other")
SEGMENTS = {
    "products": ("COALESCE(CAST(c.products_number AS INTEGER), 'Unknown')", "Number of products"),
    "country": ("COALESCE(c.country, 'Unknown')", "Country"),
    "age": (
        (
            "CASE WHEN c.age IS NULL THEN 'Unknown' WHEN c.age < 30 THEN '18-29' WHEN c.age < 40 THEN '30-39' "
            "WHEN c.age < 50 THEN '40-49' WHEN c.age < 60 THEN '50-59' ELSE '60+' END"
        ),
        "Age band",
    ),
    "tenure": ("COALESCE(CAST(c.tenure AS INTEGER), 'Unknown')", "Years as a customer"),
}
BOUNDS = {  # sanity limits for the quick-predict form
    "credit_score": (0, 1000), "age": (0, 120), "tenure": (0, 80), "balance": (0, 1e9),
    "products_number": (1, 20), "estimated_salary": (0, 1e9), "credit_card": (0, 1), "active_member": (0, 1),
}


def _manager():
    return current_app.extensions["models"]


def _err(message: str, code: int = 400):
    return jsonify({"error": message}), code


def _model_or_409():
    model = _manager().model
    if model is None:
        return None, _err("No trained model yet. An administrator must train one first.", 409)
    return model, None


# ---------------------------------------------------------------- status
@bp.get("/status")
@require()
def status():
    conn, mgr = db.get_db(), _manager()
    scope, params = scope_sql(g.user)
    job = conn.execute("SELECT * FROM scoring_jobs WHERE status='done' ORDER BY id DESC LIMIT 1").fetchone()
    return jsonify({
        "model": {"ready": mgr.model is not None, "name": mgr.model.name if mgr.model else None,
                  "trained_at": mgr.model.trained_at if mgr.model else None},
        "customers": conn.execute(f"SELECT COUNT(*) FROM customers c WHERE {scope}", params).fetchone()[0],
        "last_run": dict(job) if job else None,
        "training": mgr.job,
        "features_ready": mgr.prepared is not None,
    })


# ------------------------------------------------------------- dashboard
@bp.get("/dashboard")
@require()
def dashboard():
    conn, mgr = db.get_db(), _manager()
    scope, params = scope_sql(g.user)
    seg_key = request.args.get("segment", "products")
    if seg_key not in SEGMENTS:
        return _err("Unknown segment.")
    threshold = float(db.get_setting(conn, "alert_threshold"))

    total, labeled, churned = conn.execute(
        f"SELECT COUNT(*), COUNT(c.churn), COALESCE(SUM(c.churn), 0) FROM customers c WHERE {scope}",
        params).fetchone()
    hist_rate = round(100 * churned / labeled, 1) if labeled else None

    job_id = scoring.latest_job_id(conn)
    tiers, high, delta = {t: 0 for t in TIERS}, None, None
    if job_id:
        for r in conn.execute(
                f"SELECT s.risk_tier, COUNT(*) AS n FROM scores s JOIN customers c ON c.id = s.customer_id "
                f"WHERE s.job_id = ? AND {scope} GROUP BY s.risk_tier", [job_id, *params]):
            tiers[r["risk_tier"]] = r["n"]
        count_high = (f"SELECT COUNT(*) FROM scores s JOIN customers c ON c.id = s.customer_id "
                      f"WHERE s.job_id = ? AND s.probability >= ? AND {scope}")
        high = conn.execute(count_high, [job_id, threshold, *params]).fetchone()[0]
        prev = conn.execute("SELECT id FROM scoring_jobs WHERE status='done' AND id < ? ORDER BY id DESC LIMIT 1",
                            (job_id,)).fetchone()
        if prev:
            before = conn.execute(count_high, [prev["id"], threshold, *params]).fetchone()[0]
            delta = high - before

    expr, seg_title = SEGMENTS[seg_key]
    rows = conn.execute(
        f"SELECT {expr} AS seg, COUNT(*) AS n, COUNT(c.churn) AS lab, COALESCE(SUM(c.churn), 0) AS ch "
        f"FROM customers c WHERE {scope} GROUP BY seg", params).fetchall()
    rows = sorted(rows, key=lambda r: (str(r["seg"]) == "Unknown",
                                       int(r["seg"]) if str(r["seg"]).isdigit() else str(r["seg"])))
    reasons = mgr.model.importance()[:6] if mgr.model else []
    last = conn.execute("SELECT finished_at, duration_s, trigger FROM scoring_jobs WHERE id = ?",
                        (job_id,)).fetchone() if job_id else None
    return jsonify({
        "kpis": {"total": total, "active": total - churned, "high_risk": high, "high_delta": delta,
                 "historical_churn_rate": hist_rate,
                 "retention_rate": round(100 - hist_rate, 1) if hist_rate is not None else None},
        "tiers": tiers, "threshold": threshold, "scored": bool(job_id),
        "segment": {"key": seg_key, "title": seg_title, "labels": [str(r["seg"]) for r in rows],
                    "customers": [r["n"] for r in rows],
                    "churn_rate": [round(100 * r["ch"] / r["lab"], 1) if r["lab"] else None for r in rows]},
        "reasons": reasons,
        "last_run": dict(last) if last else None,
        "model_ready": mgr.model is not None,
    })


# ---------------------------------------------------------- predictions
def _parse_customer(model, data: dict) -> dict:
    row = {}
    for col in model.input_columns:
        if col not in data:
            raise ValueError(f"Missing field: {col}")
        if col in ("country", "gender"):
            value = str(data[col]).strip()
            if not value:
                raise ValueError(f"Missing field: {col}")
            row[col] = value
        else:
            try:
                value = float(data[col])
            except (TypeError, ValueError):
                raise ValueError(f"{col.replace('_', ' ').capitalize()} must be a number.") from None
            lo, hi = BOUNDS.get(col, (float("-inf"), float("inf")))
            if not lo <= value <= hi:
                raise ValueError(f"{col.replace('_', ' ').capitalize()} must be between {lo:g} and {hi:g}.")
            row[col] = value
    return row


@bp.get("/schema")
@require()
def schema():
    model = _manager().model
    return jsonify({"columns": model.input_columns if model else ml.INPUT_COLUMNS})


@bp.post("/predict")
@require()
def predict_one():
    model, err = _model_or_409()
    if err:
        return err
    try:
        row = _parse_customer(model, request.get_json(silent=True) or {})
    except ValueError as exc:
        return _err(str(exc))
    raw = pd.DataFrame([row])
    prob = float(model.predict_proba(raw)[0] * 100)
    tier = risk_tier(prob)
    audit("predict_adhoc", detail=f"tier={tier}")
    return jsonify({"probability": round(prob, 1), "tier": tier, "factors": model.explain(raw)[0],
                    "actions": suggest_actions(tier, row), "model": model.name,
                    "threshold": float(db.get_setting(db.get_db(), "alert_threshold"))})


@bp.post("/predict/batch")
@require(*STAFF)
def predict_batch():
    model, err = _model_or_409()
    if err:
        return err
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".csv"):
        return _err("Choose a .csv file.")
    try:
        raw = ml.normalize_columns(pd.read_csv(f))
        missing = [c for c in model.input_columns if c not in raw.columns]
        if missing:
            return _err(f"Missing columns: {', '.join(missing)}")
        probs = model.predict_proba(raw[model.input_columns]) * 100
    except Exception as exc:  # noqa: BLE001 - report any failure to the user
        return _err(f"Could not score this file: {exc}")
    out = raw.copy()
    out["churn_probability"] = probs.round(1)
    out["risk_level"] = [risk_tier(p) for p in probs]
    out = out.sort_values("churn_probability", ascending=False)
    current_app.extensions.setdefault("last_batch", {})[g.user["id"]] = out
    audit("batch_score", detail=f"{len(out)} rows")
    shown = out.head(200).copy()
    for col in ("customer_id", "id", "client_id"):
        if col in shown.columns:
            shown[col] = shown[col].map(db.mask_ref)  # REQ-15: masked on screen, full in the download
    return jsonify({"count": len(out), "high_risk": int((out["churn_probability"] >= 60).sum()),
                    "columns": shown.columns.tolist(),
                    "rows": shown.astype(object).where(shown.notna(), None).to_dict(orient="records")})


@bp.get("/predict/batch/download")
@require(*STAFF)
def download_batch():
    out = current_app.extensions.get("last_batch", {}).get(g.user["id"])
    if out is None:
        return _err("No batch results yet.", 404)
    buf = io.StringIO()
    out.to_csv(buf, index=False)
    audit("download_batch", detail=f"{len(out)} rows")
    return Response(buf.getvalue(), mimetype="text/csv", headers={
        "Content-Disposition": f"attachment; filename=churn_scoring_{datetime.now(UTC):%Y%m%d_%H%M%S}.csv"})


# ------------------------------------------------------------ customers
def _customer_filters(args) -> tuple[str, list]:
    where, params = [], []
    if args.get("tier") in TIERS:
        where.append("s.risk_tier = ?")
        params.append(args["tier"])
    if args.get("products", "").isdigit():
        where.append("CAST(c.products_number AS INTEGER) = ?")
        params.append(int(args["products"]))
    if args.get("country"):
        where.append("c.country = ?")
        params.append(args["country"])
    return (" AND ".join(where) or "1 = 1"), params


@bp.get("/customers")
@require(*STAFF)
def customers():
    conn = db.get_db()
    job_id = scoring.latest_job_id(conn)
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("per_page", 25, type=int)))
    if not job_id:
        return jsonify({"items": [], "total": 0, "page": 1, "pages": 1, "scored": False})
    scope, sp = scope_sql(g.user)
    filt, fp = _customer_filters(request.args)
    base = (f"FROM scores s JOIN customers c ON c.id = s.customer_id "
            f"WHERE s.job_id = ? AND {scope} AND {filt}")
    args = [job_id, *sp, *fp]
    total = conn.execute(f"SELECT COUNT(*) {base}", args).fetchone()[0]
    rows = conn.execute(
        f"SELECT c.id, c.customer_ref, c.country, c.products_number, c.active_member, c.age, "
        f"s.probability, s.risk_tier, s.top_factors {base} ORDER BY s.probability DESC, c.id "
        f"LIMIT ? OFFSET ?", [*args, per_page, (page - 1) * per_page]).fetchall()
    audit_many("view_customer_list", [r["id"] for r in rows])
    items = []
    for r in rows:
        top = json.loads(r["top_factors"])[0] if r["top_factors"] else None
        items.append({"id": r["id"], "ref": db.mask_ref(r["customer_ref"]), "country": r["country"],
                      "products": r["products_number"], "active": r["active_member"],
                      "probability": r["probability"], "tier": r["risk_tier"],
                      "top_factor": f"{top['label']} ({top['value']})" if top else ""})
    return jsonify({"items": items, "total": total, "page": page, "scored": True,
                    "pages": max(1, -(-total // per_page))})


@bp.get("/customers/<int:cid>")
@require(*STAFF)
def customer_detail(cid: int):
    conn = db.get_db()
    scope, sp = scope_sql(g.user)
    job_id = scoring.latest_job_id(conn)
    row = conn.execute(
        f"SELECT c.*, s.probability, s.risk_tier, s.top_factors FROM customers c "
        f"LEFT JOIN scores s ON s.customer_id = c.id AND s.job_id = ? WHERE c.id = ? AND {scope}",
        [job_id or 0, cid, *sp]).fetchone()
    if not row:
        return _err("Customer not found.", 404)
    audit("view_customer", cid)
    history = [dict(r) for r in conn.execute(
        "SELECT a.id, a.type, a.notes, a.status, a.created_at, u.name AS by FROM retention_actions a "
        "JOIN users u ON u.id = a.user_id WHERE a.customer_id = ? ORDER BY a.id DESC", (cid,))]
    profile = {k: row[k] for k in ("country", "gender", "age", "tenure", "balance", "products_number",
                                   "credit_card", "active_member", "estimated_salary") if row[k] is not None}
    tier = row["risk_tier"]
    return jsonify({
        "id": cid, "ref": db.mask_ref(row["customer_ref"]), "profile": profile,
        "scored": row["probability"] is not None, "probability": row["probability"], "tier": tier,
        "factors": json.loads(row["top_factors"]) if row["top_factors"] else [],
        "actions": suggest_actions(tier, dict(row)) if tier else [],
        "history": history,
        "threshold": float(db.get_setting(conn, "alert_threshold")),
    })


# ------------------------------------------------------------ retention
def _visible_customer(conn, cid: int):
    scope, sp = scope_sql(g.user)
    return conn.execute(f"SELECT c.id FROM customers c WHERE c.id = ? AND {scope}", [cid, *sp]).fetchone()


@bp.get("/retention/actions")
@require(*STAFF)
def list_actions():
    scope, sp = scope_sql(g.user)
    rows = db.get_db().execute(
        f"SELECT a.id, a.customer_id, c.customer_ref, a.type, a.notes, a.status, a.created_at, u.name AS by "
        f"FROM retention_actions a JOIN customers c ON c.id = a.customer_id JOIN users u ON u.id = a.user_id "
        f"WHERE {scope} ORDER BY a.id DESC LIMIT 200", sp).fetchall()
    return jsonify({"items": [{**dict(r), "ref": db.mask_ref(r["customer_ref"]), "customer_ref": None}
                              for r in rows]})


@bp.post("/retention/actions")
@require(*STAFF)
def add_action():
    data = request.get_json(silent=True) or {}
    conn = db.get_db()
    cid = data.get("customer_id")
    if not isinstance(cid, int) or not _visible_customer(conn, cid):
        return _err("Customer not found.", 404)
    kind = data.get("type")
    if kind not in ACTION_TYPES:
        return _err("Choose an action type.")
    notes = str(data.get("notes", ""))[:500]
    # The action is only recorded. Nothing is sent to the customer (REQ-20).
    action_id = conn.execute(
        "INSERT INTO retention_actions(customer_id, user_id, type, notes, created_at) VALUES (?,?,?,?,?)",
        (cid, g.user["id"], kind, notes, db.now())).lastrowid
    conn.commit()
    audit("log_retention_action", cid, kind)
    return jsonify({"ok": True, "id": action_id}), 201


@bp.patch("/retention/actions/<int:action_id>")
@require(*STAFF)
def update_action(action_id: int):
    status = (request.get_json(silent=True) or {}).get("status")
    if status not in ("planned", "done"):
        return _err("Status must be planned or done.")
    conn = db.get_db()
    row = conn.execute("SELECT customer_id FROM retention_actions WHERE id = ?", (action_id,)).fetchone()
    if not row or not _visible_customer(conn, row["customer_id"]):
        return _err("Action not found.", 404)
    conn.execute("UPDATE retention_actions SET status = ? WHERE id = ?", (status, action_id))
    conn.commit()
    audit("update_retention_action", row["customer_id"], status)
    return jsonify({"ok": True})


# --------------------------------------------------------------- alerts
@bp.get("/alerts")
@require(*STAFF)
def list_alerts():
    where, params = ("a.rm_id = ?", [g.user["id"]]) if g.user["role"] == "rm" else ("1 = 1", [])
    if request.args.get("status") in ("new", "acknowledged"):
        where += " AND a.status = ?"
        params.append(request.args["status"])
    rows = db.get_db().execute(
        f"SELECT a.id, a.customer_id, c.customer_ref, a.probability, a.threshold, a.status, a.created_at, "
        f"u.name AS rm FROM alerts a JOIN customers c ON c.id = a.customer_id "
        f"LEFT JOIN users u ON u.id = a.rm_id WHERE {where} ORDER BY a.id DESC, a.probability DESC LIMIT 200",
        params).fetchall()
    return jsonify({"items": [{**dict(r), "ref": db.mask_ref(r["customer_ref"]), "customer_ref": None}
                              for r in rows]})


@bp.post("/alerts/<int:alert_id>/ack")
@require(*STAFF)
def ack_alert(alert_id: int):
    conn = db.get_db()
    row = conn.execute("SELECT rm_id, customer_id FROM alerts WHERE id = ?", (alert_id,)).fetchone()
    if not row or (g.user["role"] == "rm" and row["rm_id"] != g.user["id"]):
        return _err("Alert not found.", 404)
    conn.execute("UPDATE alerts SET status='acknowledged', acknowledged_at=? WHERE id=?", (db.now(), alert_id))
    conn.commit()
    audit("acknowledge_alert", row["customer_id"])
    return jsonify({"ok": True})


# --------------------------------------------------------------- export
@bp.get("/export/high-risk.csv")
@require("retention_manager", "admin")
def export_segment():
    """Hand-off file for the marketing campaign tool (REQ-09)."""
    conn = db.get_db()
    job_id = scoring.latest_job_id(conn)
    if not job_id:
        return _err("No scores yet. Run scoring first.", 409)
    args = request.args.to_dict()
    args.setdefault("tier", "High")
    filt, fp = _customer_filters(args)
    rows = conn.execute(
        f"SELECT c.id, c.customer_ref, c.country, c.products_number, s.probability, s.risk_tier, s.top_factors, "
        f"u.username AS rm FROM scores s JOIN customers c ON c.id = s.customer_id "
        f"LEFT JOIN users u ON u.id = c.assigned_rm WHERE s.job_id = ? AND {filt} "
        f"ORDER BY s.probability DESC", [job_id, *fp]).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["customer_id", "country", "products", "churn_probability_pct", "risk_tier",
                "main_factors", "relationship_manager"])
    for r in rows:
        factors = "; ".join(f["label"] for f in json.loads(r["top_factors"]))
        w.writerow([r["customer_ref"], r["country"], r["products_number"], r["probability"], r["risk_tier"],
                    factors, r["rm"] or ""])
    audit("export_segment", detail=f"{len(rows)} customers, filters={json.dumps(args)[:200]}")
    return Response(buf.getvalue(), mimetype="text/csv", headers={
        "Content-Disposition": f"attachment; filename=churn_segment_{datetime.now(UTC):%Y%m%d}.csv"})


# -------------------------------------------------------------- reports
@bp.get("/reports/monthly")
@require("retention_manager", "admin", "executive")
def monthly():
    month = request.args.get("month") or datetime.now(UTC).strftime("%Y-%m")
    try:
        report = reports.monthly_report(db.get_db(), month)
    except ValueError as exc:
        return _err(str(exc))
    return jsonify(report)


@bp.get("/reports/monthly.csv")
@require("retention_manager", "admin", "executive")
def monthly_csv():
    month = request.args.get("month") or datetime.now(UTC).strftime("%Y-%m")
    try:
        report = reports.monthly_report(db.get_db(), month)
    except ValueError as exc:
        return _err(str(exc))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["section", "metric", "value"])
    w.writerows(reports.report_rows(report))
    audit("download_monthly_report", detail=month)
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=churn_kpi_{month}.csv"})


# ---------------------------------------------------------------- model
@bp.get("/model")
@require()
def model_info():
    mgr = _manager()
    meta = mgr.model.meta if mgr.model else {}
    return jsonify({
        "job": mgr.job, "ready": mgr.model is not None,
        "best_model": mgr.model.name if mgr.model else None,
        "trained_at": meta.get("trained_at"), "labels": meta.get("labels", ml.MODEL_LABELS),
        "metrics": meta.get("metrics", {}), "params": meta.get("params", {}),
        "smote": meta.get("smote"), "train_rows": meta.get("train_rows"), "test_rows": meta.get("test_rows"),
        "importance": mgr.model.importance()[:10] if mgr.model else [],
    })


# --------------------------------------------------- data / training (admin)
@bp.post("/data/upload")
@require("admin")
def upload():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".csv"):
        return _err("Choose a .csv file.")
    try:
        result = ingest.ingest_dataframe(db.get_db(), pd.read_csv(f))
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:  # noqa: BLE001 - report any failure to the user
        return _err(f"Could not read the CSV: {exc}")
    audit("ingest_data", detail=f"{f.filename}: {result['rows']} rows")
    return jsonify({"ok": True, "source": f.filename, **result})


@bp.post("/data/sample")
@require("admin")
def sample():
    path = current_app.config["DATA_DIR"] / current_app.config["SAMPLE_FILE"]
    if not path.exists():
        return _err(f"Sample file not found. Put '{path.name}' in the data/ folder or upload a CSV.", 404)
    result = ingest.ingest_dataframe(db.get_db(), pd.read_csv(path))
    audit("ingest_data", detail=f"{path.name}: {result['rows']} rows")
    return jsonify({"ok": True, "source": path.name, **result})


@bp.get("/data/summary")
@require("admin")
def summary():
    conn = db.get_db()
    df = pd.read_sql("SELECT customer_ref, credit_score, country, gender, age, tenure, balance, products_number, "
                     "credit_card, active_member, estimated_salary, churn FROM customers", conn)
    if df.empty:
        return _err("No customer data loaded.", 409)
    df = df.dropna(axis=1, how="all")
    df["customer_ref"] = df["customer_ref"].map(db.mask_ref)
    numeric = df.select_dtypes("number").drop(columns=["churn"], errors="ignore")
    corr = numeric.corr().round(2)
    labeled = df["churn"].dropna() if "churn" in df.columns else pd.Series(dtype=float)
    return jsonify({
        "rows": len(df), "columns": int(df.shape[1]), "missing": int(df.isnull().sum().sum()),
        "churn_rate": float(labeled.mean()) if len(labeled) else None,
        "head": df.head(10).astype(object).where(df.head(10).notna(), None).to_dict(orient="records"),
        "column_info": [{"column": c, "type": str(df[c].dtype), "non_null": int(df[c].notnull().sum()),
                         "null": int(df[c].isnull().sum()), "unique": int(df[c].nunique())} for c in df.columns],
        "churn_counts": {"labels": ["Stayed", "Left"],
                         "values": [int((labeled == 0).sum()), int((labeled == 1).sum())]},
        "correlation": {"labels": corr.columns.tolist(), "matrix": corr.where(corr.notna(), None).values.tolist()},
    })


@bp.post("/features")
@require("admin")
def build_features():
    frame, _ids = ingest.load_model_frame(db.get_db(), "churn IS NOT NULL")
    if len(frame) < 100 or frame["churn"].nunique() < 2:
        return _err("Need at least 100 customers with a known churn outcome (both stayed and left).", 409)
    prepared = _manager().prepare(frame)
    return jsonify({"n_features": len(prepared["feature_names"]), "features": prepared["feature_names"],
                    "train_rows": len(prepared["y_train"]), "test_rows": len(prepared["y_test"])})


@bp.post("/train")
@require("admin")
def train():
    mgr = _manager()
    if mgr.prepared is None:
        return _err("Generate features first.", 409)
    if mgr.job["status"] == "running":
        return _err("Training is already running.", 409)
    body = request.get_json(silent=True) or {}
    keys = [k for k in body.get("models", ["lr", "lgbm"]) if k in ml.TRAINERS]
    if not keys:
        return _err("Select at least one model.")
    app = current_app._get_current_object()

    def rescore():  # a new model version is scored right away so the dashboard is never stale
        try:
            scoring.run_batch(app.config["DB_PATH"], mgr, trigger="after_training")
        except Exception as exc:  # noqa: BLE001 - report any failure to the user
            app.logger.warning("Scoring after training failed: %s", exc)

    mgr.start_training(keys, bool(body.get("smote", True)), on_done=rescore)
    audit("train_model", detail=",".join(keys))
    return jsonify({"ok": True})


# ---------------------------------------------------------------- admin
@bp.post("/admin/score")
@require("admin")
def run_scoring():
    try:
        result = scoring.run_batch(current_app.config["DB_PATH"], _manager(), trigger="manual")
    except RuntimeError as exc:
        return _err(str(exc), 409)
    audit("run_scoring", detail=f"{result['customers_scored']} customers")
    return jsonify(result)


@bp.get("/admin/jobs")
@require("admin")
def jobs():
    rows = db.get_db().execute("SELECT * FROM scoring_jobs ORDER BY id DESC LIMIT 20").fetchall()
    return jsonify({"items": [dict(r) for r in rows]})


@bp.get("/admin/settings")
@require("admin")
def get_settings():
    return jsonify({"alert_threshold": float(db.get_setting(db.get_db(), "alert_threshold"))})


@bp.post("/admin/settings")
@require("admin")
def save_settings():
    try:
        value = float((request.get_json(silent=True) or {}).get("alert_threshold"))
    except (TypeError, ValueError):
        return _err("Alert threshold must be a number.")
    if not 1 <= value <= 99:
        return _err("Alert threshold must be between 1 and 99.")
    db.set_setting(db.get_db(), "alert_threshold", f"{value:g}")
    audit("change_alert_threshold", detail=f"{value:g}")
    return jsonify({"ok": True, "alert_threshold": value})


@bp.get("/admin/users")
@require("admin")
def list_users():
    rows = db.get_db().execute("SELECT id, username, name, role, branch, active FROM users ORDER BY id").fetchall()
    return jsonify({"items": [dict(r) for r in rows], "roles": ROLES})


@bp.post("/admin/users")
@require("admin")
def create_user():
    d = request.get_json(silent=True) or {}
    username, name, role = str(d.get("username", "")).strip(), str(d.get("name", "")).strip(), d.get("role")
    password = str(d.get("password", ""))
    if not username or not name or role not in ROLES:
        return _err("Username, name and role are required.")
    if len(password) < 10:
        return _err("Password must have at least 10 characters.")
    branch = (str(d.get("branch", "")).strip().title() or None) if role == "rm" else None
    conn = db.get_db()
    try:
        uid = conn.execute(
            "INSERT INTO users(username, name, role, branch, password_hash) VALUES (?,?,?,?,?)",
            (username, name, role, branch, generate_password_hash(password))).lastrowid
    except Exception:  # noqa: BLE001 - report any failure to the user
        return _err("That username already exists.", 409)
    if role == "rm" and branch:  # take over this branch's unassigned customers
        conn.execute("UPDATE customers SET assigned_rm = ? WHERE branch = ? AND assigned_rm IS NULL", (uid, branch))
    conn.commit()
    audit("create_user", detail=f"{username} ({role})")
    return jsonify({"ok": True, "id": uid}), 201


@bp.post("/admin/users/<int:uid>/active")
@require("admin")
def set_user_active(uid: int):
    if uid == g.user["id"]:
        return _err("You cannot deactivate your own account.")
    active = 1 if (request.get_json(silent=True) or {}).get("active") else 0
    conn = db.get_db()
    if not conn.execute("UPDATE users SET active = ? WHERE id = ?", (active, uid)).rowcount:
        return _err("User not found.", 404)
    conn.commit()
    audit("set_user_active", detail=f"user {uid} -> {active}")
    return jsonify({"ok": True})


@bp.get("/admin/audit")
@require("admin")
def audit_log():
    where, params = ["1 = 1"], []
    if request.args.get("action"):
        where.append("l.action = ?")
        params.append(request.args["action"])
    limit = min(500, request.args.get("limit", 100, type=int))
    rows = db.get_db().execute(
        f"SELECT l.id, l.ts, l.username, l.role, l.action, l.customer_id, l.detail, c.customer_ref "
        f"FROM audit_log l LEFT JOIN customers c ON c.id = l.customer_id WHERE {' AND '.join(where)} "
        f"ORDER BY l.id DESC LIMIT ?", [*params, limit]).fetchall()
    return jsonify({"items": [{
        "id": r["id"], "ts": r["ts"], "user": r["username"], "role": r["role"], "action": r["action"],
        "customer": db.mask_ref(r["customer_ref"]) if r["customer_ref"] else None, "detail": r["detail"]}
        for r in rows]})
