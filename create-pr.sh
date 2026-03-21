#!/bin/bash

# Script to create a branch, modify a text file with random value, and create a PR

set -e

# Validation checks
echo "🔍 Validating repository state..."

# Check if we're on main branch
CURRENT_BRANCH=$(git branch --show-current)
if [[ "$CURRENT_BRANCH" != "main" ]]; then
  echo "❌ Error: You must be on the main branch to run this script."
  echo "   Current branch: $CURRENT_BRANCH"
  echo "   Run: git checkout main"
  exit 1
fi

# Check for uncommitted changes
if [[ -n $(git status --porcelain) ]]; then
  echo "❌ Error: You have uncommitted changes. Please commit or stash them first."
  git status --short
  exit 1
fi

echo "✅ Repository state validated"

# Configuration
FILE_NAME="test-file.txt"
BRANCH_NAME="test-branch-$(date +%s)"
RANDOM_VALUE=$(uuidgen | head -c 8)

echo "Creating test branch and pull request..."
echo "Branch: $BRANCH_NAME"
echo "Random value: $RANDOM_VALUE"

# Create and switch to new branch
git checkout -b "$BRANCH_NAME"

# Create or modify the test file with random value
echo "Random test value: $RANDOM_VALUE" > "$FILE_NAME"
echo "Timestamp: $(date)" >> "$FILE_NAME"
echo "Branch: $BRANCH_NAME" >> "$FILE_NAME"

# Add and commit changes
git add "$FILE_NAME"
git commit -m "Add random test value $RANDOM_VALUE"

# Push branch to origin
git push -u origin "$BRANCH_NAME"

# Create pull request using gh CLI
echo "Creating pull request..."
PR_URL=$(gh pr create \
  --title "Test PR with random value $RANDOM_VALUE" \
  --body "This is an automated test PR that adds a random value ($RANDOM_VALUE) to $FILE_NAME.

**Changes:**
- Added random test value: $RANDOM_VALUE
- Timestamp: $(date)
- Branch: $BRANCH_NAME

This PR is for testing the merge queue workflow." \
  --base main \
  --head "$BRANCH_NAME")

echo "✅ Pull request created: $PR_URL"
echo "🔀 Branch: $BRANCH_NAME"
echo "📝 File modified: $FILE_NAME"
echo "🎲 Random value: $RANDOM_VALUE"

# Switch back to main branch
echo "🔄 Switching back to main branch..."
git checkout main
