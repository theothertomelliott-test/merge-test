#!/bin/bash

# Script to create 5 test PRs in specific order and merge them all at once

set -e

echo "🚀 Setting up 5 test PRs in order: ok, fail, ok, ok, ok"

# Array of check values in the specified order
declare -a CHECK_VALUES=("ok" "fail" "ok" "ok" "ok")
declare -a PR_URLS=()

# Create each PR
for i in "${!CHECK_VALUES[@]}"; do
  echo ""
  echo "📋 Creating PR $((i+1))/5 with check value: ${CHECK_VALUES[$i]}"
  
  # Ensure we're on main before creating each PR
  git checkout main
  
  # Run create-pr.sh directly (simplified approach)
  echo "🔄 Running create-pr.sh with check value: ${CHECK_VALUES[$i]}"
  
  # Run create-pr.sh and check if it succeeded
  if ./create-pr.sh "${CHECK_VALUES[$i]}"; then
    echo "✅ PR $((i+1)) created successfully"
    # Note: We'll skip URL extraction for now to avoid hanging issues
    PR_URLS[i]="PR-$((i+1))-created"
  else
    echo "❌ Failed to create PR $((i+1))"
    exit 1
  fi
  
  # Small delay to ensure unique timestamps and branch names
  sleep 1
done

echo ""
echo "📊 All 5 PRs created successfully:"
for i in "${!PR_URLS[@]}"; do
  echo "  PR $((i+1)): ${PR_URLS[i]} (${CHECK_VALUES[$i]})"
done

echo ""
echo "🔄 Waiting a moment before merging..."
sleep 5

echo ""
echo "🚀 Adding all PRs to merge queue..."

# Get current open PRs and add them to merge queue
CURRENT_PRS=$(gh pr list --state open --json number | jq -r '.[].number' | sort -n)

if [[ -z "$CURRENT_PRS" ]]; then
  echo "ℹ️  No open PRs found to add to merge queue."
  exit 0
fi

echo "� Found open PRs: $CURRENT_PRS"

# Add each PR to merge queue
echo "$CURRENT_PRS" | while read -r pr_number; do
  echo "📋 Adding PR #$pr_number to merge queue..."
  if gh pr merge "$pr_number" --squash; then
    echo "✅ PR #$pr_number added to merge queue"
  else
    echo "❌ Failed to add PR #$pr_number to merge queue"
  fi
done

echo ""
echo "🎉 All 5 PRs have been created and added to the merge queue!"
echo "📈 PR order: ${CHECK_VALUES[*]}"
echo "🔄 They will be processed in order by the merge queue"
