# User guide

Open http://127.0.0.1:5000 and sign in. Demo accounts: `admin`, `retention`, `executive`, `rm_france`, `rm_germany`, `rm_spain` (password in README).

## First use (administrator)
1. **Data & Upload** → *Load sample* (or upload your own CSV).
2. *Generate features*, then *Train*. Two models are compared; the best AUC becomes active. Scoring runs automatically afterwards.

## Every day
- **Dashboard**: totals, predicted churners, risk tiers, segment chart, top reasons and a quick prediction form.
- **Customer Prediction**: enter one customer's details; get the probability, the main reasons and suggested actions.
- **Customer Insights**: search and filter customers. Click a row to open the profile. Ids are masked (C-****1234). Each view is logged.
- **Retention Strategies**: alerts for customers at or above the threshold, and the action log. Add an action from a customer profile with *Add to Retention Campaign*. Nothing is ever sent to the customer automatically.
- **Churn Analytics**: model comparison, ROC curves, confusion matrices, drivers of churn, and the monthly KPI report (CSV download).
- **Administration** (admin): alert threshold, *Run scoring now*, users, audit log.

## Who can do what
Relationship manager: own customers only. Retention manager: all customers, exports, reports. Executive: dashboard and reports, read-only. Administrator: everything.

## Reading a result
Low < 30%, Medium 30–60%, High ≥ 60%. "Raises the risk" and "lowers the risk" explain what pushed the probability up or down for that customer. The probability is a model estimate, not a certainty.
