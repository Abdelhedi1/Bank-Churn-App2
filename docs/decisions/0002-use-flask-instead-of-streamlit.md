# 2. Use Flask (HTML/CSS/JS) instead of Streamlit

- **Status:** Accepted
- **Date:** 2026-10-19

## Context

The first prototype of the churn app was built with Streamlit. Lab 6 asks for a
real, collaborative project workspace, and we want a "real website": our own
pages, routes, styling and a JSON API that can be tested and deployed like any
web app. Streamlit reruns the script on every interaction, hides the HTTP layer
and limits layout control. The team already knows Python and the ML libraries.

## Decision

Build the app with **Flask** (Python): server-rendered Jinja pages, a small JSON
API under `/api`, vanilla JavaScript on the front end and Plotly.js for charts.
ML code stays in a framework-free module (`app/ml.py`) so it is unit-testable.

## Consequences

- Easier: full control of design, URLs and API; endpoints and ML code are
  testable with pytest; the ML code is reusable outside the web layer.
- Harder: more code than Streamlit (templates, JS); state is held in memory, so
  the app is single-user until a database/session layer is added.
- Committed to: Python + Flask; Plotly.js loaded from a CDN (needs internet).
