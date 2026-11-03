"""Churn Data Store (design component C9): SQLite behind small repository helpers.

Business code asks this module for data and never builds connections itself, so
the store can later move to PostgreSQL without touching the services (design
pattern: Repository, REQ-10).
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('rm', 'retention_manager', 'admin', 'executive')),
    branch TEXT,
    password_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_ref TEXT UNIQUE NOT NULL,
    credit_score REAL, country TEXT, gender TEXT, age REAL, tenure REAL, balance REAL,
    products_number REAL, credit_card INTEGER, active_member INTEGER, estimated_salary REAL,
    churn INTEGER,
    branch TEXT,
    assigned_rm INTEGER REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS ix_customers_rm ON customers(assigned_rm);

CREATE TABLE IF NOT EXISTS scoring_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL, finished_at TEXT,
    status TEXT NOT NULL,
    trigger TEXT NOT NULL,
    model_name TEXT,
    customers_scored INTEGER DEFAULT 0,
    high_risk_count INTEGER DEFAULT 0,
    duration_s REAL,
    error TEXT
);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES scoring_jobs(id) ON DELETE CASCADE,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    probability REAL NOT NULL,
    risk_tier TEXT NOT NULL,
    top_factors TEXT NOT NULL,
    computed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_scores_job ON scores(job_id, probability DESC);
CREATE INDEX IF NOT EXISTS ix_scores_customer ON scores(customer_id);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    rm_id INTEGER REFERENCES users(id),
    probability REAL NOT NULL,
    threshold REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'acknowledged')),
    created_at TEXT NOT NULL,
    acknowledged_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_alerts_rm ON alerts(rm_id, status);

CREATE TABLE IF NOT EXISTS retention_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    type TEXT NOT NULL,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'done')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    user_id INTEGER,
    username TEXT,
    role TEXT,
    action TEXT NOT NULL,
    customer_id INTEGER,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_ts ON audit_log(ts DESC);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    # The SRS does not define the alert threshold (open question in the Lab 5 design).
    "alert_threshold": "60",
}


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def connect(path: str | Path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(path: str | Path) -> None:
    conn = connect(path)
    conn.executescript(SCHEMA)
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()


def get_db() -> sqlite3.Connection:
    """One connection per request, closed automatically at teardown."""
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
    return g.db


def close_db(_exc=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def get_setting(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else DEFAULT_SETTINGS[key]


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def mask_ref(ref: str) -> str:
    """Anonymised customer reference shown on dashboards (REQ-15)."""
    tail = str(ref)[-4:]
    return f"C-****{tail}"
