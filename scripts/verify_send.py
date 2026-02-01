import asyncio
import sys
import os
import json
import httpx
from dotenv import load_dotenv

# Load env from parent directory
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

async def test_send(to_phone):
    token = os.getenv("WHATSAPP_TOKEN")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    
    if not token or not phone_id:
        print("ERROR: Missing WHATSAPP_TOKEN or WHATSAPP_PHONE_NUMBER_ID in .env")
        return

    url = f"https://graph.facebook.com/v22.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": "Test message from VoiceKhata debugger"},
    }

    print(f"Sending to: {to_phone}")
    print(f"Using Phone ID: {phone_id}")
    print("Sending request...")
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload)
        print(f"Status Code: {resp.status_code}")
        print("Response Body:")
        try:
            print(json.dumps(resp.json(), indent=2))
        except:
            print(resp.text)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/verify_send.py <PHONE_NUMBER_WITH_COUNTRY_CODE>")
        print("Example: python scripts/verify_send.py 919876543210")
        sys.exit(1)
    
    asyncio.run(test_send(sys.argv[1]))
