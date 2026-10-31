"""Entry point: `python run.py` starts the website on http://127.0.0.1:5000."""
import os

from app import create_app, scoring

app = create_app()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG") == "1"
    # The weekly scoring thread starts once (not in the debug reloader's parent process).
    if os.environ.get("SCHEDULER", "1") == "1" and (not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true"):
        scoring.start_scheduler(app)
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 5000)), debug=debug)
