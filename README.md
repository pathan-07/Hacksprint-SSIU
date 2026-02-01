# VoiceKhata (Backend)

WhatsApp voice-based *udhaar* manager for kirana shops.

- Backend: FastAPI (Python)
- DB: Supabase (Postgres)
- AI: Google Gemini (audio transcription + intent extraction)
- Interface: WhatsApp Cloud API webhook

## 1) Setup

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env` (copy from `.env.example`) and fill:
- `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
- `GEMINI_API_KEY`

## 2) Create DB tables (Supabase)

Run SQL in Supabase SQL editor:
- [supabase/schema.sql](supabase/schema.sql)

Important:
- For hackathon speed, the SQL includes GRANTs so a publishable/anon key can access the tables.
- For production, remove those GRANTs and use RLS + policies; keep the service role key server-only.

Quick DB smoke test (after you ran the SQL):
```bash
python scripts/smoke_db.py
```

## 3) Run server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:
- `GET http://localhost:8000/health`

Webhook:
- `GET/POST http://localhost:8000/webhook/whatsapp`

## WhatsApp setup (connect your phone)

In test mode, you message the **Cloud API business/test number** from your own WhatsApp.

1) Start the server:
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

2) Start a tunnel (example: ngrok) and copy the HTTPS URL:
```bash
ngrok http 8000
```

3) Meta Developers → WhatsApp → Configuration:
- Callback URL: `https://<public-url>/webhook/whatsapp`
- Verify token: same as `WHATSAPP_VERIFY_TOKEN` in `.env`
- Turn on webhook field: `messages`

4) Meta Developers → WhatsApp → API Setup:
- Add your phone number as a test recipient and complete OTP verification.
- If a `join <code>` message is shown, send that exact message to the test number once.

5) From your WhatsApp app, send a text/voice note to the **test/business number** shown in API Setup.
The bot should reply with a YES/NO confirmation flow.

## Send a test message (no curl)

Avoid pasting tokens into terminal history. This helper reads `WHATSAPP_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID` from `.env`:

```bash
python scripts/send_whatsapp.py template --to 919574896517 --name jaspers_market_plain_text_v1
python scripts/send_whatsapp.py text --to 919574896517 --body "Hello from VoiceKhata demo"
```

## Demo mode (no WhatsApp)

If you can't set up Meta/WhatsApp tokens, you can demo the same voice-first flow using these endpoints:

- `POST /demo/voice?shop_phone=+919999999999` (multipart form-data with `file=@voice.ogg`)
- `POST /demo/text` (JSON body)
- `POST /demo/confirm` (JSON body)

Examples:
```bash
curl -X POST http://127.0.0.1:8000/demo/text \
	-H "Content-Type: application/json" \
	-d '{"shop_phone":"+919999999999","text":"Raju ko 120 udhaar add karo"}'

curl -X POST http://127.0.0.1:8000/demo/confirm \
	-H "Content-Type: application/json" \
	-d '{"pending_id": 1, "decision": "YES"}'
```

Direct voice recording in browser:
- Open `http://127.0.0.1:8000/demo/record` and record/upload from the page.

To run without WhatsApp config, set `ENABLE_WHATSAPP=false` in your `.env`.

## Notes

- The service *never deletes* udhaar entries. Undo is implemented by marking the last entry as `reversed=true`.
- For `add_udhaar` and `undo_last`, the server asks for a **YES/NO confirmation** before writing the final DB change.
- If Gemini confidence < threshold, the server asks the shopkeeper to re-send or clarify.
