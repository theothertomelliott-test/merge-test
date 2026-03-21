#!/bin/bash

# Script to merge all passing pull requests using the merge queue

set -e

echo "🔍 Checking for passing pull requests..."

# Get list of open pull requests that are mergeable and have all checks passing
PASSING_PRS=$(gh pr list --state open --json number,title,mergeable,statusCheckRollup --jq '
  .[] | 
  select(.mergeable == "MERGEABLE") | 
  select(.statusCheckRollup | all(.conclusion == "SUCCESS")) |
  "\(.number): \(.title)"
')

if [[ -z "$PASSING_PRS" ]]; then
  echo "ℹ️  No passing pull requests found to merge."
  exit 0
fi

echo "✅ Found passing pull requests:"
echo "$PASSING_PRS"
echo

# Ask for confirmation before merging
echo "⚠️  This will add all passing PRs to the merge queue."
read -p "Continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "❌ Cancelled."
  exit 0
fi

# Merge each passing PR
echo "🚀 Adding passing PRs to merge queue..."
while IFS=: read -r pr_number pr_title; do
  echo "📋 Processing PR #$pr_number: $pr_title"
  
  # Add PR to merge queue
  if gh pr merge "$pr_number" --squash; then
    echo "✅ PR #$pr_number added to merge queue"
  else
    echo "❌ Failed to add PR #$pr_number to merge queue"
  fi
  echo
done <<< "$PASSING_PRS"

echo "🎉 All passing PRs have been added to the merge queue!"
