"""Machine-learning core: data cleaning, feature engineering, training, prediction.

Pure functions (no Flask) so they can be unit-tested and reused. Ported from the
original Streamlit prototype, with its bugs fixed (missing imports, undefined
`y` in evaluate_model, swapped roc_auc_score arguments, shadowed function names).
"""
from __future__ import annotations

import warnings
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import GridSearchCV, StratifiedKFold, train_test_split
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

COUNTRIES = ["France", "Germany", "Spain"]
BASE_COLUMNS = [
    "credit_score", "age", "tenure", "balance", "products_number",
    "credit_card", "active_member", "estimated_salary",
]
ID_COLUMNS = ["customer_id", "id", "client_id"]


# ----------------------------------------------------------------- data
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def detect_target(df: pd.DataFrame) -> str | None:
    for name in ("churn", "exited", "target"):
        if name in df.columns:
            return name
    for c in df.columns:
        vals = df[c].dropna().unique()
        if len(vals) == 2 and set(vals).issubset({0, 1}) and 0.05 < df[c].mean() < 0.5:
            return c
    return None


def load_csv(source) -> pd.DataFrame:
    """Read a CSV (path or file-like), lowercase columns, rename target to 'churn'."""
    df = normalize_columns(pd.read_csv(source))
    target = detect_target(df)
    if target and target != "churn":
        df = df.rename(columns={target: "churn"})
    return df


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ID_COLUMNS:
        if c in df.columns:
            df = df.drop(columns=c)
            break
    for c in df.select_dtypes(include=[np.number]).columns:
        if df[c].isnull().any():
            df[c] = df[c].fillna(df[c].median())
    for c in df.select_dtypes(include=["object", "string"]).columns:
        if df[c].isnull().any():
            df[c] = df[c].fillna(df[c].mode()[0])
    return df


def missing_columns(df: pd.DataFrame) -> list[str]:
    needed = BASE_COLUMNS + ["gender", "country"]
    return [c for c in needed if c not in df.columns]


# ------------------------------------------------------------- features
def create_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["balance_salary_ratio"] = df["balance"] / (df["estimated_salary"] + 1)
    df["activity_score"] = df["products_number"] * df["active_member"]
    df["tenure_risk"] = 1 / (df["tenure"] + 1)
    df["age_risk"] = np.where((df["age"] < 30) | (df["age"] > 60), 1, 0)
    df["low_balance"] = np.where(df["balance"] < 1000, 1, 0)
    df["high_value"] = np.where((df["balance"] > 100000) & (df["products_number"] >= 2), 1, 0)
    df["credit_active"] = df["credit_card"] * df["active_member"]
    return df


def encode_features(df: pd.DataFrame) -> pd.DataFrame:
    """Gender -> 0/1, country -> one-hot with a fixed column set (train == serve)."""
    df = df.copy()
    df["gender_encoded"] = (df["gender"].astype(str).str.strip().str.lower() == "male").astype(int)
    df = df.drop(columns="gender")
    country = df["country"].astype(str).str.strip().str.title()
    for c in COUNTRIES:
        df[f"country_{c}"] = (country == c).astype(int)
    return df.drop(columns="country")


def build_matrix(df: pd.DataFrame, feature_names: list[str] | None = None) -> pd.DataFrame:
    """Raw frame -> numeric feature matrix, aligned to feature_names when given."""
    X = encode_features(create_features(clean_data(df)))
    X = X.drop(columns=["churn"], errors="ignore")
    if feature_names is not None:
        X = X.reindex(columns=feature_names, fill_value=0)
    return X


def prepare_training_data(df: pd.DataFrame, test_size: float = 0.2, seed: int = 42) -> dict:
    X = build_matrix(df)
    y = pd.to_numeric(clean_data(df)["churn"], errors="coerce").fillna(0).astype(int)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=test_size, random_state=seed, stratify=y)
    scaler = StandardScaler()
    return {
        "X_train": scaler.fit_transform(X_tr),
        "X_test": scaler.transform(X_te),
        "y_train": y_tr.to_numpy(),
        "y_test": y_te.to_numpy(),
        "scaler": scaler,
        "feature_names": list(X.columns),
    }


# ------------------------------------------------------------- training
def compute_ks(y_true, y_prob) -> float:
    y_true, y_prob = np.asarray(y_true), np.asarray(y_prob)
    pos, neg = np.sort(y_prob[y_true == 1]), np.sort(y_prob[y_true == 0])
    if len(pos) == 0 or len(neg) == 0:
        return 0.0
    grid = np.unique(y_prob)
    cdf_pos = np.searchsorted(pos, grid, side="right") / len(pos)
    cdf_neg = np.searchsorted(neg, grid, side="right") / len(neg)
    return float(np.max(np.abs(cdf_pos - cdf_neg)))


def evaluate_model(model, X_te, y_te) -> dict:
    y_pred = model.predict(X_te)
    y_prob = model.predict_proba(X_te)[:, 1]
    fpr, tpr, _ = roc_curve(y_te, y_prob)
    step = max(1, len(fpr) // 200)  # keep the JSON small
    return {
        "accuracy": float(accuracy_score(y_te, y_pred)),
        "precision": float(precision_score(y_te, y_pred, zero_division=0)),
        "recall": float(recall_score(y_te, y_pred, zero_division=0)),
        "f1": float(f1_score(y_te, y_pred, zero_division=0)),
        "auc": float(roc_auc_score(y_te, y_prob)),
        "ks": compute_ks(y_te, y_prob),
        "confusion_matrix": confusion_matrix(y_te, y_pred).tolist(),
        "roc": {"fpr": fpr[::step].tolist(), "tpr": tpr[::step].tolist()},
    }


def _fit_grid(estimator, grid, X, y, use_smote, seed):
    if use_smote:
        X, y = SMOTE(random_state=seed).fit_resample(X, y)
    cv = StratifiedKFold(5, shuffle=True, random_state=seed)
    gs = GridSearchCV(estimator, grid, cv=cv, scoring="roc_auc", n_jobs=-1)
    gs.fit(X, y)
    return gs.best_estimator_, gs.best_params_


def train_logistic_regression(X, y, use_smote=True, seed=42):
    return _fit_grid(
        LogisticRegression(random_state=seed, max_iter=1000),
        {"C": [0.01, 0.1, 1, 10]}, X, y, use_smote, seed,
    )


def train_lightgbm(X, y, use_smote=True, seed=42):
    return _fit_grid(
        lgb.LGBMClassifier(random_state=seed, verbose=-1),
        {"n_estimators": [100, 200], "learning_rate": [0.05, 0.1], "max_depth": [3, 5]},
        X, y, use_smote, seed,
    )


TRAINERS = {"lr": train_logistic_regression, "lgbm": train_lightgbm}
MODEL_LABELS = {"lr": "Logistic Regression", "lgbm": "LightGBM"}


# ------------------------------------------------------------ prediction
def risk_level(prob: float) -> str:
    return "Low" if prob < 0.3 else "Medium" if prob < 0.6 else "High"


def predict_frame(model, scaler, feature_names, raw: pd.DataFrame) -> pd.DataFrame:
    X = scaler.transform(build_matrix(raw, feature_names))
    probs = model.predict_proba(X)[:, 1]
    out = raw.copy()
    out["churn_probability"] = np.round(probs, 4)
    out["prediction"] = model.predict(X).astype(int)
    out["risk_level"] = [risk_level(p) for p in probs]
    return out


# ------------------------------------------------------------ persistence
def save_artifacts(path: Path, model, scaler, feature_names, model_name: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"model": model, "scaler": scaler, "feature_names": feature_names, "model_name": model_name},
        path / "best_model.joblib",
    )


def load_artifacts(path: Path) -> dict | None:
    f = path / "best_model.joblib"
    return joblib.load(f) if f.exists() else None
