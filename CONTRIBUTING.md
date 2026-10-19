# Contributing & Team Workflow

This is how our team works together on this repo. Everyone follows the same
rules so we don't step on each other or break `main`. Read it once, then keep it
handy.

## 1. Golden rules

1. **Never commit directly to `main`.** `main` always works.
2. **One feature = one branch = one Pull Request (PR).**
3. **At least one teammate reviews** every PR before it merges.
4. **CI must pass** (green check) before merging.
5. **Never commit secrets** (`.env`, API keys). They belong in `.env` only.

## 2. Branch naming

```
feat/<short-name>     a new feature      e.g. feat/login-page
fix/<short-name>      a bug fix          e.g. fix/empty-cart-crash
docs/<short-name>     documentation      e.g. docs/architecture
chore/<short-name>    tooling/config     e.g. chore/add-linter
```

## 3. Daily flow

```bash
git checkout main
git pull                       # get everyone's latest work
git checkout -b feat/my-thing  # start a fresh branch

# ... do work, commit as you go ...

git push -u origin feat/my-thing   # push your branch
# then open a Pull Request on GitHub
```

## 4. Commit messages

Keep them small and descriptive. We use a light version of
[Conventional Commits](https://www.conventionalcommits.org):

```
feat: add study-partner matching by course
fix: stop crash when the search box is empty
docs: document the matching algorithm
chore: add Prettier config
```

**One logical change per commit.** If your message needs the word "and", it's
probably two commits.

## 5. Pull Requests

- Fill in the PR template (it appears automatically).
- Link the issue it closes, if any (`Closes #12`).
- Keep PRs small — easier to review, fewer merge conflicts.
- If you changed behavior, update `docs/CHANGELOG.md` **in the same PR**.
- If you made a notable design choice, add an ADR in `docs/decisions/`.

## 6. Using AI assistants responsibly

AI tools (Copilot, Claude, Cursor) are encouraged — this is an AI-First course —
but you own every line you commit:

- **Read and understand** AI-generated code before committing it. You will be
  asked to explain your own PRs.
- Keep `AI_CONTEXT.md` up to date so suggestions stay relevant.
- Never paste secrets, credentials, or private user data into an AI chat.
- If AI writes a big chunk, review it like a teammate's PR: does it fit our
  conventions? Is it tested? Does it do only what we asked?

## 7. Keeping docs alive (lightweight)

- Behavior changed? → add a line to `docs/CHANGELOG.md`.
- Made a real decision (framework, data model, trade-off)? → add an ADR.
- Moved files around? → run `./scripts/update-structure.sh`.

A git hook will gently remind you if you change code without touching docs. It
only warns — it won't block you.

## 8. Resolving disagreements

Follow your team charter's conflict rule (from Lab 0). Default: discuss, then if
still split, the person who owns that area decides, and we revisit later.
