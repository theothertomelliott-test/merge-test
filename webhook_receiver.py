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
            
            # CRITICAL DEBUG: Log ALL PR webhook events immediately
            print(f"🚨 PR WEBHOOK RECEIVED - PR #{pr_id}, Action: {action}")
            
            # Store PR action
            import datetime
            timestamp = datetime.datetime.now().isoformat()
            
            # Debug: Log all PR webhook events
            print(f"🔍 PR Webhook Event - PR #{pr_id}, Action: {action}, Timestamp: {timestamp}")
            
            # Get existing actions for this PR
            existing_actions = pr_actions.get(pr_id, "[]")
            import json as json_lib
            actions_list = json_lib.loads(existing_actions)
            
            # Simplified: Just use the PR data from webhook payload directly
            print(f"🔍 Processing PR #{pr_id} action: {action}")
            
            # Add new action with simple data extraction
            new_action = {
                "action": action,
                "timestamp": timestamp,
                "title": pr_data.get("title", f"PR #{pr_id}"),
                "state": pr_data.get("state", ""),
                "user": pr_data.get("user", {}).get("login", ""),
                "base_branch": pr_data.get("base", {}).get("ref", ""),
                "head_branch": pr_data.get("head", {}).get("ref", "")
            }
            actions_list.append(new_action)
            
            # Store updated actions
            pr_actions[pr_id] = json_lib.dumps(actions_list)
            
            print(f"🔍 PR #{pr_id} action stored: {action} (Total actions: {len(actions_list)})")
            
            # Store PR data for metrics calculation
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
            # Handle workflow run events
            event_type = "workflow_run"
            workflow_data = payload["workflow_run"]
            action = payload.get("action", "unknown")
            
            # Extract PR information from workflow
            pr_id = None
            
            # Method 1: Direct pull_requests association
            if workflow_data.get("pull_requests"):
                pr_list = workflow_data["pull_requests"]
                if pr_list and len(pr_list) > 0:
                    pr_id = str(pr_list[0]["number"])
            
            # Method 2: Try to match by head branch if no direct PR association
            if not pr_id and workflow_data.get("head_branch"):
                head_branch = workflow_data["head_branch"]
                print(f"🔍 Workflow Debug - Trying head_branch match: {head_branch}")
                
                # Check if it's a merge queue temporary branch
                if "gh-readonly-queue/main/pr-" in head_branch:
                    # Extract PR number from: refs/heads/gh-readonly-queue/main/pr-171-<hash>
                    import re
                    pr_match = re.search(r'gh-readonly-queue/main/pr-(\d+)-', head_branch)
                    if pr_match:
                        pr_id = pr_match.group(1)
                        print(f"🔍 Workflow Debug - Extracted PR {pr_id} from merge queue branch")
                else:
                    # Regular branch matching
                    # Look for PRs that have this head branch in our stored data
                    for stored_pr_id, actions_json in pr_actions.items():
                        try:
                            import json as json_lib
                            actions = json_lib.loads(actions_json)
                            for action in actions:
                                if action.get("head_branch") == head_branch:
                                    pr_id = stored_pr_id
                                    print(f"🔍 Workflow Debug - Matched PR {pr_id} by head_branch {head_branch}")
                                    break
                            if pr_id:
                                break
                        except:
                            continue
            
            print(f"🔍 Workflow Debug - Final PR ID: {pr_id} for workflow {workflow_data.get('name')}")
            
            if pr_id:
                # Store workflow action
                import datetime
                timestamp = datetime.datetime.now().isoformat()
                
                # Get existing actions for this PR
                existing_actions = pr_actions.get(pr_id, "[]")
                import json as json_lib
                actions_list = json_lib.loads(existing_actions)
                
                # Ensure we have PR data - extract from existing actions if missing
                pr_data_json = pr_data_store.get(pr_id, "{}")
                pr_data = json_lib.loads(pr_data_json)
                
                if not pr_data.get("title"):  # If we don't have PR data, extract from existing actions
                    print(f"🔍 Missing PR data for #{pr_id} in workflow, extracting from existing actions...")
                    # For workflow events, create a better title using workflow info
                    workflow_name = workflow_data.get("name", "unknown")
                    pr_title = f"PR #{pr_id} - {workflow_name}"
                    
                    pr_data = {
                        "title": pr_title,
                        "state": "unknown",
                        "user": {"login": "system"},
                        "head": {"ref": workflow_data.get("head_branch", "")},
                        "base": {"ref": "main"}
                    }
                    pr_data_store[pr_id] = json_lib.dumps(pr_data)
                    print(f"🔍 Created PR data for #{pr_id}: {pr_title}")
                
                # Add new workflow action
                # Use workflow run ID from payload if available, otherwise create timestamp-based ID
                workflow_run_id = workflow_data.get("id", f"run_{timestamp.replace(':', '-')}")
                new_action = {
                    "action": f"workflow_{action}_{workflow_run_id}",
                    "timestamp": timestamp,
                    "title": f"Workflow: {workflow_data.get('name', 'unknown')} (ID: {workflow_run_id})",
                    "state": workflow_data.get("status", "unknown"),
                    "user": "system",
                    "base_branch": "",
                    "head_branch": "",
                    "workflow_name": workflow_data.get("name", ""),
                    "workflow_status": workflow_data.get("status", ""),
                    "workflow_conclusion": workflow_data.get("conclusion", ""),
                    "run_id": workflow_run_id
                }
                actions_list.append(new_action)
                
                # Store updated actions (keep all events for testing)
                pr_actions[pr_id] = json_lib.dumps(actions_list)
                
                print(f"🔍 Workflow #{pr_id}: {workflow_data.get('name')} - {action} ({workflow_data.get('status', 'unknown')})")
            else:
                print(f"🔍 Workflow without PR: {workflow_data.get('name')} - {action}")
            
            return {"status": "success", "message": "Workflow run received"}
        elif payload.get("workflow_job"):
            # Handle workflow job events
            event_type = "workflow_job"
            job_data = payload["workflow_job"]
            action = payload.get("action", "unknown")
            
            # Extract PR information from workflow job
            pr_id = None
            if job_data.get("pull_requests"):
                pr_list = job_data["pull_requests"]
                if pr_list and len(pr_list) > 0:
                    pr_id = str(pr_list[0]["number"])
            
            if pr_id:
                # Store workflow job action
                import datetime
                timestamp = datetime.datetime.now().isoformat()
                
                # Get existing actions for this PR
                existing_actions = pr_actions.get(pr_id, "[]")
                import json as json_lib
                actions_list = json_lib.loads(existing_actions)
                
                # Add new workflow job action
                # Use job run ID from payload if available, otherwise create timestamp-based ID
                job_run_id = job_data.get("id", f"run_{timestamp.replace(':', '-')}")
                new_action = {
                    "action": f"job_{action}_{job_run_id}",
                    "timestamp": timestamp,
                    "title": f"Job: {job_data.get('name', 'unknown')} (ID: {job_run_id})",
                    "state": job_data.get("status", "unknown"),
                    "user": "system",
                    "base_branch": "",
                    "head_branch": "",
                    "job_name": job_data.get("name", ""),
                    "job_status": job_data.get("status", ""),
                    "job_conclusion": job_data.get("conclusion", ""),
                    "run_id": job_run_id
                }
                actions_list.append(new_action)
                
                # Store updated actions (keep all events for testing)
                pr_actions[pr_id] = json_lib.dumps(actions_list)
                
                print(f"🔍 Job #{pr_id}: {job_data.get('name')} - {action} ({job_data.get('status', 'unknown')})")
            else:
                print(f"🔍 Job without PR: {job_data.get('name')} - {action}")
            
            return {"status": "success", "message": "Workflow job received"}

        # Handle custom check_evaluation webhook from workflow
        elif payload.get("event_type") == "check_evaluation":
            event_type = "check_evaluation"
            branch_name = payload.get("branch_name", "")
            base_branch = payload.get("base_branch", "main")
            check_content = payload.get("check_content", "")
            check_status = payload.get("check_status", "")
            context = payload.get("context", "")
            commits = payload.get("commits", [])
            pr_number = payload.get("pr_number")
            timestamp = payload.get("timestamp", "")
            
            print(f"🔍 Check Evaluation - Branch: {branch_name}, Status: {check_status}, Commits: {len(commits)}")
            
            # Update build counts with commit information
            current_count = build_counts.get(branch_name, "0")
            new_count = int(current_count) + 1
            build_counts[branch_name] = str(new_count)
            
            # Store additional build information including commits
            build_info = {
                "branch_name": branch_name,
                "base_branch": base_branch,
                "check_content": check_content,
                "check_status": check_status,
                "context": context,
                "commits": commits,
                "pr_number": pr_number,
                "timestamp": timestamp,
                "build_count": new_count
            }
            
            # Store build info with a key that includes the branch and count
            build_key = f"{branch_name}_build_{new_count}"
            import json as json_lib
            build_counts[build_key] = json_lib.dumps(build_info)
            
            print(f"📊 Updated build count for {branch_name}: {new_count} (with {len(commits)} commits)")

        print("Action:", payload.get("action"), "Type:", event_type)
        
        return {"status": "success", "message": f"{event_type} event received"}
        
    except HTTPException as e:
        print(f"❌ Webhook validation failed: {e.detail}")
        raise e
    except Exception as e:
        print(f"❌ Error processing webhook: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

# FastAPI endpoint for receiving workflow webhooks (no signature validation)
@app.function(image=modal.Image.debian_slim().pip_install(["fastapi"]))
@modal.fastapi_endpoint(method="POST", docs=False)
async def workflow_webhook(request: Request):
    """Receive workflow webhooks with commit information"""
    try:
        # Get request body
        body = await request.body()
        
        # Parse JSON payload
        payload = json.loads(body.decode('utf-8'))
        
        print(f"🔍 Workflow Webhook Received: {payload.get('event_type', 'unknown')}")
        
        # Handle check_evaluation webhook from workflow
        if payload.get("event_type") == "check_evaluation":
            branch_name = payload.get("branch_name", "")
            base_branch = payload.get("base_branch", "main")
            check_content = payload.get("check_content", "")
            check_status = payload.get("check_status", "")
            context = payload.get("context", "")
            commits = payload.get("commits", [])
            pr_number = payload.get("pr_number")
            timestamp = payload.get("timestamp", "")
            
            print(f"🔍 Check Evaluation - Branch: {branch_name}, Status: {check_status}, Commits: {len(commits)}")
            
            # Update build counts with commit information
            current_count = build_counts.get(branch_name, "0")
            new_count = int(current_count) + 1
            build_counts[branch_name] = str(new_count)
            
            # Store additional build information including commits
            build_info = {
                "branch_name": branch_name,
                "base_branch": base_branch,
                "check_content": check_content,
                "check_status": check_status,
                "context": context,
                "commits": commits,
                "pr_number": pr_number,
                "timestamp": timestamp,
                "build_count": new_count
            }
            
            # Store build info with a key that includes the branch and count
            build_key = f"{branch_name}_build_{new_count}"
            try:
                build_counts[build_key] = json.dumps(build_info)
                print(f"📊 Successfully stored build info key: {build_key}")
                print(f"📊 Build info content: {json.dumps(build_info, indent=2)}")
            except Exception as e:
                print(f"❌ Failed to store build info: {e}")
                print(f"❌ Build info was: {build_info}")
            
            print(f"📊 Updated build count for {branch_name}: {new_count} (with {len(commits)} commits)")
            print(f"📊 Stored build info key: {build_key}")
            
            return {"status": "success", "message": f"Build count updated for {branch_name}"}
        
        return {"status": "success", "message": "Workflow webhook received"}
        
    except Exception as e:
        print(f"❌ Error processing workflow webhook: {str(e)}")
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
        # Skip build info keys (they contain _build_)
        if "_build_" in branch:
            continue
        lines.append(f"{branch}: {count}")
        
        # Look for build info for this branch
        build_info_key = f"{branch}_build_{count}"
        if build_info_key in build_counts_dict:
            try:
                build_info = json.loads(build_counts_dict[build_info_key])
                commits = build_info.get("commits", [])
                pr_number = build_info.get("pr_number")
                check_status = build_info.get("check_status", "")
                
                if commits:
                    lines.append(f"  └─ PR #{pr_number}")
                    for i, commit in enumerate(commits[:5], 1):  # Show max 5 commits
                        lines.append(f"     {i}. {commit}")
                    if len(commits) > 5:
                        lines.append(f"     ... and {len(commits) - 5} more")
                elif pr_number:
                    lines.append(f"  └─ PR #{pr_number} - {check_status.upper()}")
            except Exception as e:
                print(f"❌ Failed to parse build info for {branch}: {e}")
    
    lines.append("")
    
    # PR actions section
    lines.append("=== PULL REQUEST ACTIONS ===")
    for pr_id, actions_json in sorted_prs:
        import json as json_lib
        try:
            actions = json_lib.loads(actions_json)
            
            # Get PR data for title and metrics calculation
            pr_data_json = pr_data_store.get(pr_id, "{}")
            pr_data = json_lib.loads(pr_data_json)
            pr_title = pr_data.get("title", "Unknown Title")
            
            # Calculate queue metrics for this PR with stored PR data
            queue_metrics = calculate_queue_metrics(actions, pr_data)
            
            # Display PR header with title
            lines.append(f"PR #{pr_id}: {pr_title}")
            
            for action in actions:
                # Handle different action types
                if action['action'].startswith('workflow_') or action['action'].startswith('job_'):
                    # Workflow/job actions
                    if action['action'].startswith('workflow_'):
                        workflow_name = action.get('workflow_name', 'unknown')
                        status = action.get('workflow_status', 'unknown')
                        conclusion = action.get('workflow_conclusion', '')
                        
                        # Skip intermediate workflow stages (queued, in_progress)
                        # Only show completed workflows with success/failure
                        if status not in ['completed'] and conclusion not in ['success', 'failure', 'cancelled', 'timed_out']:
                            continue  # Skip this action, don't display it
                        
                        # Extract action type using multiple methods
                        action_type = "unknown"
                        status = action.get('workflow_status', 'unknown')
                        conclusion = action.get('workflow_conclusion', '')
                        
                        # Method 1: Use workflow_status if available
                        if status == 'queued':
                            action_type = 'requested'
                        elif status == 'in_progress':
                            action_type = 'in_progress'
                        elif status == 'completed':
                            action_type = 'completed'
                        # Method 2: Use conclusion to infer completed status
                        elif conclusion in ['success', 'failure', 'cancelled', 'timed_out']:
                            action_type = 'completed'
                        # Method 3: Parse the malformed action string
                        else:
                            action_str = action['action'].lower()
                            if "'action': 'requested'" in action_str or '"action": "requested"' in action_str or "requested" in action_str:
                                action_type = "requested"
                            elif "'action': 'in_progress'" in action_str or '"action": "in_progress"' in action_str or "in_progress" in action_str:
                                action_type = "in_progress" 
                            elif "'action': 'completed'" in action_str or '"action": "completed"' in action_str or "completed" in action_str:
                                action_type = "completed"
                        
                        # Show workflow with final status
                        final_status = conclusion if conclusion in ['success', 'failure', 'cancelled', 'timed_out'] else status
                        action_line = f"  {action['timestamp']} - workflow_{action_type} by {action['user']} ({final_status})"
                        
                        if conclusion:
                            action_line += f" - {conclusion}"
                        action_line += f") [{workflow_name}]"
                    else:  # job actions
                        job_name = action.get('job_name', 'unknown')
                        status = action.get('job_status', 'unknown')
                        conclusion = action.get('job_conclusion', '')
                        
                        # Extract action type from the malformed action string
                        action_type = "unknown"
                        if "requested" in action['action']:
                            action_type = "requested"
                        elif "in_progress" in action['action']:
                            action_type = "in_progress"
                        elif "completed" in action['action']:
                            action_type = "completed"
                        
                        action_line = f"  {action['timestamp']} - job_{action_type} by {action['user']} ({status}"
                        if conclusion:
                            action_line += f" - {conclusion}"
                        action_line += f") [{job_name}]"
                else:
                    # PR actions
                    action_line = f"  {action['timestamp']} - {action['action']} by {action['user']} ({action['state']})"
                    
                    # Add queue metrics to dequeue action
                    if action['action'] == 'dequeued' and queue_metrics:
                        metrics_text = queue_metrics['queue_duration_formatted']
                        action_line += f" [{metrics_text}, {queue_metrics['result']}]"
                
                lines.append(action_line)
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
    return {"status": "success", "message": "All data cleared"}
