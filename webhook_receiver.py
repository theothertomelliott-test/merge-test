import modal
import json
from typing import Dict, Any

# Modal app for receiving webhook events
app = modal.App("merge-queue-webhook-receiver")

# FastAPI endpoint for receiving webhooks
@app.function(image=modal.Image.debian_slim().pip_install(["fastapi"]))
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
        "received_type": str(type(request_data))
    }
