#!/usr/bin/env bash
# One-time project setup. Run this once after cloning:  ./scripts/setup.sh
# Safe to run again — it just re-applies settings.
set -euo pipefail

cd "$(dirname "$0")/.."   # repo root

echo "==> Setting up this project..."

# 1. Point git at our shared hooks folder (so the docs reminder works for everyone).
if [ -d .git ]; then
  git config core.hooksPath .githooks
  chmod +x .githooks/* 2>/dev/null || true
  echo "    git hooks enabled (.githooks)"
else
  echo "    (!) Not a git repo yet. Run 'git init' first, then re-run this script."
fi

# 2. Make scripts executable.
chmod +x scripts/*.sh 2>/dev/null || true

# 3. Remind about environment file.
if [ ! -f .env ] && [ -f .env.example ]; then
  echo "    (!) No .env found. Run: cp .env.example .env   then fill it in."
fi

echo "==> Done."
echo
echo "Next steps:"
echo "  1. cp .env.example .env   (and fill in values)"
echo "  2. install dependencies   (see docs/setup.md)"
echo "  3. fill in AI_CONTEXT.md   (so your AI tools understand the project)"
