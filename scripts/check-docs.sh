#!/usr/bin/env bash
# Lightweight "did you update the docs?" check.
#
# It compares the commits you're about to push against the remote and, if you
# changed code but touched NO documentation, it prints a friendly reminder.
# It NEVER blocks you — it always exits 0. It's a nudge, not a gate.
set -uo pipefail

cd "$(dirname "$0")/.."

# Figure out what range of commits to inspect.
if git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
  RANGE="@{u}..HEAD"            # commits not yet on the remote branch
elif git rev-parse HEAD >/dev/null 2>&1; then
  RANGE="HEAD~1..HEAD"          # fallback: just the last commit
else
  exit 0                        # no commits yet, nothing to check
fi

CHANGED="$(git diff --name-only "$RANGE" 2>/dev/null || true)"
[ -z "$CHANGED" ] && exit 0

# Did any "code-like" file change?
CODE_CHANGED="$(echo "$CHANGED" | grep -Ei '\.(js|jsx|ts|tsx|py|java|kt|go|rb|rs|c|cpp|cs|php|swift|dart|vue|svelte)$' || true)"

# Did any docs change?
DOCS_CHANGED="$(echo "$CHANGED" | grep -Ei '(^docs/|README|CHANGELOG|\.md$)' || true)"

if [ -n "$CODE_CHANGED" ] && [ -z "$DOCS_CHANGED" ]; then
  echo ""
  echo "  📝  Reminder: you changed code but no docs in these commits."
  echo "      If behavior changed, add a line to docs/CHANGELOG.md."
  echo "      If you made a real decision, add an ADR in docs/decisions/."
  echo "      (This is only a reminder — your push will continue.)"
  echo ""
fi

exit 0
