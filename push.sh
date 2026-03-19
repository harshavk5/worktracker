#!/bin/bash

# ── Productivity Tracker — Git Push Script ─────────────────────────────────
# Usage: ./push.sh "your commit message"
#        ./push.sh              (uses default message with timestamp)
# ───────────────────────────────────────────────────────────────────────────

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
BRANCH="main"

# Colours
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Colour

cd "$REPO_DIR" || { echo -e "${RED}✗ Could not find repo directory${NC}"; exit 1; }

echo -e "${CYAN}── Productivity Tracker — Git Push ──${NC}"
echo -e "   Repo : $REPO_DIR"
echo -e "   Branch: $BRANCH"
echo ""

# ── Commit message ──────────────────────────────────────────────────────────
if [ -n "$1" ]; then
  COMMIT_MSG="$1"
else
  COMMIT_MSG="chore: update $(date '+%Y-%m-%d %H:%M')"
fi

echo -e "${YELLOW}► Commit message:${NC} $COMMIT_MSG"
echo ""

# ── Check for changes ───────────────────────────────────────────────────────
if git diff --quiet && git diff --cached --quiet; then
  echo -e "${YELLOW}⚠ No changes to commit.${NC}"

  # Still offer to push if there are unpushed commits
  UNPUSHED=$(git log origin/$BRANCH..HEAD --oneline 2>/dev/null | wc -l | tr -d ' ')
  if [ "$UNPUSHED" -gt 0 ]; then
    echo -e "  Found $UNPUSHED unpushed commit(s). Pushing..."
    git push origin "$BRANCH" && \
      echo -e "${GREEN}✓ Pushed successfully.${NC}" || \
      echo -e "${RED}✗ Push failed. Check your token / branch rules.${NC}"
  fi
  exit 0
fi

# ── Stage → Commit → Push ───────────────────────────────────────────────────
echo -e "${YELLOW}► Staging all changes...${NC}"
git add .

echo -e "${YELLOW}► Committing...${NC}"
git commit -m "$COMMIT_MSG"

echo -e "${YELLOW}► Pushing to origin/$BRANCH...${NC}"
git push origin "$BRANCH"

if [ $? -eq 0 ]; then
  echo ""
  echo -e "${GREEN}✓ Done. Changes pushed to origin/$BRANCH.${NC}"
else
  echo ""
  echo -e "${RED}✗ Push failed.${NC}"
  echo -e "  Common causes:"
  echo -e "  1. Token expired     → GitHub → Settings → Developer Settings → regenerate PAT"
  echo -e "  2. Branch rule       → create a PR branch instead: git checkout -b feat/your-change"
  echo -e "  3. Remote rejected   → run: git pull origin $BRANCH --rebase  then push again"
  exit 1
fi
