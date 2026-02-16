import requests

WEBHOOK_URL = "http://localhost:8000/webhook/whatsapp"

payload = {
    "entry": [
        {
            "changes": [
                {
                    "value": {
                        "messages": [
                            {
                                "from": "919876543210",
                                "type": "image",
                                "image": {
                                    "id": "BILL_IMAGE_123",
                                    "mime_type": "image/jpeg",
                                    "caption": "Aaj ka maal",
                                },
                            }
                        ]
                    }
                }
            ]
        }
    ]
}

print("Sending mock bill image...")
try:
    response = requests.post(WEBHOOK_URL, json=payload, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Body: {response.text}")
except Exception as exc:
    print(f"Error: {exc}")
