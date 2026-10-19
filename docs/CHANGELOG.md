# Changelog

All notable changes. Newest at the top. Based on [Keep a Changelog](https://keepachangelog.com).

## [Unreleased]

### Added
- Initial project scaffold from the CS 488 starter template.
- Flask web app: Home, Data, Features, Training and Prediction pages with a JSON API.
- ML core (`app/ml.py`): cleaning, feature engineering, Logistic Regression + LightGBM with SMOTE and 5-fold CV, KS/AUC metrics.
- Single-customer and batch (CSV) scoring with downloadable results.
- pytest tests (synthetic data) and ADR 0002 (Flask instead of Streamlit).

### Fixed
- Bugs carried over from the Streamlit prototype: missing imports, undefined `y` in model evaluation, swapped `roc_auc_score` arguments, a variable shadowing the `train_lr` function, and a gauge chart that was rendered twice.
