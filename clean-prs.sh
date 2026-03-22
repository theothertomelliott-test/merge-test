#!/bin/bash

# Script to close all outstanding PRs in bulk

set -e

echo "🧹 Cleaning up outstanding pull requests..."

# Check if there are any open PRs
OPEN_PRS=$(gh pr list --state open --json number | jq -r '.[].number' 2>/dev/null)

if [[ -z "$OPEN_PRS" ]]; then
  echo "ℹ️  No open pull requests found."
  echo ""
  echo "🧹 Clearing webhook receiver state..."
  WEBHOOK_CLEAR_URL="https://theothertomelliott--merge-queue-webhook-receiver-clear-b-91cdf4.modal.run"

  if curl -X DELETE "$WEBHOOK_CLEAR_URL" >/dev/null 2>&1; then
    echo "✅ Webhook receiver state cleared"
  else
    echo "⚠️  Failed to clear webhook receiver state (may be unavailable)"
  fi

  echo ""
  echo "🎯 Cleanup complete!"
  exit 0
fi

# Count open PRs
PR_COUNT=$(echo "$OPEN_PRS" | wc -l | tr -d ' ')
echo "📊 Found $PR_COUNT open pull request(s):"

# List the PRs that will be closed
gh pr list --state open --json number,title | jq -r '.[] | "- #\(.number): \(.title)"'

# Ask for confirmation
echo ""
read -p "⚠️  This will close all $PR_COUNT open PRs. Continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "❌ Cancelled."
  exit 0
fi

# Close all PRs
echo ""
echo "🚀 Closing all open PRs..."
echo "$OPEN_PRS" | while read -r pr_number; do
  echo "📋 Closing PR #$pr_number..."
  if gh pr close "$pr_number" --comment "Automated cleanup - closing test PRs" 2>/dev/null; then
    echo "✅ PR #$pr_number closed"
  else
    echo "❌ Failed to close PR #$pr_number (may already be merged/closed)"
  fi
done

echo ""
echo "🎉 Cleanup completed!"
echo "📈 All open PRs have been closed."

# Clear webhook receiver state
echo ""
echo "🧹 Clearing webhook receiver state..."
WEBHOOK_CLEAR_URL="https://theothertomelliott--merge-queue-webhook-receiver-clear-b-91cdf4.modal.run"

if curl -X DELETE "$WEBHOOK_CLEAR_URL" >/dev/null 2>&1; then
  echo "✅ Webhook receiver state cleared"
else
  echo "⚠️  Failed to clear webhook receiver state (may be unavailable)"
fi

echo ""
echo "🎯 Full cleanup complete!"
