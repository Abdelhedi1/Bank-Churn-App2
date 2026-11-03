# Developer guide

## Setup
`python -m venv .venv`, activate it, `pip install -r requirements.txt`, then `python run.py`. Environment variables are listed in `.env.example`.

## Code style
Python 3.12, 120-character lines, rules in `ruff.toml` (pycodestyle, pyflakes, pyupgrade, import order). Check with `ruff check app tests`. Broad `except` blocks are allowed only where an error must be shown to the user, and carry a `noqa` comment with the reason.

## Tests
`pytest` runs all tests; `pytest --cov=app` adds coverage (CI requires at least 60%). Tests in `tests/test_ml.py` exercise the model code directly (unit level). Tests in `tests/test_app.py` call the running Flask app through HTTP with a real SQLite database (integration level).

## CI
`.github/workflows/ci.yml` runs on every push and pull request: install dependencies, `ruff check app tests`, `pytest --cov=app --cov-fail-under=60`, then the docs reminder.

## Contributing
Work on a branch, open a pull request, keep changes small, update `docs/CHANGELOG.md`, and record AI use in `docs/ai-usage-log.md`. See `CONTRIBUTING.md`.
