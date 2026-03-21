# Webhook Event Logging for Merge Queue Testing

This setup allows you to log all check evaluation events from the merge queue testing workflow to a Modal app for real-time monitoring and debugging.

## Features

- 📡 **Real-time event logging** - Every check evaluation is logged with full context
- 🔍 **Branch-specific tracking** - Filter events by branch name
- 📊 **Event history** - View complete history of all check evaluations
- 🔄 **Context awareness** - Distinguishes between individual PR and merge group contexts
- 🧹 **Event management** - Clear events when needed for fresh testing

## Setup Instructions

### 1. Deploy the Webhook Receiver

```bash
# Install dependencies
pip install modal fastapi pydantic

# Deploy to Modal
./deploy_webhook.sh
```

### 2. Configure GitHub Actions

1. Go to your GitHub repository settings
2. Navigate to **Secrets and variables > Actions**
3. Add a new repository secret:
   - **Name**: `WEBHOOK_URL`
   - **Value**: The webhook URL from the deployment output (e.g., `https://your-app-name.modal.app/webhook_endpoint`)

### 3. Test the Setup

```bash
# Create a test PR to trigger webhook events
./create-pr.sh ok

# View logged events
curl https://your-app-name.modal.app/view_events
```

## Webhook Event Format

Each event includes:

```json
{
  "event_type": "check_evaluation",
  "branch_name": "test-branch-1234567890",
  "check_content": "merge_fail",
  "check_status": "pass",
  "context": "individual",
  "timestamp": "2024-03-21T17:30:00Z",
  "repository": "username/repo",
  "commit_sha": "abc123def456",
  "pr_number": 123,
  "additional_info": {
    "workflow_run_id": "456789",
    "github_event": "pull_request",
    "actor": "username"
  }
}
```

## API Endpoints

### POST `/webhook_endpoint`
Receives webhook events from GitHub Actions.

### GET `/view_events`
Returns all logged events.

```bash
curl https://your-app-name.modal.app/view_events
```

### DELETE `/clear_events`
Clears all logged events.

```bash
curl -X DELETE https://your-app-name.modal.app/clear_events
```

## Event Contexts

- **`individual`** - Check running on an individual PR
- **`merge_group`** - Check running as part of a merge group

## Check Types and Behaviors

| Check Type | Individual Context | Merge Group Context |
|------------|-------------------|-------------------|
| `ok` | ✅ Pass | ✅ Pass |
| `fail` | ❌ Fail | ❌ Fail |
| `merge_fail` | ✅ Pass | ❌ Fail |
| `20%` | 🎲 Random (20% pass) | 🎲 Random (20% pass) |
| `5m` | ⏰ Time-based | ⏰ Time-based |
| `timestamp` | ⏰ Time-based | ⏰ Time-based |

## Monitoring Use Cases

### Track Merge Failures
```bash
# View all merge_fail events
curl https://your-app-name.modal.app/view_events | \
  jq '.events[] | select(.check_content == "merge_fail")'
```

### Monitor Branch Activity
```bash
# View events for specific branch
curl https://your-app-name.modal.app/view_events | \
  jq '.events[] | select(.branch_name == "test-branch-1234567890")'
```

### Debug Merge Queue Issues
```bash
# View all merge group events
curl https://your-app-name.modal.app/view_events | \
  jq '.events[] | select(.context == "merge_group")'
```

## Local Development

For local testing without Modal:

```python
# Simple local webhook server
from flask import Flask, request, jsonify
import json

app = Flask(__name__)
events = []

@app.route('/webhook_endpoint', methods=['POST'])
def webhook():
    event = request.json
    events.append(event)
    print(f"📡 Event received: {event}")
    return jsonify({"status": "success"})

@app.route('/view_events', methods=['GET'])
def view_events():
    return jsonify({"events": events})

if __name__ == '__main__':
    app.run(port=5000)
```

Then use `http://localhost:5000/webhook_endpoint` as your WEBHOOK_URL.

## Troubleshooting

### Webhook Not Triggering
- Ensure `WEBHOOK_URL` secret is set correctly
- Check that the workflow is running (GitHub Actions tab)
- Verify the Modal app is deployed and accessible

### Events Not Appearing
- Check the GitHub Actions logs for webhook step output
- Verify the Modal app logs in the Modal dashboard
- Test the webhook endpoint manually:
  ```bash
  curl -X POST https://your-app-name.modal.app/webhook_endpoint \
    -H "Content-Type: application/json" \
    -d '{"test": "event"}'
  ```

### Modal Deployment Issues
- Ensure you're logged in: `modal whoami`
- Check Modal account status and billing
- Verify app name uniqueness

## Production Considerations

For production use, consider:
- Adding authentication to webhook endpoints
- Using a database instead of in-memory storage
- Implementing event retention policies
- Adding monitoring and alerting
- Error handling and retry logic
