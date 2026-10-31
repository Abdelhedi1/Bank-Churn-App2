# Changelog

All notable changes. Newest at the top. Based on [Keep a Changelog](https://keepachangelog.com).

## [Unreleased]

### Added
- Initial project scaffold from the CS 488 starter template.
- Flask web app: Home, Data, Features, Training and Prediction pages with a JSON API.
- ML core (`app/ml.py`): cleaning, feature engineering, Logistic Regression + LightGBM with SMOTE and 5-fold CV, KS/AUC metrics.
- Single-customer and batch (CSV) scoring with downloadable results.
- pytest tests (synthetic data) and ADR 0002 (Flask instead of Streamlit).

### Added (data)
- `data/Bank Customer Churn Prediction.csv`: 8,000-customer stratified sample (seed 42) of the public Churn_Modelling dataset; surnames and row numbers removed, columns renamed to the app's schema. The Data page's "Load sample data" button uses it.

### Changed
- `age`, `gender`, `tenure` and `balance` are now optional. Only credit_score, country, products_number, credit_card, active_member, estimated_salary and the churn target are required; features needing a missing column are skipped and the prediction form shows only the columns the model uses.

### Fixed
- Bugs carried over from the Streamlit prototype: missing imports, undefined `y` in model evaluation, swapped `roc_auc_score` arguments, a variable shadowing the `train_lr` function, and a gauge chart that was rendered twice.

## Unreleased — Lab 6 full web app
- Dark "BankChurn AI" interface (dashboard, prediction, insights, analytics, retention, data, admin).
- Login, roles, audit log, masked ids, alerts, weekly scoring, monthly report.
- Model management with LR vs LightGBM comparison; 8,000-customer demo dataset.
- Added skills (`.claude/skills`, `.github/skills`, `.cursor/skills`) and MCP configs.
