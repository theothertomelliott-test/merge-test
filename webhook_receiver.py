import modal
import json
from typing import Dict, Any

# Modal app for receiving webhook events
app = modal.App("merge-queue-webhook-receiver")

# FastAPI endpoint for receiving webhooks
@app.function(image=modal.Image.debian_slim().pip_install(["fastapi"]))
@modal.web_endpoint(method="POST")
def webhook_endpoint(request_data: Dict[str, Any]):
    """Receive webhook events and echo the body"""
    print("📡 Webhook received:")
    print(json.dumps(request_data, indent=2))
    print("-" * 50)
    
    return {
        "status": "success",
        "echo": request_data
    }
