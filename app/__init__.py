"""Flask application factory."""
import os
from pathlib import Path

from flask import Flask

ROOT = Path(__file__).resolve().parent.parent


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        MAX_CONTENT_LENGTH=32 * 1024 * 1024,  # 32 MB uploads
        DATA_DIR=ROOT / "data",
        MODELS_DIR=ROOT / "models",
        SAMPLE_FILE="Bank Customer Churn Prediction.csv",
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
    )
    if config:
        app.config.update(config)

    from .routes import bp, init_state

    app.register_blueprint(bp)
    init_state(app)
    return app
