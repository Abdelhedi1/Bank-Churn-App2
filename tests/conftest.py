"""Shared fixtures. All data here is SYNTHETIC test data, not the bank's customers."""
import time

import numpy as np
import pandas as pd
import pytest

from app import create_app, db, ingest, scoring

PASSWORD = "churn-demo-2026"


def make_df(n=900, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "customer_id": 10_000_000 + np.arange(n),
        "credit_score": rng.integers(350, 850, n),
        "country": rng.choice(["France", "Spain", "Germany"], n),
        "gender": rng.choice(["Male", "Female"], n),
        "age": rng.integers(18, 80, n),
        "tenure": rng.integers(0, 11, n),
        "balance": rng.choice([0.0, 50000.0, 120000.0], n),
        "products_number": rng.integers(1, 4, n),
        "credit_card": rng.integers(0, 2, n),
        "active_member": rng.integers(0, 2, n),
        "estimated_salary": rng.uniform(10000, 200000, n).round(2),
    })
    logit = 0.05 * (df["age"] - 45) - 1.2 * df["active_member"] - 0.8
    df["churn"] = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    return df


@pytest.fixture
def df():
    return make_df()


def client_for(app, username):
    """Test client signed in as a demo user, with its CSRF header in `.h`."""
    c = app.test_client()
    with c.session_transaction() as s:
        s["csrf"] = "tok"
    r = c.post("/login", data={"username": username, "password": PASSWORD, "csrf_token": "tok"})
    assert r.status_code == 302, "login failed"
    with c.session_transaction() as s:
        c.h = {"X-CSRF-Token": s["csrf"]}
    return c


@pytest.fixture
def fresh_app(tmp_path):
    return create_app({"TESTING": True, "DB_PATH": tmp_path / "t.db", "MODELS_DIR": tmp_path / "models",
                       "DATA_DIR": tmp_path})


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    """An app with synthetic customers loaded, a small model trained and one scoring run done."""
    tmp = tmp_path_factory.mktemp("churn")
    app = create_app({"TESTING": True, "DB_PATH": tmp / "t.db", "MODELS_DIR": tmp / "models", "DATA_DIR": tmp})
    conn = db.connect(app.config["DB_PATH"])
    ingest.ingest_dataframe(conn, make_df())
    frame, _ = ingest.load_model_frame(conn, "churn IS NOT NULL")
    conn.close()
    mgr = app.extensions["models"]
    mgr.prepare(frame)
    mgr.start_training(["lr"], True)
    for _ in range(240):
        if mgr.job["status"] != "running":
            break
        time.sleep(0.5)
    assert mgr.job["status"] == "done", mgr.job
    scoring.run_batch(app.config["DB_PATH"], mgr)
    return app
