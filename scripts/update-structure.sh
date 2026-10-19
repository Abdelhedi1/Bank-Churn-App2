#!/usr/bin/env bash
# Regenerate the project-structure tree in README.md between the markers:
#   <!-- STRUCTURE:START --> ... <!-- STRUCTURE:END -->
# Run it whenever you add/move folders:  ./scripts/update-structure.sh
set -euo pipefail

cd "$(dirname "$0")/.."
README="README.md"

TREE_FILE="$(mktemp)"
OUT_FILE="$(mktemp)"
trap 'rm -f "$TREE_FILE" "$OUT_FILE"' EXIT

# Build a tree, ignoring noise. Prefer `tree` if installed; else use `find`.
if command -v tree >/dev/null 2>&1; then
  tree -a -L 2 -I '.git|node_modules|.venv|venv|dist|build|__pycache__|.next|coverage|DerivedData' --dirsfirst > "$TREE_FILE"
else
  find . -maxdepth 2 \
      -not -path '*/.git/*' -not -path '*/node_modules/*' \
      -not -path '*/.venv/*' -not -path '*/venv/*' \
      -not -path '*/dist/*' -not -path '*/build/*' \
      -not -path '*/__pycache__/*' -not -path '*/.next/*' \
      -not -path '*/coverage/*' \
      | sed 's|^\./||' | grep -vE '^\.git(/|$)' | sort > "$TREE_FILE"
fi

# Replace the block between the markers. awk reads the tree from a file
# (getline) so there are no multi-line-variable issues on macOS/BSD awk.
awk -v treefile="$TREE_FILE" '
  /<!-- STRUCTURE:START/ {
    print
    print "```"
    while ((getline line < treefile) > 0) print line
    close(treefile)
    print "```"
    skip = 1
    next
  }
  /<!-- STRUCTURE:END/ { skip = 0 }
  skip != 1 { print }
' "$README" > "$OUT_FILE"

mv "$OUT_FILE" "$README"
trap - EXIT
rm -f "$TREE_FILE"
echo "Updated project structure in $README"
