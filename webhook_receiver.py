import modal
import json
import hashlib
import hmac
from typing import Dict, Any
from fastapi import HTTPException, Request, Response

# Modal app for receiving webhook events
app = modal.App("merge-queue-webhook-receiver")

# Modal Dict to store build counts per branch
build_counts = modal.Dict.from_name("branch-build-counts", create_if_missing=True)

# Modal Dict to store pull request actions by PR ID
pr_actions = modal.Dict.from_name("pr-actions", create_if_missing=True)

# Modal Dict to store PR data for metrics calculation
pr_data_store = modal.Dict.from_name("pr-data", create_if_missing=True)

def calculate_queue_metrics(actions_list, pr_data=None):
    """Calculate queue duration and classify result for dequeued PRs.
    
    Args:
        actions_list: List of PR action dictionaries
        pr_data: PR data from webhook payload (optional)
        
    Returns:
        Dictionary with queue metrics or None if not applicable
    """
    if not actions_list:
        return None
        
    # Find enqueue and dequeue actions
    enqueue_action = None
    dequeue_action = None
    
    for action in actions_list:
        if action.get("action") == "enqueued":
            enqueue_action = action
        elif action.get("action") == "dequeued":
            dequeue_action = action
    
    # Calculate metrics only if both actions exist
    if not enqueue_action or not dequeue_action:
        return None
    
    try:
        # Parse timestamps
        from datetime import datetime
        enqueue_time = datetime.fromisoformat(enqueue_action["timestamp"])
        dequeue_time = datetime.fromisoformat(dequeue_action["timestamp"])
        
        # Calculate duration between enqueue and dequeue
        queue_duration_seconds = (dequeue_time - enqueue_time).total_seconds()
        
        # Classify result based on PR state at dequeue
        state_at_dequeue = dequeue_action.get("state", "unknown")
        if state_at_dequeue == "closed":
            result = "success"
        elif state_at_dequeue == "open":
            result = "failure"
        else:
            result = "unknown"
        
        return {
            "queue_duration_seconds": round(queue_duration_seconds, 2),
            "queue_duration_formatted": f"{queue_duration_seconds:.1f}s",
            "result": result,
            "state_at_dequeue": state_at_dequeue
        }
        
    except Exception as e:
        print(f"Error calculating queue metrics: {e}")
        return None

# Modal Secret for GitHub webhook validation
webhook_secret = modal.Secret.from_name("github-app")

def verify_signature(payload_body: bytes, secret_token: str, signature_header: str):
    """Verify that the payload was sent from GitHub by validating SHA256.

    Raise and return 403 if not authorized.

    Args:
        payload_body: original request body to verify (request.body())
        secret_token: GitHub app webhook token (WEBHOOK_SECRET)
        signature_header: header received from GitHub (x-hub-signature-256)
    """
    if not signature_header:
        raise HTTPException(status_code=403, detail="x-hub-signature-256 header is missing!")
    hash_object = hmac.new(secret_token.encode('utf-8'), msg=payload_body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + hash_object.hexdigest()
    if not hmac.compare_digest(expected_signature, signature_header):
        raise HTTPException(status_code=403, detail="Request signatures didn't match!")

# FastAPI endpoint for receiving webhooks
@app.function(image=modal.Image.debian_slim().pip_install(["fastapi"]), max_containers=1, secrets=[webhook_secret])
@modal.fastapi_endpoint(method="POST")
async def github_webhook(request: Request):
    """Receive GitHub webhooks with signature validation"""
    try:
        # Get signature from header
        signature_header = request.headers.get("x-hub-signature-256")
        
        # Get raw request body (await the coroutine)
        body = await request.body()
        
        # Get secret from Modal secrets environment variable
        import os
        secret_token = os.environ["WEBHOOK_SECRET"]
        
        # Verify signature
        verify_signature(body, secret_token, signature_header)
        
        # Parse JSON payload
        payload = json.loads(body.decode('utf-8'))
        
        event_type = "Unknown"
        if payload.get("pull_request"):
            event_type = "pull_request"
            pr_data = payload["pull_request"]
            pr_id = str(pr_data["number"])
            action = payload.get("action", "unknown")
            
            # Store PR action
            import datetime
            timestamp = datetime.datetime.now().isoformat()
            
            # Get existing actions for this PR
            existing_actions = pr_actions.get(pr_id, "[]")
            import json as json_lib
            actions_list = json_lib.loads(existing_actions)
            
            # Add new action
            new_action = {
                "action": action,
                "timestamp": timestamp,
                "title": pr_data.get("title", ""),
                "state": pr_data.get("state", ""),
                "user": pr_data.get("user", {}).get("login", ""),
                "base_branch": pr_data.get("base", {}).get("ref", ""),
                "head_branch": pr_data.get("head", {}).get("ref", "")
            }
            actions_list.append(new_action)
            
            # Store updated actions (keep only last 10 actions per PR)
            if len(actions_list) > 10:
                actions_list = actions_list[-10:]
            
            pr_actions[pr_id] = json_lib.dumps(actions_list)
            
            # Store PR data for metrics calculation (update on each webhook event)
            pr_data_store[pr_id] = json_lib.dumps(pr_data)
            
            print(f"🔍 PR #{pr_id} action: {action}")
            
            # Calculate queue metrics for this PR with stored PR data
            queue_metrics = calculate_queue_metrics(actions_list, pr_data)
            
            # Debug logging for dequeued PRs
            if any(action['action'] == 'dequeued' for action in actions):
                print(f"🔍 GET Debug PR #{pr_id}:")
                print(f"  Actions count: {len(actions)}")
                print(f"  PR data available: {bool(pr_data)}")
                print(f"  Queue metrics: {queue_metrics}")
                
                # Look for timing data in the webhook payload
                print("🔍 Looking for timing data in payload:")
                for key in ["queued_at", "enqueued_at", "merge_queue_entry", "reason"]:
                    if key in payload:
                        print(f"  {key}: {payload[key]}")
                
                # Check PR data for timing fields
                print("🔍 PR data timing fields:")
                for key in ["created_at", "updated_at", "merged_at", "closed_at"]:
                    if key in pr_data:
                        print(f"  {key}: {pr_data[key]}")
            
        elif payload.get("workflow_run"):
            # Ignore workflow run events
            event_type = "workflow_run"
            return {"status": "success", "message": "Workflow run received"}
        elif payload.get("workflow_job"):
            # Ignore workflow job events
            event_type = "workflow_job"
            return {"status": "success", "message": "Workflow job received"}

        print("Action:", payload.get("action"), "Type:", event_type)
        
        return {"status": "success", "message": "GitHub webhook received and verified"}
        
    except HTTPException as e:
        print(f"❌ Webhook validation failed: {e.detail}")
        raise e
    except Exception as e:
        print(f"❌ Error processing webhook: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

# FastAPI endpoint for receiving webhooks
@app.function(image=modal.Image.debian_slim().pip_install(["fastapi"]), max_containers=1)
@modal.fastapi_endpoint(method="POST")
def webhook_endpoint(request_data: Dict[str, Any]):
    """Receive webhook events and echo the body"""
    print("📡 Webhook received:")
    print(f"Raw request type: {type(request_data)}")
    print(f"Raw request: {request_data}")
    
    # Handle different request formats
    if isinstance(request_data, dict):
        print("✅ Request is a dictionary")
        print(json.dumps(request_data, indent=2))
        
        # Update build count for this branch
        # Note: Modal Dict doesn't have built-in atomic operations, so there's a small race condition risk
        # For high-concurrency scenarios, consider using a database with proper transactions
        branch_name = request_data.get("branch_name", "unknown")
        build_counts[branch_name] = build_counts.get(branch_name, 0) + 1
        new_count = build_counts[branch_name]
        
        print(f"📊 Branch '{branch_name}' build count: {new_count}")
        
        # Print all build counts
        print("📈 All branch build counts:")
        for branch, count in build_counts.items():
            print(f"   {branch}: {count}")
            
    else:
        print(f"⚠️  Unexpected request format: {type(request_data)}")
        try:
            # Try to parse as JSON string
            if isinstance(request_data, str):
                parsed = json.loads(request_data)
                print("✅ Parsed as JSON:")
                print(json.dumps(parsed, indent=2))
                request_data = parsed
        except Exception as e:
            print(f"❌ Failed to parse as JSON: {e}")
    
    print("-" * 50)
    
    return {
        "status": "success",
        "echo": request_data,
        "received_type": str(type(request_data)),
        "build_counts": dict(build_counts.items())
    }

# Endpoint to view build counts
@app.function(image=modal.Image.debian_slim().pip_install(["fastapi"]))
@modal.fastapi_endpoint(method="GET", docs=False)
def get_build_counts():
    """Get all build counts and PR actions"""
    from fastapi import Response
    
    # Get build counts
    build_counts_dict = dict(build_counts.items())
    sorted_builds = sorted(build_counts_dict.items())
    
    # Get PR actions
    pr_actions_dict = dict(pr_actions.items())
    sorted_prs = sorted(pr_actions_dict.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0])
    
    lines = []
    
    # Build counts section
    lines.append("=== BUILD COUNTS ===")
    for branch, count in sorted_builds:
        lines.append(f"{branch}: {count}")
    
    lines.append("")
    
    # PR actions section
    lines.append("=== PULL REQUEST ACTIONS ===")
    for pr_id, actions_json in sorted_prs:
        import json as json_lib
        try:
            actions = json_lib.loads(actions_json)
            lines.append(f"PR #{pr_id}:")
            
            # Get PR data for metrics calculation
            pr_data_json = pr_data_store.get(pr_id, "{}")
            pr_data = json_lib.loads(pr_data_json)
            
            # Calculate queue metrics for this PR with stored PR data
            queue_metrics = calculate_queue_metrics(actions, pr_data)
            
            for action in actions:
                action_line = f"  {action['timestamp']} - {action['action']} by {action['user']} ({action['state']})"
                
                # Add queue metrics to dequeue action
                if action['action'] == 'dequeued' and queue_metrics:
                    metrics_text = queue_metrics['queue_duration_formatted']
                    action_line += f" [{metrics_text}, {queue_metrics['result']}]"
                
                lines.append(action_line)
                lines.append(f"    Title: {action['title']}")
                lines.append(f"    Branches: {action['head_branch']} -> {action['base_branch']}")
            lines.append("")
        except:
            lines.append(f"PR #{pr_id}: [Invalid data]")
            lines.append("")
    
    content = "\n".join(lines)
    return Response(content=content, media_type="text/plain")

# Endpoint to clear build counts
@app.function(image=modal.Image.debian_slim().pip_install(["fastapi"]))
@modal.fastapi_endpoint(method="DELETE")
def clear_build_counts():
    """Clear all build counts and PR actions"""
    build_counts.clear()
    pr_actions.clear()
    pr_data_store.clear()
    return {
        "status": "success",
        "message": "All build counts and PR actions cleared"
    }
