import json
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
                                "type": "text",
                                "text": {
                                    "body": "Raju ne 5 packet Parle-G aur 2 bottle Coke udhar liya"
                                },
                            }
                        ]
                    }
                }
            ]
        }
    ]
}

print("Sending inventory request...")
try:
    response = requests.post(WEBHOOK_URL, json=payload, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Body: {response.text}")
except Exception as exc:
    print(f"Error: {exc}")
