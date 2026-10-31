"""Flask application factory."""
import logging
import os
import secrets
from pathlib import Path

from flask import Flask, g, request

ROOT = Path(__file__).resolve().parent.parent


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    secret = os.environ.get("SECRET_KEY")
    if not secret:
        # No key configured: use a random one. Sessions then end when the server restarts.
        secret = secrets.token_hex(32)
    app.config.update(
        MAX_CONTENT_LENGTH=32 * 1024 * 1024,  # 32 MB uploads
        DATA_DIR=ROOT / "data",
        MODELS_DIR=Path(os.environ.get("MODELS_DIR", ROOT / "models")),
        DB_PATH=Path(os.environ.get("DB_PATH", ROOT / "instance" / "churn.db")),
        SAMPLE_FILE="Bank Customer Churn Prediction.csv",
        SECRET_KEY=secret,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",  # set behind HTTPS
    )
    if config:
        app.config.update(config)

    from . import auth, db
    from .api import bp as api_bp
    from .model_service import ModelManager
    from .web import bp as web_bp

    db.init_db(app.config["DB_PATH"])
    conn = db.connect(app.config["DB_PATH"])
    if auth.seed_demo_users(conn, auth.demo_password()):
        logging.getLogger(__name__).warning(
            "Demo accounts created (admin, retention, executive, rm_france, rm_germany, rm_spain). "
            "Change DEMO_PASSWORD in .env before sharing the app.")
    conn.close()

    app.extensions["models"] = ModelManager(app.config["MODELS_DIR"])
    app.teardown_appcontext(db.close_db)
    app.before_request(auth.load_user)
    app.before_request(auth.check_csrf)
    app.register_blueprint(auth.bp)
    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp)

    @app.context_processor
    def inject():
        user = g.get("user")
        return {"csrf_token": auth.csrf_token, "user": user, "ROLES": auth.ROLES}

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if request.endpoint != "static":
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    return app
