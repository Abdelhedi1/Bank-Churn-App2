# AI Context — Single Source of Truth

> Every AI tool config in this repo (`CLAUDE.md`, `.github/copilot-instructions.md`,
> `.cursor/rules/`) points here. Keep it short, current and honest; update it in
> the same commit as the change it describes.

---

## 1. Project summary

**Name:** BankChurn AI (Churn Detection Pro)
**One-liner:** A web application that predicts which bank customers are likely to leave (churn).
**Primary users:** Relationship managers, retention managers, executives, administrators.
**The AI-assisted component:** Two ML classifiers (Logistic Regression and LightGBM, trained with SMOTE and 5-fold CV) score customers one by one, in batch and weekly; the best model by ROC AUC serves predictions.

- SRS / requirements: Lab 2/3 SRS (`docs/`)
- Architecture: [`docs/architecture.md`](docs/architecture.md)

## 2. Tech stack

| Layer       | Choice                                                         |
|-------------|----------------------------------------------------------------|
| Language(s) | Python 3.12+, HTML/CSS, vanilla JavaScript (ES2020)             |
| Framework   | Flask 3 (server-rendered pages + JSON API)                      |
| ML          | pandas, scikit-learn, imbalanced-learn (SMOTE), LightGBM        |
| Charts      | Plotly.js (CDN)                                                 |
| Database    | SQLite (`instance/churn.db`); trained model files in `models/`  |
| Package mgr | pip + venv (`requirements.txt`)                                 |
| Testing     | pytest, pytest-cov, ruff (CI on GitHub Actions)                 |
| Deploy      | none yet (`python run.py` locally)                              |

## 3. Project structure

- `app/ml.py` — pure ML code: cleaning, features, training, prediction (no Flask)
- `app/model_service.py` — model management (`ChurnModel` Strategy, `ModelManager`)
- `app/db.py` — SQLite schema and settings (data store)
- `app/auth.py` — login, roles, CSRF, audit log
- `app/ingest.py`, `app/scoring.py`, `app/advice.py`, `app/reports.py` — ingestion, batch and weekly scoring with alerts, suggested actions, monthly report
- `app/api.py` — JSON endpoints; `app/web.py` — pages
- `app/templates/` — Jinja pages (`base.html` + one per page)
- `app/static/` — `css/app.css`, `js/core.js`, `js/pages.js`
- `data/` — `Bank Customer Churn Prediction.csv`: 8,000-customer synthetic sample (no names; the only CSV committed)
- `models/` — saved trained model (gitignored)
- `tests/` — pytest tests (synthetic data only)
- `docs/` — architecture, UML, OpenAPI, ADRs, changelog, guides, reports
- `scripts/` — helper scripts

## 4. Conventions the assistant MUST follow

- **Style:** follow `.editorconfig`. Don't reformat unrelated code.
- **Naming:** `snake_case` in Python; `camelCase` in JavaScript; dataset columns are lowercase `snake_case`.
- **Comments:** explain *why*, not *what*.
- **Separation:** ML logic goes in `app/ml.py` and `app/model_service.py`; routes stay thin; no ML code in templates/JS.
- **Dependencies:** do **not** add a library without the team agreeing first.
- **Secrets:** never hardcode keys. Use `.env` (gitignored); see `.env.example`.
- **Data:** never commit real customer data or model files; the only committed CSV is the anonymised public sample in `data/`.
- **Tests:** new features come with at least one pytest test.
- **Commits:** small, Conventional-Commit style (`feat:`, `fix:`, `docs:`); update `docs/CHANGELOG.md` when behavior changes.

## 5. What NOT to do

- Don't invent requirements — ask or leave a `TODO` with your name.
- Don't delete or rewrite large sections you weren't asked to touch.
- Don't commit generated files, `.venv/`, `models/`, `instance/`, other CSV data or `.env`.
- Don't paste private customer data or credentials into AI chats.

## 6. Glossary / domain terms

- **Churn** — a customer who leaves the bank (target column `churn`, 1 = left).
- **SMOTE** — oversampling technique that balances churners vs. non-churners in the training set only.
- **AUC** — area under the ROC curve; used to pick the best model.
- **KS** — Kolmogorov–Smirnov statistic; separation between churner and non-churner score distributions.
- **Risk level** — Low (<30%), Medium (30–60%), High (≥60%) churn probability.

---

_Last updated: 2026-11-03 by Hedi._
