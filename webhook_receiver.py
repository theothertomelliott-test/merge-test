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
        
        print("✅ GitHub webhook signature verified")
        print("📡 GitHub webhook received:")
        type = "Unknown"
        if payload.get("action"):
            type = payload.get("action")
        if payload.get("pull_request"):
            type = "pull_request"
        if payload.get("workflow_run"):
            type = "workflow_run"
        if payload.get("workflow_job"):
            type = "workflow_job"

        print("Action:", payload.get("action"), "Type:", type)
        print(json.dumps(payload, indent=2))
        
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
    """Get all build counts"""
    from fastapi import Response
    
    counts_dict = dict(build_counts.items())
    
    # Sort by branch name and create line-by-line output
    sorted_branches = sorted(counts_dict.items())
    
    lines = []
    
    for branch, count in sorted_branches:
        lines.append(f"{branch}: {count}")
    
    content = "\n".join(lines)
    return Response(content=content, media_type="text/plain")

# Endpoint to clear build counts
@app.function(image=modal.Image.debian_slim().pip_install(["fastapi"]))
@modal.fastapi_endpoint(method="DELETE")
def clear_build_counts():
    """Clear all build counts"""
    build_counts.clear()
    return {
        "status": "success",
        "message": "All build counts cleared"
    }
