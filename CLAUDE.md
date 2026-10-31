# CLAUDE.md

This file gives Claude (Claude Code, the Claude desktop/web app, and the Claude
VS Code extension) context about this repository.

**Read [`AI_CONTEXT.md`](AI_CONTEXT.md) first — it is the single source of truth**
for the project summary, tech stack, structure, and conventions. Everything below
just adds Claude-specific working notes.

## How to work in this repo

- Follow every rule in `AI_CONTEXT.md` (style, secrets, dependencies, tests, commits).
- Before making changes, skim `docs/architecture.md` and the latest entries in
  `docs/decisions/` so your changes fit existing decisions.
- Keep changes small and focused. Explain non-obvious choices in the PR description.
- When behavior changes, update `docs/CHANGELOG.md` in the same change.
- Run the project's tests before claiming something works; report real output.

## Useful commands

<!-- Fill these in once your stack is set up so Claude can build/test correctly. -->

```bash
# install deps:   python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
# run the app:    python run.py        (http://127.0.0.1:5000)
# run tests:      pytest
# lint/format:    (none configured yet)
```

## Project-specific guidance

<!-- Anything Claude keeps getting wrong goes here. Add to it over the semester. -->

- ML code lives in `app/ml.py`; model lifecycle in `app/model_service.py` (Strategy). Keep route modules (`web.py`, `api.py`, `auth.py`) thin.
- Tests use synthetic data (`tests/conftest.py`). `data/Bank Customer Churn Prediction.csv` is a synthetic demo dataset (no names), safe to commit.
- Skills are in `.claude/skills/` (frontend-design, webapp-testing); MCP servers in `.mcp.json`. Never hardcode tokens.
