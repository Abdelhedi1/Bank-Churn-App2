"""HTTP layer: HTML pages + JSON API. State is in memory (single-user demo app)."""
from __future__ import annotations

import io
import threading
from datetime import datetime

import numpy as np
import pandas as pd
from flask import Blueprint, Response, current_app, jsonify, render_template, request

from . import ml

bp = Blueprint("main", __name__)
LOCK = threading.Lock()

STATE: dict = {}


def _fresh_state() -> dict:
    return {
        "df": None, "source": None,
        "prepared": None,
        "best": None,            # {"model", "scaler", "feature_names", "model_name"}
        "metrics": {},           # key -> metrics dict
        "params": {},
        "job": {"status": "idle", "message": "", "error": None},
        "last_batch": None,
    }


def init_state(app) -> None:
    STATE.clear()
    STATE.update(_fresh_state())
    saved = ml.load_artifacts(app.config["MODELS_DIR"])
    if saved:  # a previously trained model can serve predictions right away
        STATE["best"] = saved


def _err(message: str, code: int = 400):
    return jsonify({"error": message}), code


# ----------------------------------------------------------------- pages
@bp.route("/")
def home():
    return render_template("index.html", page="home")


@bp.route("/data")
def data_page():
    return render_template("data.html", page="data")


@bp.route("/features")
def features_page():
    return render_template("features.html", page="features")


@bp.route("/training")
def training_page():
    return render_template("training.html", page="training")


@bp.route("/prediction")
def prediction_page():
    return render_template("prediction.html", page="prediction")


# ------------------------------------------------------------------- API
@bp.get("/api/status")
def status():
    df = STATE["df"]
    return jsonify({
        "data_loaded": df is not None,
        "rows": None if df is None else int(len(df)),
        "source": STATE["source"],
        "features_ready": STATE["prepared"] is not None,
        "model_ready": STATE["best"] is not None,
        "best_model": STATE["best"]["model_name"] if STATE["best"] else None,
        "job": STATE["job"],
    })


def _set_dataframe(df: pd.DataFrame, source: str):
    if "churn" not in df.columns:
        return _err("No target column found (expected 'churn' or 'exited').")
    missing = ml.missing_columns(df)
    if missing:
        return _err(f"Missing required columns: {', '.join(missing)}")
    with LOCK:
        STATE.update(_fresh_state() | {"df": df, "source": source, "best": STATE["best"]})
    return jsonify({"ok": True, "rows": int(len(df)), "source": source})


@bp.post("/api/data/upload")
def upload():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".csv"):
        return _err("Please upload a .csv file.")
    try:
        df = ml.load_csv(f)
    except Exception as exc:  # unreadable / malformed CSV
        return _err(f"Could not read CSV: {exc}")
    return _set_dataframe(df, f.filename)


@bp.post("/api/data/sample")
def sample():
    path = current_app.config["DATA_DIR"] / current_app.config["SAMPLE_FILE"]
    if not path.exists():
        return _err(f"Sample file not found. Put '{path.name}' in the data/ folder or upload a CSV.", 404)
    return _set_dataframe(ml.load_csv(path), path.name)


@bp.get("/api/data/summary")
def summary():
    df = STATE["df"]
    if df is None:
        return _err("No data loaded.", 409)
    numeric = df.select_dtypes(include=[np.number]).drop(columns=["churn"], errors="ignore")
    corr = numeric.corr().round(2)
    counts = df["churn"].value_counts().sort_index()
    return jsonify({
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "missing": int(df.isnull().sum().sum()),
        "churn_rate": float(df["churn"].mean()),
        "head": df.head(10).replace({np.nan: None}).to_dict(orient="records"),
        "column_info": [
            {"column": c, "type": str(df[c].dtype), "non_null": int(df[c].notnull().sum()),
             "null": int(df[c].isnull().sum()), "unique": int(df[c].nunique())}
            for c in df.columns
        ],
        "churn_counts": {"labels": ["No churn", "Churn"], "values": [int(counts.get(0, 0)), int(counts.get(1, 0))]},
        "correlation": {"labels": corr.columns.tolist(), "matrix": corr.values.tolist()},
    })


@bp.post("/api/features")
def build_features():
    df = STATE["df"]
    if df is None:
        return _err("Load data first.", 409)
    prepared = ml.prepare_training_data(df)
    with LOCK:
        STATE["prepared"] = prepared
    return jsonify({
        "n_features": len(prepared["feature_names"]),
        "features": prepared["feature_names"],
        "train_rows": int(len(prepared["y_train"])),
        "test_rows": int(len(prepared["y_test"])),
    })


def _train_job(app, keys: list[str], use_smote: bool) -> None:
    try:
        prep = STATE["prepared"]
        results = {}
        for i, key in enumerate(keys):
            STATE["job"]["message"] = f"Training {ml.MODEL_LABELS[key]} ({i + 1}/{len(keys)})…"
            model, params = ml.TRAINERS[key](prep["X_train"], prep["y_train"], use_smote)
            results[key] = (model, params, ml.evaluate_model(model, prep["X_test"], prep["y_test"]))
        best_key = max(results, key=lambda k: results[k][2]["auc"])
        best = {
            "model": results[best_key][0], "scaler": prep["scaler"],
            "feature_names": prep["feature_names"], "model_name": ml.MODEL_LABELS[best_key],
        }
        with LOCK:
            STATE["metrics"] = {k: v[2] for k, v in results.items()}
            STATE["params"] = {k: v[1] for k, v in results.items()}
            STATE["best"] = best
        ml.save_artifacts(app.config["MODELS_DIR"], best["model"], best["scaler"],
                          best["feature_names"], best["model_name"])
        STATE["job"] = {"status": "done", "message": f"Best model: {best['model_name']}", "error": None}
    except Exception as exc:
        STATE["job"] = {"status": "error", "message": "", "error": str(exc)}


@bp.post("/api/train")
def train():
    if STATE["prepared"] is None:
        return _err("Generate features first.", 409)
    if STATE["job"]["status"] == "running":
        return _err("Training already running.", 409)
    body = request.get_json(silent=True) or {}
    keys = [k for k in body.get("models", ["lr", "lgbm"]) if k in ml.TRAINERS]
    if not keys:
        return _err("Select at least one model.")
    STATE["job"] = {"status": "running", "message": "Starting…", "error": None}
    threading.Thread(
        target=_train_job, args=(current_app._get_current_object(), keys, bool(body.get("smote", True))),
        daemon=True,
    ).start()
    return jsonify({"ok": True})


@bp.get("/api/train/results")
def train_results():
    return jsonify({
        "job": STATE["job"],
        "labels": ml.MODEL_LABELS,
        "metrics": STATE["metrics"],
        "params": STATE["params"],
        "best_model": STATE["best"]["model_name"] if STATE["best"] else None,
    })


@bp.post("/api/predict")
def predict_one():
    best = STATE["best"]
    if not best:
        return _err("Train a model first.", 409)
    d = request.get_json(silent=True) or {}
    try:
        row = {
            "credit_score": float(d["credit_score"]), "age": float(d["age"]),
            "gender": str(d["gender"]), "country": str(d["country"]),
            "tenure": float(d["tenure"]), "balance": float(d["balance"]),
            "products_number": float(d["products_number"]),
            "credit_card": int(d["credit_card"]), "active_member": int(d["active_member"]),
            "estimated_salary": float(d["estimated_salary"]),
        }
    except (KeyError, TypeError, ValueError) as exc:
        return _err(f"Invalid or missing field: {exc}")
    out = ml.predict_frame(best["model"], best["scaler"], best["feature_names"], pd.DataFrame([row])).iloc[0]
    return jsonify({
        "probability": float(out["churn_probability"]),
        "prediction": int(out["prediction"]),
        "risk_level": out["risk_level"],
        "model": best["model_name"],
    })


@bp.post("/api/predict/batch")
def predict_batch():
    best = STATE["best"]
    if not best:
        return _err("Train a model first.", 409)
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".csv"):
        return _err("Please upload a .csv file.")
    try:
        raw = ml.normalize_columns(pd.read_csv(f))
        missing = ml.missing_columns(raw)
        if missing:
            return _err(f"Missing required columns: {', '.join(missing)}")
        out = ml.predict_frame(best["model"], best["scaler"], best["feature_names"], raw)
    except Exception as exc:
        return _err(f"Scoring failed: {exc}")
    out = out.sort_values("churn_probability", ascending=False)
    STATE["last_batch"] = out
    return jsonify({
        "count": int(len(out)),
        "high_risk": int((out["risk_level"] == "High").sum()),
        "columns": out.columns.tolist(),
        "rows": out.head(200).replace({np.nan: None}).to_dict(orient="records"),
    })


@bp.get("/api/predict/batch/download")
def download_batch():
    out = STATE["last_batch"]
    if out is None:
        return _err("No batch results yet.", 404)
    buf = io.StringIO()
    out.to_csv(buf, index=False)
    name = f"churn_scoring_{datetime.now():%Y%m%d_%H%M%S}.csv"
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={name}"})
