"""Access Control & Audit (design component C2, REQ-11/13/14/15).

Acts as the protection proxy in front of customer data: every request passes
through `load_user` + `require(...)`, and every read of individual customer
churn data is written to the audit log.
"""
from __future__ import annotations

import hmac
import os
import secrets
from functools import wraps

from flask import (Blueprint, current_app, g, jsonify, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from . import db

bp = Blueprint("auth", __name__)

ROLES = {
    "rm": "Relationship manager",
    "retention_manager": "Retention manager",
    "admin": "Administrator",
    "executive": "Executive",
}

# Demo accounts. One relationship manager per branch (branch = customer country).
DEMO_USERS = [
    ("admin", "Hedi Hamdi", "admin", None),
    ("retention", "Retention Manager", "retention_manager", None),
    ("executive", "Executive Viewer", "executive", None),
    ("rm_france", "RM France", "rm", "France"),
    ("rm_germany", "RM Germany", "rm", "Germany"),
    ("rm_spain", "RM Spain", "rm", "Spain"),
]


def seed_demo_users(conn, password: str) -> bool:
    """Create the demo accounts once, on an empty users table."""
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        return False
    for username, name, role, branch in DEMO_USERS:
        conn.execute(
            "INSERT INTO users(username, name, role, branch, password_hash) VALUES (?,?,?,?,?)",
            (username, name, role, branch, generate_password_hash(password)),
        )
    conn.commit()
    return True


# ----------------------------------------------------------------- audit
def audit(action: str, customer_id: int | None = None, detail: str = "", user=None) -> None:
    user = user if user is not None else g.get("user")
    conn = db.get_db()
    conn.execute(
        "INSERT INTO audit_log(ts, user_id, username, role, action, customer_id, detail) "
        "VALUES (?,?,?,?,?,?,?)",
        (db.now(), user["id"] if user else None, user["username"] if user else None,
         user["role"] if user else None, action, customer_id, detail[:500]),
    )
    conn.commit()


def audit_many(action: str, customer_ids: list[int], detail: str = "") -> None:
    """One audit row per customer whose churn data was shown (REQ-14)."""
    user, conn = g.user, db.get_db()
    ts = db.now()
    conn.executemany(
        "INSERT INTO audit_log(ts, user_id, username, role, action, customer_id, detail) "
        "VALUES (?,?,?,?,?,?,?)",
        [(ts, user["id"], user["username"], user["role"], action, cid, detail[:500])
         for cid in customer_ids],
    )
    conn.commit()


# ----------------------------------------------------------------- scope
def scope_sql(user, alias: str = "c") -> tuple[str, list]:
    """Relationship managers only see the customers assigned to them."""
    if user["role"] == "rm":
        return f"{alias}.assigned_rm = ?", [user["id"]]
    return "1 = 1", []


# ------------------------------------------------------------ decorators
def _wants_json() -> bool:
    return request.path.startswith("/api/")


def require(*roles: str):
    """Require a signed-in user, optionally with one of the given roles."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = g.get("user")
            if user is None:
                if _wants_json():
                    return jsonify(error="Sign in required."), 401
                return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
            if roles and user["role"] not in roles:
                if _wants_json():
                    return jsonify(error="Your role is not allowed to do this."), 403
                return render_template("forbidden.html", page="forbidden"), 403
            return fn(*args, **kwargs)
        return wrapper
    return deco


# ------------------------------------------------------------------ CSRF
def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


def check_csrf():
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
    if not hmac.compare_digest(sent, session.get("csrf", "")):
        if _wants_json():
            return jsonify(error="Security token missing or expired. Reload the page."), 400
        return render_template("forbidden.html", page="forbidden",
                               message="Security token expired. Reload the page and try again."), 400
    return None


def load_user() -> None:
    g.user = None
    uid = session.get("uid")
    if uid:
        row = db.get_db().execute("SELECT * FROM users WHERE id = ? AND active = 1", (uid,)).fetchone()
        if row:
            g.user = row
        else:
            session.pop("uid", None)


# ----------------------------------------------------------------- views
def _safe_next(target: str | None) -> str:
    # Only allow local paths, never an absolute URL (open-redirect protection).
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("web.dashboard")


@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        row = db.get_db().execute(
            "SELECT * FROM users WHERE username = ? AND active = 1", (username,)).fetchone()
        if row and check_password_hash(row["password_hash"], request.form.get("password", "")):
            session.clear()
            session["uid"] = row["id"]
            session["csrf"] = secrets.token_hex(16)
            audit("login", user=row)
            return redirect(_safe_next(request.args.get("next")))
        audit("login_failed", detail=f"username={username[:40]}", user=None)
        error = "Wrong username or password."
    return render_template("login.html", error=error)


@bp.post("/logout")
def logout():
    if g.get("user"):
        audit("logout")
    session.clear()
    return redirect(url_for("auth.login"))


def demo_password() -> str:
    return os.environ.get("DEMO_PASSWORD", "churn-demo-2026")
