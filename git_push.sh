#!/bin/bash
# ── Productivity Tracker — Git Push Script ────────────────────────────────────
# Usage: bash git_push.sh "your commit message"
# If no message passed, defaults to a timestamped commit.

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
BRANCH="main"

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
RESET="\033[0m"

echo -e "${YELLOW}── Productivity Tracker — Git Push ──${RESET}"

# ── Move to repo root ─────────────────────────────────────────────────────────
cd "$REPO_DIR" || { echo -e "${RED}ERROR: Cannot cd to $REPO_DIR${RESET}"; exit 1; }

# ── Check git is initialised ──────────────────────────────────────────────────
if [ ! -d ".git" ]; then
  echo -e "${RED}ERROR: Not a git repository. Run 'git init' first.${RESET}"
  exit 1
fi

# ── Commit message ────────────────────────────────────────────────────────────
if [ -n "$1" ]; then
  COMMIT_MSG="$1"
else
  COMMIT_MSG="chore: update $(date '+%Y-%m-%d %H:%M')"
fi

# ── Show current status ───────────────────────────────────────────────────────
echo -e "\n${YELLOW}Changed files:${RESET}"
git status --short

# ── Stage all ─────────────────────────────────────────────────────────────────
echo -e "\n${YELLOW}Staging all changes...${RESET}"
git add .

# ── Commit ────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}Committing: \"$COMMIT_MSG\"${RESET}"
git commit -m "$COMMIT_MSG"

COMMIT_EXIT=$?
if [ $COMMIT_EXIT -ne 0 ]; then
  echo -e "${YELLOW}Nothing new to commit. Attempting push anyway...${RESET}"
fi

# ── Push ──────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}Pushing to origin/$BRANCH...${RESET}"
git push origin "$BRANCH"

PUSH_EXIT=$?
if [ $PUSH_EXIT -eq 0 ]; then
  echo -e "\n${GREEN}✓ Pushed successfully to origin/$BRANCH${RESET}"
else
  echo -e "\n${RED}✗ Push failed. Check your remote URL or token.${RESET}"
  echo -e "${YELLOW}Tip: run 'git remote -v' to verify remote.${RESET}"
  exit 1
fi
