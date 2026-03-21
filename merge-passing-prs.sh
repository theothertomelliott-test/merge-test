#!/bin/bash

# Script to merge all passing pull requests using the merge queue

set -e

# Check if we're on main branch
CURRENT_BRANCH=$(git branch --show-current)
if [[ "$CURRENT_BRANCH" != "main" ]]; then
  echo "❌ Error: You must be on the main branch to run this script."
  echo "   Current branch: $CURRENT_BRANCH"
  echo "   Run: git checkout main"
  exit 1
fi

# Check for uncommitted changes (but allow script files to be modified)
if [[ -n $(git status --porcelain | grep -v -E "(create-pr\.sh|setup-test-prs\.sh|merge-passing-prs\.sh)") ]]; then
  echo "❌ Error: You have uncommitted changes. Please commit or stash them first."
  git status --short | grep -v -E "(create-pr\.sh|setup-test-prs\.sh|merge-passing-prs\.sh)"
  exit 1
fi

# Check if script files are the only uncommitted changes
SCRIPT_CHANGES=$(git status --porcelain | grep -E "(create-pr\.sh|setup-test-prs\.sh|merge-passing-prs\.sh)")
if [[ -n "$SCRIPT_CHANGES" ]]; then
  echo "ℹ️  Script files have uncommitted changes, proceeding anyway..."
  echo "$SCRIPT_CHANGES"
fi

echo "✅ Repository state validated"

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
