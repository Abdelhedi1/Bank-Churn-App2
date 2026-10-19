"""Shared fixtures. The dataset here is SYNTHETIC test data only — not the bank's real data."""
import io

import numpy as np
import pandas as pd
import pytest

from app import create_app


def make_df(n=600, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "customer_id": np.arange(n),
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
    logit = 0.04 * (df["age"] - 45) - 1.2 * df["active_member"] - 1.0
    df["churn"] = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    return df


@pytest.fixture
def df():
    return make_df()


@pytest.fixture
def csv_bytes(df):
    return df.to_csv(index=False).encode()


@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DATA_DIR": tmp_path, "MODELS_DIR": tmp_path / "models"})
    return app.test_client()
