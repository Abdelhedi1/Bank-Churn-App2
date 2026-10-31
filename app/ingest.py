"""Data Ingestion (design component C6, REQ-10).

In this version the "core banking / data lake" feed is a CSV file (uploaded or
placed in `data/`). Rows are cleaned and upserted into the Churn Data Store.
"""
from __future__ import annotations

import pandas as pd

from . import ml

NUMERIC = ["credit_score", "age", "tenure", "balance", "products_number", "estimated_salary"]
BINARY = ["credit_card", "active_member", "churn"]
STORE_COLUMNS = ["credit_score", "country", "gender", "age", "tenure", "balance", "products_number",
                 "credit_card", "active_member", "estimated_salary", "churn"]


def ingest_dataframe(conn, df: pd.DataFrame) -> dict:
    """Validate, clean and upsert customers. Returns {rows, new}."""
    df = ml.normalize_columns(df)
    target = ml.detect_target(df)
    if target and target != "churn":
        df = df.rename(columns={target: "churn"})
    missing = ml.missing_columns(df)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    df = df.copy()
    for col in NUMERIC + BINARY:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["country"] = df["country"].astype(str).str.strip().str.title()
    if "gender" in df.columns:
        df["gender"] = df["gender"].astype(str).str.strip().str.title()
    for col in STORE_COLUMNS:
        if col not in df.columns:
            df[col] = None

    ref_col = next((c for c in ("customer_id", "id", "client_id") if c in df.columns), None)
    if ref_col:
        refs = df[ref_col].astype(str).str.replace(r"\.0$", "", regex=True)
    else:
        start = conn.execute("SELECT COALESCE(MAX(id), 0) FROM customers").fetchone()[0]
        refs = pd.Series([f"AUTO-{start + i + 1}" for i in range(len(df))], index=df.index)

    # Branch = customer country; each branch has one demo relationship manager.
    rm_by_branch = {r["branch"]: r["id"] for r in
                    conn.execute("SELECT id, branch FROM users WHERE role = 'rm' AND active = 1")}
    before = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]

    clean = df[STORE_COLUMNS].astype(object).where(df[STORE_COLUMNS].notna(), None)
    rows = []
    for ref, rec in zip(refs, clean.itertuples(index=False)):
        rec = list(rec)
        country = rec[STORE_COLUMNS.index("country")]
        rows.append([ref, *rec, country, rm_by_branch.get(country)])

    cols = ["customer_ref", *STORE_COLUMNS, "branch", "assigned_rm"]
    updates = ", ".join(f"{c} = excluded.{c}" for c in cols[1:])
    conn.executemany(
        f"INSERT INTO customers({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
        f"ON CONFLICT(customer_ref) DO UPDATE SET {updates}", rows)
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    return {"rows": len(rows), "new": after - before}


def load_model_frame(conn, where: str = "1 = 1") -> tuple[pd.DataFrame, pd.Series]:
    """Customers as the ML code expects them (model input columns + churn), plus their ids."""
    cols = ", ".join(ml.INPUT_COLUMNS + ["churn"])
    df = pd.read_sql(f"SELECT id, {cols} FROM customers WHERE {where}", conn)
    ids = df.pop("id")
    # Optional columns that are empty in the store are dropped so features adapt (reduced CSVs).
    keep = [c for c in df.columns if c in ml.REQUIRED_COLUMNS or c == "churn" or df[c].notna().any()]
    return df[keep], ids
