# GitHub Copilot — Repository Instructions

GitHub Copilot reads this file automatically for Chat and code suggestions in
this repository (VS Code, Visual Studio, and github.com).

**Your single source of truth for this project is [`/AI_CONTEXT.md`](../AI_CONTEXT.md).**
Read it and follow it. It describes the project, the tech stack, the folder
layout, and the conventions every suggestion must respect.

Quick rules (the full list is in `AI_CONTEXT.md`):

- Match the existing code style and `.editorconfig`; do not reformat unrelated code.
- Never hardcode secrets. Use environment variables (`.env`, which is gitignored).
- Do not add new dependencies without a note in your PR explaining why.
- New features include at least one test.
- When behavior changes, update `docs/CHANGELOG.md`.
- If a requirement is unclear, leave a `TODO:` comment rather than guessing.

When this file and `AI_CONTEXT.md` disagree, `AI_CONTEXT.md` wins — update both.
