# Requirements traceability (SRS REQ-01..20)

Status is stated honestly from what the code and tests do. Check the SRS wording for each REQ before the demo.

| Area | REQ | Status | Where / note |
|---|---|---|---|
| Dashboard & KPIs | 01–03 | Met | Dashboard, Customer Insights, Churn Analytics |
| Prediction & factors | 04–06 | Met | `/api/predict`, drawer, explanations (LightGBM contributions / LR coefficients) |
| Alerts | 07 | Partly | In-app alerts only; no e-mail channel |
| Monthly report | 08 | Met | `/api/reports/monthly(.csv)` |
| Data ingestion | 09–11 | Met | Data & Upload page |
| Weekly scoring | 12 | Met | Scheduler (7 days); 6,370 customers scored in ~2–4 s |
| Security | 13 | Partly | Hashed passwords, CSRF, headers; encryption at rest/in transit must be done at deployment (HTTPS, disk) |
| Audit & masking | 14–15 | Met | Audit log, masked ids `C-****1234` |
| Roles | 16 | Met | 4 roles, RM scope |
| Performance | 17–18 | Not verified | Not load-tested |
| Retention actions | 19–20 | Met | Suggestions only, never auto-sent |

Limits: scoring is in-sample for training rows; branch = country and demo RM assignment are assumptions; the dataset has no product types or dates.
