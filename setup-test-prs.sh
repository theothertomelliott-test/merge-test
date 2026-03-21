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
  
  # Run create-pr.sh and capture the output
  CREATE_OUTPUT=$(./create-pr.sh "${CHECK_VALUES[$i]}")
  
  if [[ $? -eq 0 ]]; then
    # Extract PR URL from the output
    PR_URL=$(echo "$CREATE_OUTPUT" | grep "✅ Pull request created:" | cut -d' ' -f4)
    if [[ -n "$PR_URL" ]]; then
      PR_URLS[i]="$PR_URL"
      echo "✅ PR $((i+1)) created: $PR_URL"
    else
      echo "❌ Failed to extract PR URL for PR $((i+1))"
      echo "Output was: $CREATE_OUTPUT"
      exit 1
    fi
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
echo "🚀 Merging all PRs in order..."

# Merge each PR in order
for i in "${!PR_URLS[@]}"; do
  echo ""
  echo "📋 Merging PR $((i+1))/5: ${PR_URLS[i]} (${CHECK_VALUES[$i]})"
  
  # Extract PR number from URL
  PR_NUMBER=$(echo "${PR_URLS[i]}" | grep -o '[0-9]\+' | tail -1)
  
  if gh pr merge "$PR_NUMBER" --squash; then
    echo "✅ PR $((i+1)) added to merge queue"
  else
    echo "❌ Failed to merge PR $((i+1))"
    exit 1
  fi
done

echo ""
echo "🎉 All 5 PRs have been created and added to the merge queue!"
echo "📈 PR order: ${CHECK_VALUES[*]}"
echo "🔄 They will be processed in order by the merge queue"
