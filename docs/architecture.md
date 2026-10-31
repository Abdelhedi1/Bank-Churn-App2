# Architecture (Lab 5 design → code)

Flask app factory with three blueprints (`auth`, `web`, `api`), SQLite store, vanilla JS + Plotly.

| Design | Responsibility | Code |
|---|---|---|
| C1 Dashboard | Pages and charts | `app/web.py`, `app/templates/`, `static/js/pages.js` |
| C2 Access control & audit | Login, roles, RM scope, CSRF, audit | `app/auth.py` |
| C3 Insights API | JSON endpoints | `app/api.py` |
| C4 Alerts | Alerts for high-risk customers (Observer) | `app/scoring.py` (`subscribe`, `notify_relationship_managers`) |
| C5 Retention actions | Suggestions, action log, CSV export | `app/advice.py`, `api.py` |
| C6 Ingestion | CSV upload, upsert by customer ref | `app/ingest.py` |
| C7 Scoring engine | Batch scoring, weekly scheduler | `app/scoring.py` |
| C8 Model management | Train/compare/select (Strategy: `ChurnModel`, `SklearnChurnModel`, `ModelManager`) | `app/model_service.py`, `app/ml.py` |
| C9 Churn data store | SQLite (Repository) | `app/db.py` |

Flow: Upload CSV → generate features → train LR + LightGBM → best AUC becomes active → batch scoring stores probabilities → dashboard, insights, alerts and reports read the store.
Roles: relationship manager (own customers only), retention manager, executive (read-only), admin.
Risk tiers: Low <30, Medium 30–60, High ≥60 (alert threshold configurable).
