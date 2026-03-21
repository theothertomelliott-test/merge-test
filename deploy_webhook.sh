#!/bin/bash

# Script to deploy the webhook receiver to Modal

set -e

echo "🚀 Deploying webhook receiver to Modal..."

# Check if Modal is installed
if ! command -v modal &> /dev/null; then
    echo "❌ Modal CLI not found. Please install it first:"
    echo "   pip install modal"
    exit 1
fi

# Check if user is logged in to Modal
if ! modal whoami &> /dev/null; then
    echo "❌ Not logged in to Modal. Please run:"
    echo "   modal setup"
    exit 1
fi

# Deploy the app
echo "📦 Deploying webhook receiver..."
modal deploy webhook_receiver.py

# Get the app URL
APP_URL=$(modal app show merge-queue-webhook-receiver --url 2>/dev/null || echo "")
if [[ -z "$APP_URL" ]]; then
    echo "⚠️  Could not automatically get app URL. Please check Modal dashboard."
    APP_URL="https://your-app-name.modal.app"
fi

echo ""
echo "✅ Webhook receiver deployed successfully!"
echo ""
echo "📡 Webhook endpoints:"
echo "   POST: $APP_URL/webhook_endpoint"
echo "   GET  : $APP_URL/view_events"
echo "   DEL  : $APP_URL/clear_events"
echo ""
echo "🔧 To use with GitHub Actions:"
echo "   Add WEBHOOK_URL as a repository secret:"
echo "   $APP_URL/webhook_endpoint"
echo ""
echo "📊 To view events:"
echo "   curl $APP_URL/view_events"
echo ""
echo "🧹 To clear events:"
echo "   curl -X DELETE $APP_URL/clear_events"
