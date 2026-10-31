# Full Setup Guide

## Prerequisites

- Git
- Python 3.12+
- A code editor with an AI assistant (VS Code + GitHub Copilot recommended)

## Steps

```bash
# 1. Clone
git clone <your-repo-url>
cd <repo>

# 2. One-time project setup (git hooks, etc.) — on Windows use Git Bash
./scripts/setup.sh

# 3. Environment variables
cp .env.example .env

# 4. Install dependencies
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 5. Data: data/Bank Customer Churn Prediction.csv is included (8,000 customers);
#    click "Load sample data" on the Data page, or upload any CSV

# 6. Run
python run.py                    # open http://127.0.0.1:5000

# 7. Run tests
pytest
```

## Troubleshooting

- **Problem:** "Sample file not found" on the Data page.
  **Fix:** make sure `data/Bank Customer Churn Prediction.csv` exists, or upload a CSV.
- **Problem:** Charts are empty.
  **Fix:** Plotly.js loads from a CDN — check your internet connection.
- **Problem:** `lightgbm` fails to install on macOS.
  **Fix:** `brew install libomp`, then reinstall.
