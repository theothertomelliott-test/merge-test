import modal
import json
from typing import Dict, Any

# Modal app for receiving webhook events
app = modal.App("merge-queue-webhook-receiver")

# Modal Dict to store build counts per branch
build_counts = modal.Dict.from_name("branch-build-counts", create_if_missing=True)

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
