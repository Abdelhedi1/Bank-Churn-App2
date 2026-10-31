"""HTML pages (design component C1: Dashboard & Reporting Web App)."""
from flask import Blueprint, g, render_template

from . import db
from .auth import require

bp = Blueprint("web", __name__)

ALL = ("rm", "retention_manager", "admin", "executive")
STAFF = ("rm", "retention_manager", "admin")

# key, label, endpoint, roles allowed
NAV = [
    ("dashboard", "Dashboard", "web.dashboard", ALL),
    ("prediction", "Customer Prediction", "web.prediction", ALL),
    ("insights", "Customer Insights", "web.insights", STAFF),
    ("analytics", "Churn Analytics", "web.analytics", ALL),
    ("retention", "Retention Strategies", "web.retention", STAFF),
    ("data", "Data & Upload", "web.data", ("admin",)),
    ("admin", "Administration", "web.admin", ("admin",)),
]


@bp.app_context_processor
def shell():
    user = g.get("user")
    if not user:
        return {"nav": [], "unread_alerts": 0}
    conn = db.get_db()
    if user["role"] == "rm":
        n = conn.execute("SELECT COUNT(*) FROM alerts WHERE status='new' AND rm_id=?", (user["id"],)).fetchone()[0]
    elif user["role"] in ("retention_manager", "admin"):
        n = conn.execute("SELECT COUNT(*) FROM alerts WHERE status='new'").fetchone()[0]
    else:
        n = 0
    return {"nav": [x for x in NAV if user["role"] in x[3]], "unread_alerts": n}


@bp.get("/")
@require()
def dashboard():
    return render_template("dashboard.html", page="dashboard")


@bp.get("/prediction")
@require()
def prediction():
    return render_template("prediction.html", page="prediction")


@bp.get("/insights")
@require(*STAFF)
def insights():
    return render_template("insights.html", page="insights")


@bp.get("/analytics")
@require()
def analytics():
    return render_template("analytics.html", page="analytics")


@bp.get("/retention")
@require(*STAFF)
def retention():
    return render_template("retention.html", page="retention")


@bp.get("/data")
@require("admin")
def data():
    return render_template("data.html", page="data")


@bp.get("/admin")
@require("admin")
def admin():
    return render_template("admin.html", page="admin")
