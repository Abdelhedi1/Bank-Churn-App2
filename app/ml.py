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
# Columns every dataset must have; the rest are optional and their features are
# only built when the column exists (so a reduced CSV still works).
REQUIRED_COLUMNS = [
    "credit_score", "country", "products_number", "credit_card", "active_member", "estimated_salary",
]
OPTIONAL_COLUMNS = ["gender", "age", "tenure", "balance"]
INPUT_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
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
    return [c for c in REQUIRED_COLUMNS if c not in df.columns]


def input_columns(df: pd.DataFrame) -> list[str]:
    """Known input columns present in df (what the prediction form must ask for)."""
    return [c for c in INPUT_COLUMNS if c in df.columns]


# ------------------------------------------------------------- features
def create_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    has = set(df.columns)
    df["activity_score"] = df["products_number"] * df["active_member"]
    df["credit_active"] = df["credit_card"] * df["active_member"]
    if "balance" in has:
        df["balance_salary_ratio"] = df["balance"] / (df["estimated_salary"] + 1)
        df["low_balance"] = np.where(df["balance"] < 1000, 1, 0)
        df["high_value"] = np.where((df["balance"] > 100000) & (df["products_number"] >= 2), 1, 0)
    if "tenure" in has:
        df["tenure_risk"] = 1 / (df["tenure"] + 1)
    if "age" in has:
        df["age_risk"] = np.where((df["age"] < 30) | (df["age"] > 60), 1, 0)
    return df


def encode_features(df: pd.DataFrame) -> pd.DataFrame:
    """Gender -> 0/1 (if present), country -> one-hot with a fixed column set (train == serve)."""
    df = df.copy()
    if "gender" in df.columns:
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
        "input_columns": input_columns(df),
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
def save_artifacts(path: Path, model, scaler, feature_names, model_name: str, inputs: list[str],
                   meta: dict | None = None) -> None:
    path.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"model": model, "scaler": scaler, "feature_names": feature_names,
         "model_name": model_name, "input_columns": inputs, "meta": meta or {}},
        path / "best_model.joblib",
    )


def load_artifacts(path: Path) -> dict | None:
    f = path / "best_model.joblib"
    return joblib.load(f) if f.exists() else None


# ----------------------------------------------------------- explanations
FEATURE_LABELS = {
    "credit_score": "Credit score", "age": "Age", "tenure": "Years as a customer",
    "balance": "Account balance", "products_number": "Number of products",
    "credit_card": "Has a credit card", "active_member": "Active member",
    "estimated_salary": "Estimated salary", "activity_score": "Product activity",
    "credit_active": "Active card use", "balance_salary_ratio": "Balance compared with salary",
    "low_balance": "Very low balance", "high_value": "High-value profile",
    "tenure_risk": "Short time as a customer", "age_risk": "Age bracket (under 30 or over 60)",
    "gender_encoded": "Male customer", "country_France": "Lives in France",
    "country_Germany": "Lives in Germany", "country_Spain": "Lives in Spain",
}
BINARY_FEATURES = {"credit_card", "active_member", "credit_active", "low_balance", "high_value",
                   "age_risk", "gender_encoded", "country_France", "country_Germany", "country_Spain"}


def feature_label(name: str) -> str:
    return FEATURE_LABELS.get(name, name.replace("_", " ").capitalize())


def _format_value(name: str, value: float) -> str:
    if name in BINARY_FEATURES:
        return "Yes" if value >= 0.5 else "No"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:.0f}" if float(value).is_integer() else f"{value:.2f}"


def _contributions(model, scaled: np.ndarray) -> np.ndarray:
    """Per-feature push on the churn score (log-odds). Positive = raises risk."""
    if hasattr(model, "booster_"):  # LightGBM computes exact tree contributions itself
        return np.asarray(model.predict(scaled, pred_contrib=True))[:, :-1]
    if hasattr(model, "coef_"):  # linear model: coefficient x scaled value
        return scaled * model.coef_[0]
    return np.zeros_like(scaled)


def explain_frame(model, scaler, feature_names, raw: pd.DataFrame, top_n: int = 3) -> list[list[dict]]:
    """Top factors behind each customer's score (REQ-04)."""
    X = build_matrix(raw, feature_names)
    contrib = _contributions(model, scaler.transform(X))
    order = np.argsort(-np.abs(contrib), axis=1)[:, :top_n]
    values = X.to_numpy()
    out = []
    for i in range(len(X)):
        out.append([
            {"feature": feature_names[j], "label": feature_label(feature_names[j]),
             "value": _format_value(feature_names[j], float(values[i, j])),
             "impact": round(float(contrib[i, j]), 3),
             "direction": "raises" if contrib[i, j] > 0 else "lowers"}
            for j in order[i]
        ])
    return out


def feature_importance(model, feature_names) -> list[dict]:
    """Global drivers of churn: each feature's share of the model's total importance."""
    if hasattr(model, "booster_"):
        raw = np.asarray(model.booster_.feature_importance(importance_type="gain"), dtype=float)
    elif hasattr(model, "coef_"):
        raw = np.abs(model.coef_[0])
    else:
        return []
    total = raw.sum() or 1.0
    ranked = sorted(zip(feature_names, raw / total), key=lambda t: -t[1])
    return [{"feature": f, "label": feature_label(f), "share": round(float(v), 4)} for f, v in ranked]
