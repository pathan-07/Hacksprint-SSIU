import requests

# Yeh aapke local server ka address hai
WEBHOOK_URL = "http://localhost:8000/webhook/whatsapp"

# Yeh wo data hai jo usually WhatsApp bhejta hai (JSON Payload)
mock_payload = {
    "entry": [
        {
            "changes": [
                {
                    "value": {
                        "messages": [
                            {
                                "from": "919876543210",  # Fake Customer Number
                                "type": "text",
                                "text": {
                                    "body": "Raju ne 500 ka udhar liya"  # Jo test karna hai wo yaha likho
                                },
                            }
                        ]
                    }
                }
            ]
        }
    ]
}

# Server ko request bhejo
try:
    response = requests.post(WEBHOOK_URL, json=mock_payload, timeout=10)
    print(f"Status Code: {response.status_code}")
    print(f"Server Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
    print("Kya server chalu hai? (uvicorn app.main:app --reload)")
