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
FILE_NAME="check.txt"
BRANCH_NAME="test-branch-$(date +%s)"

# Parse command line argument for check setting
if [[ $# -eq 0 ]]; then
  CHECK_VALUE="ok"
  echo "ℹ️  No check value provided, using default: ok"
else
  INPUT_VALUE="$1"
  
  # Validate merge_fail
  if [[ "$INPUT_VALUE" == "merge_fail" ]]; then
    CHECK_VALUE="$INPUT_VALUE"
    echo "🔄 Will use merge_fail - passes individually, fails in merge queue"
  # Validate percentage format (number + %)
  elif [[ "$INPUT_VALUE" =~ ^([0-9]+)%$ ]]; then
    PERCENTAGE="${BASH_REMATCH[1]}"
    
    # Validate percentage range
    if [[ $PERCENTAGE -lt 0 || $PERCENTAGE -gt 100 ]]; then
      echo "❌ Error: Percentage must be between 0 and 100"
      echo "   Provided: $PERCENTAGE%"
      exit 1
    fi
    
    CHECK_VALUE="$INPUT_VALUE"
    echo "🎲 Will use percentage $INPUT_VALUE during workflow run"
    
  # Validate duration format (number + unit)
  elif [[ "$INPUT_VALUE" =~ ^([0-9]+)([smhd])$ ]]; then
    DURATION_NUM="${BASH_REMATCH[1]}"
    DURATION_UNIT="${BASH_REMATCH[2]}"
    CURRENT_TIME=$(date +%s)
    
    # Convert duration to seconds
    case "$DURATION_UNIT" in
      "s") SECONDS_OFFSET=$DURATION_NUM ;;
      "m") SECONDS_OFFSET=$((DURATION_NUM * 60)) ;;
      "h") SECONDS_OFFSET=$((DURATION_NUM * 3600)) ;;
      "d") SECONDS_OFFSET=$((DURATION_NUM * 86400)) ;;
    esac
    
    CHECK_VALUE=$((CURRENT_TIME + SECONDS_OFFSET))
    echo "⏰ Duration $INPUT_VALUE converted to timestamp $CHECK_VALUE"
  else
    CHECK_VALUE="$INPUT_VALUE"
  fi
fi

# Validate check value
case "$CHECK_VALUE" in
  "ok"|"fail")
    ;;
  [0-9]*)
    # Timestamp validation - check if it's a reasonable future timestamp
    CURRENT_TIME=$(date +%s)
    if [[ $CHECK_VALUE -lt $CURRENT_TIME ]]; then
      echo "❌ Error: Timestamp $CHECK_VALUE is in the past"
      echo "   Current time: $CURRENT_TIME"
      exit 1
    fi
    # Check if timestamp is too far in the future (more than 1 year)
    if [[ $CHECK_VALUE -gt $((CURRENT_TIME + 31536000)) ]]; then
      echo "❌ Error: Timestamp $CHECK_VALUE is too far in the future"
      echo "   Maximum: 1 year from now"
      exit 1
    fi
    ;;
  *)
    echo "❌ Error: Invalid check value '$INPUT_VALUE'"
    echo "   Valid values: 'ok', 'fail', 'merge_fail', Unix timestamp, duration (e.g., 5m, 2h, 1d), or percentage (e.g., 20%)"
    exit 1
    ;;
esac

echo "Creating test branch and pull request..."
echo "Branch: $BRANCH_NAME"
echo "Check value: $CHECK_VALUE"

# Create and switch to new branch (force to ignore script changes)
git checkout --force -b "$BRANCH_NAME"

# Create or modify the check file with the specified value
echo "$CHECK_VALUE" > "$FILE_NAME"
echo "📝 Created $FILE_NAME with content: $CHECK_VALUE"

# Force add the file and ensure it's always committed
git add "$FILE_NAME"

# Always commit the check.txt file, even if unchanged
# This ensures each PR has a clean check.txt state
if git diff --cached --quiet; then
  echo "ℹ️  No changes to $FILE_NAME, but forcing commit..."
  git commit --allow-empty -m "Set check to $CHECK_VALUE"
else
  git commit -m "Set check to $CHECK_VALUE"
fi

# Push branch to origin
git push -u origin "$BRANCH_NAME"

# Create pull request using gh CLI
echo "Creating pull request..."
PR_URL=$(gh pr create \
  --title "Test PR with check set to $CHECK_VALUE" \
  --body "This is an automated test PR that sets check.txt to '$CHECK_VALUE'.

**Changes:**
- Set check.txt to: $CHECK_VALUE
- Branch: $BRANCH_NAME

This PR is for testing the merge queue workflow with check behavior control." \
  --base main \
  --head "$BRANCH_NAME")

echo "✅ Pull request created: $PR_URL"
echo "🔀 Branch: $BRANCH_NAME"
echo "📝 File modified: $FILE_NAME"
echo "�️  Check value: $CHECK_VALUE"

# Switch back to main branch
echo "🔄 Switching back to main branch..."
git checkout main
