from __future__ import annotations

import datetime as dt
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .db import (
    create_pending_action,
    expire_pending_actions,
    get_or_create_customer,
    get_pending_action,
    get_recent_entries,
    get_summary,
    insert_udhaar_entry,
    set_pending_action_status,
    undo_last_entry,
)
from .gemini_ai import extract_intent, transcribe_audio
from .settings import settings
from .types import Intent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("/record", response_class=HTMLResponse)
def demo_record_page() -> HTMLResponse:
    """A tiny in-server page to record voice and hit the demo APIs.

    WHY: Lets you demo 'voice input' end-to-end without WhatsApp/Meta setup.
    """

    html = """<!doctype html>
<html lang=\"en\">
    <head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
        <title>VoiceKhata Demo Recorder</title>
        <style>
            body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 24px; }
            .row { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
            button { padding: 10px 14px; border-radius: 10px; border: 1px solid #ddd; cursor: pointer; }
            button:disabled { opacity: 0.6; cursor: not-allowed; }
            input { padding: 10px 12px; border-radius: 10px; border: 1px solid #ddd; min-width: 260px; }
            pre { background: #0b1020; color: #e7e9ee; padding: 14px; border-radius: 12px; overflow: auto; }
            .hint { color: #555; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border-bottom: 1px solid #eee; padding: 8px 10px; text-align: left; font-size: 14px; }
            th { background: #fafafa; position: sticky; top: 0; }
            .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; border: 1px solid #ddd; }
            .rev { background: #fff4f4; }
        </style>
    </head>
    <body>
        <h2>VoiceKhata: Direct Voice Recording (Demo)</h2>
        <div class=\"hint\" style=\"margin-top:-8px; margin-bottom:10px;\">Recorder build: 2026-01-14 (no-cache)</div>
        <p class=\"hint\">Record a voice note here, we send it to <code>/demo/voice</code>, get intent + confirmation, then you can confirm to commit.</p>

        <div id=\"banner\" class=\"hint\" style=\"padding:10px 12px; border:1px solid #eee; border-radius:12px; background:#fafafa; margin: 12px 0; white-space: pre-line;\">Loading checks...</div>

        <div class=\"row\">
            <label>Shop phone:</label>
            <input id=\"shopPhone\" value=\"+919999999999\" />
            <button id=\"btnStart\">Start Recording</button>
            <button id=\"btnStop\" disabled>Stop & Upload</button>
            <button id=\"btnDiag\" type=\"button\">Diagnostics</button>
        </div>

        <div style=\"height: 12px\"></div>
        <div class=\"row\">
            <label>Pending ID:</label>
            <input id=\"pendingId\" placeholder=\"(auto)\" />
            <button id=\"btnYes\" disabled>YES (Commit)</button>
            <button id=\"btnNo\" disabled>NO (Cancel)</button>
        </div>

        <h3>Result</h3>
        <pre id=\"out\">Ready.</pre>

        <h3>Live ledger (auto refresh)</h3>
        <div class=\"hint\">Shows latest entries for this shop phone. Updates every 2 seconds.</div>
        <div style=\"height: 8px\"></div>
        <div style=\"max-height: 320px; overflow:auto; border: 1px solid #eee; border-radius: 12px;\">
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Customer</th>
                        <th>Amount</th>
                        <th>Status</th>
                        <th>When</th>
                    </tr>
                </thead>
                <tbody id=\"ledgerBody\"></tbody>
            </table>
        </div>

        <script>
            const out = document.getElementById('out');
            const banner = document.getElementById('banner');
            const shopPhone = document.getElementById('shopPhone');
            const pendingId = document.getElementById('pendingId');
            const btnStart = document.getElementById('btnStart');
            const btnStop = document.getElementById('btnStop');
            const btnYes = document.getElementById('btnYes');
            const btnNo = document.getElementById('btnNo');
            const btnDiag = document.getElementById('btnDiag');
            const ledgerBody = document.getElementById('ledgerBody');

            let mediaRecorder;
            let chunks = [];

            function log(obj) {
                out.textContent = typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2);
            }

            // Surface JS errors directly in the UI (helps when DevTools aren't available).
            window.addEventListener('error', (e) => {
                log({ error: 'window.error', message: String(e.message || e), source: e.filename, line: e.lineno });
            });
            window.addEventListener('unhandledrejection', (e) => {
                log({ error: 'unhandledrejection', message: String(e.reason || e) });
            });

            function showDiagnostics() {
                const diag = {
                    isSecureContext: (typeof isSecureContext !== 'undefined') ? isSecureContext : null,
                    userAgent: navigator.userAgent,
                    hasMediaDevices: !!(navigator.mediaDevices),
                    hasGetUserMedia: !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia),
                    hasMediaRecorder: (typeof MediaRecorder !== 'undefined'),
                    note: 'If hasMediaRecorder=false or hasGetUserMedia=false, open this page in Chrome/Edge (not VS Code Simple Browser).'
                };
                log(diag);
            }

            function updateBanner() {
                const secure = (typeof isSecureContext !== 'undefined') ? isSecureContext : true;
                const hasGUM = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
                const hasMR = (typeof MediaRecorder !== 'undefined');

                const lines = [];
                lines.push('Status checks:');
                lines.push(`- secure context: ${secure}`);
                lines.push(`- getUserMedia available: ${hasGUM}`);
                lines.push(`- MediaRecorder available: ${hasMR}`);
                if (!secure) {
                    lines.push('Fix: open http://localhost:8000/demo/record (or use https).');
                }
                if (!hasGUM || !hasMR) {
                    lines.push('Fix: open in Chrome/Edge (not VS Code Simple Browser).');
                }
                banner.textContent = lines.join('\\n');
            }

            function friendlyMicError(e) {
                const msg = String(e && (e.name || e.message) ? (e.name + ': ' + e.message) : e);
                // Common cases:
                // - NotAllowedError: user denied mic
                // - NotFoundError: no microphone device
                if (msg.includes('NotAllowedError')) {
                    return {
                        error: msg,
                        help: [
                            'Microphone permission denied.',
                            'If you opened this inside VS Code Simple Browser, mic access is usually blocked. Open in Chrome/Edge instead:',
                            '  http://127.0.0.1:8000/demo/record',
                            'Then click the lock icon → Site permissions → Microphone → Allow.',
                            'Windows check: Settings → Privacy & security → Microphone → allow access for your browser + "Let desktop apps access your microphone".'
                        ].join('\\n')
                    };
                }
                if (msg.includes('NotFoundError')) {
                    return {
                        error: msg,
                        help: 'No microphone device found. Plug in a mic/headset and try again.'
                    };
                }
                return { error: msg };
            }

            function setConfirmEnabled(enabled) {
                btnYes.disabled = !enabled;
                btnNo.disabled = !enabled;
            }

            function renderLedger(rows) {
                ledgerBody.innerHTML = '';
                if (!rows || rows.length === 0) {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `<td colspan=\"5\" class=\"hint\">No entries yet.</td>`;
                    ledgerBody.appendChild(tr);
                    return;
                }

                for (const r of rows) {
                    const tr = document.createElement('tr');
                    if (r.reversed) tr.className = 'rev';
                    const status = r.reversed ? '<span class=\"badge\">reversed</span>' : '<span class=\"badge\">active</span>';
                    const when = (r.created_at || '').replace('T',' ').replace('+00:00','Z');
                    tr.innerHTML = `
                        <td>${r.id}</td>
                        <td>${(r.customer_name || '')}</td>
                        <td>₹${Number(r.amount).toFixed(0)}</td>
                        <td>${status}</td>
                        <td>${when}</td>
                    `;
                    ledgerBody.appendChild(tr);
                }
            }

            async function refreshLedger() {
                try {
                    const url = `/demo/entries?shop_phone=${encodeURIComponent(shopPhone.value)}&limit=25`;
                    const resp = await fetch(url);
                    const data = await resp.json();
                    renderLedger(data.entries || []);
                } catch (e) {
                    // Non-blocking
                }
            }

            async function startRecording() {
                chunks = [];
                setConfirmEnabled(false);
                pendingId.value = '';

                if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                    throw new Error('getUserMedia not available in this browser. Open in Chrome/Edge.');
                }
                if (typeof MediaRecorder === 'undefined') {
                    throw new Error('MediaRecorder not available in this browser. Open in Chrome/Edge.');
                }

                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

                // Try common mime types; browser support varies.
                const preferred = [
                    'audio/webm;codecs=opus',
                    'audio/webm',
                    'audio/ogg;codecs=opus',
                    'audio/ogg'
                ];
                let mimeType = '';
                for (const mt of preferred) {
                    if (MediaRecorder.isTypeSupported(mt)) { mimeType = mt; break; }
                }

                mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
                mediaRecorder.ondataavailable = (e) => { if (e.data && e.data.size > 0) chunks.push(e.data); };
                mediaRecorder.onstop = () => { stream.getTracks().forEach(t => t.stop()); };
                mediaRecorder.start();

                btnStart.disabled = true;
                btnStop.disabled = false;
                log('Recording... speak Hindi/Hinglish like: "Raju ko 120 udhaar"');
            }

            async function stopAndUpload() {
                btnStop.disabled = true;
                log('Uploading...');

                mediaRecorder.stop();
                await new Promise(r => setTimeout(r, 250));

                const blob = new Blob(chunks, { type: mediaRecorder.mimeType || 'audio/webm' });
                const fd = new FormData();
                fd.append('file', blob, 'voice.webm');

                const url = `/demo/voice?shop_phone=${encodeURIComponent(shopPhone.value)}`;
                const resp = await fetch(url, { method: 'POST', body: fd });
                const data = await resp.json();
                log(data);

                if (data && data.pending_id) {
                    pendingId.value = String(data.pending_id);
                    setConfirmEnabled(true);
                }
                btnStart.disabled = false;
            }

            async function confirm(decision) {
                const id = parseInt(pendingId.value, 10);
                if (!id) { log('Missing pending_id'); return; }
                log('Confirming...');
                const resp = await fetch('/demo/confirm', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ pending_id: id, decision })
                });
                const data = await resp.json();
                log(data);
            }

            btnStart.addEventListener('click', () => {
                log('Start clicked. Requesting microphone permission...');
                startRecording().catch(e => log(friendlyMicError(e)));
            });
            btnStop.addEventListener('click', () => {
                stopAndUpload().catch(e => log({ error: String(e) }));
            });
            btnYes.addEventListener('click', () => {
                confirm('YES').catch(e => log({ error: String(e) }));
            });
            btnNo.addEventListener('click', () => {
                confirm('NO').catch(e => log({ error: String(e) }));
            });
            btnDiag.addEventListener('click', () => {
                updateBanner();
                showDiagnostics();
            });

            refreshLedger();
            setInterval(refreshLedger, 2000);

            updateBanner();
            showDiagnostics();
        </script>
    </body>
</html>"""

    return HTMLResponse(
        content=html,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/entries")
def demo_entries(shop_phone: str, limit: int = 25) -> dict:
    if not shop_phone.strip():
        raise HTTPException(status_code=400, detail="shop_phone required")
    entries = get_recent_entries(shop_phone.strip(), limit=limit)
    return {"entries": entries}


class DemoTextIn(BaseModel):
    shop_phone: str = Field(..., description="Identifier for a shop user (e.g., +91...).")
    text: str


class DemoConfirmIn(BaseModel):
    pending_id: int
    decision: str = Field(..., description="YES or NO")


def _is_yes(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in {"y", "yes", "haan", "haanji", "ha", "ok", "okay", "confirm", "✅"}


def _is_no(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in {"n", "no", "nahin", "nahi", "cancel", "❌"}


def _money(amount: float) -> str:
    return f"₹{amount:.0f}" if float(amount).is_integer() else f"₹{amount:.2f}"


def _commit_pending(pending: dict, *, decision: str) -> dict:
    if pending.get("status") != "pending":
        return {"status": "ignored", "message": f"Already {pending.get('status')}"}

    if _is_no(decision):
        set_pending_action_status(int(pending["id"]), "cancelled")
        return {"status": "cancelled", "message": "Okay, cancelled."}

    if not _is_yes(decision):
        return {"status": "need_yes_no", "message": "Please reply YES or NO."}

    action_type = pending.get("action_type")
    payload = pending.get("action_json") or {}
    shop_phone = pending.get("shop_phone")

    try:
        if action_type == Intent.add_udhaar.value:
            customer = get_or_create_customer(shop_phone, payload.get("customer_name", ""))
            entry = insert_udhaar_entry(
                shop_phone=shop_phone,
                customer_id=int(customer["id"]),
                amount=float(payload["amount"]),
                transcript=payload.get("transcript"),
                raw_text=payload.get("raw_text"),
                source_message_id=payload.get("source_message_id"),
            )
            set_pending_action_status(int(pending["id"]), "confirmed")
            return {
                "status": "confirmed",
                "message": f"Done. Added {_money(float(entry['amount']))} udhaar for {customer['name']}",
                "entry": entry,
            }

        if action_type == Intent.undo_last.value:
            entry = undo_last_entry(shop_phone)
            set_pending_action_status(int(pending["id"]), "confirmed")
            if not entry:
                return {"status": "confirmed", "message": "Nothing to undo."}
            return {"status": "confirmed", "message": "Done. Last entry undone (marked reversed).", "entry": entry}

        set_pending_action_status(int(pending["id"]), "cancelled")
        return {"status": "cancelled", "message": "Unknown action type."}
    except Exception:
        logger.exception("Failed committing pending action")
        return {"status": "error", "message": "Failed while saving. Please try again."}


@router.post("/text")
def demo_text(body: DemoTextIn) -> dict:
    # First, expire old pending actions for cleanliness.
    expire_pending_actions(body.shop_phone)

    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    # If user typed YES/NO, they probably mean confirmation.
    if _is_yes(text) or _is_no(text):
        # Confirm the latest pending action.
        pending = get_pending_action(shop_phone=body.shop_phone, pending_id=None)
        if not pending:
            return {"status": "no_pending", "message": "No pending action to confirm."}
        return _commit_pending(pending, decision=text)

    result = extract_intent(text)

    if result.confidence < settings.confidence_threshold:
        return {
            "status": "clarification_needed",
            "intent": result.model_dump(),
            "message": "Samajh nahi aaya. Customer ka naam aur amount bolo (e.g., 'Raju ko 120 udhaar').",
        }

    if result.intent == Intent.get_summary:
        items = get_summary(body.shop_phone)
        return {"status": "ok", "intent": result.model_dump(), "summary": items}

    if result.intent == Intent.undo_last:
        pending = create_pending_action(
            body.shop_phone,
            Intent.undo_last.value,
            {"raw_text": text, "source_message_id": None},
        )
        return {
            "status": "pending_confirmation",
            "pending_id": pending["id"],
            "intent": result.model_dump(),
            "message": "Confirm undo last entry? Reply YES or NO.",
        }

    if result.intent == Intent.add_udhaar:
        if not result.customer_name.strip() or result.amount is None:
            return {
                "status": "clarification_needed",
                "intent": result.model_dump(),
                "message": "Customer ka naam aur amount clear bolo (e.g., 'Sita ko 150 udhaar').",
            }

        pending = create_pending_action(
            body.shop_phone,
            Intent.add_udhaar.value,
            {
                "customer_name": result.customer_name.strip(),
                "amount": float(result.amount),
                "transcript": None,
                "raw_text": text,
                "source_message_id": None,
            },
        )
        return {
            "status": "pending_confirmation",
            "pending_id": pending["id"],
            "intent": result.model_dump(),
            "message": f"Confirm: Add {_money(float(result.amount))} udhaar for {result.customer_name.strip()}? Reply YES or NO.",
        }

    return {"status": "error", "message": "Unknown intent."}


@router.post("/voice")
async def demo_voice(shop_phone: str, file: UploadFile = File(...)) -> dict:
    expire_pending_actions(shop_phone)

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio")

    mime_type = file.content_type or "audio/ogg"
    transcript = await transcribe_audio(audio_bytes, mime_type)
    if not transcript:
        return {"status": "clarification_needed", "message": "Voice clear nahi thi. Please resend."}

    # Reuse the same intent flow, just feed transcript into extractor.
    result = extract_intent(transcript)

    if result.confidence < settings.confidence_threshold:
        return {
            "status": "clarification_needed",
            "transcript": transcript,
            "intent": result.model_dump(),
            "message": "Samajh nahi aaya. Customer ka naam aur amount dubara bolo.",
        }

    if result.intent == Intent.get_summary:
        items = get_summary(shop_phone)
        return {"status": "ok", "transcript": transcript, "intent": result.model_dump(), "summary": items}

    if result.intent == Intent.undo_last:
        pending = create_pending_action(
            shop_phone,
            Intent.undo_last.value,
            {"raw_text": transcript, "transcript": transcript, "source_message_id": None},
        )
        return {
            "status": "pending_confirmation",
            "pending_id": pending["id"],
            "transcript": transcript,
            "intent": result.model_dump(),
            "message": "Confirm undo last entry? Reply YES or NO.",
        }

    if result.intent == Intent.add_udhaar:
        if not result.customer_name.strip() or result.amount is None:
            return {
                "status": "clarification_needed",
                "transcript": transcript,
                "intent": result.model_dump(),
                "message": "Customer ka naam aur amount clear bolo (e.g., 'Raju 120 udhaar').",
            }

        pending = create_pending_action(
            shop_phone,
            Intent.add_udhaar.value,
            {
                "customer_name": result.customer_name.strip(),
                "amount": float(result.amount),
                "transcript": transcript,
                "raw_text": transcript,
                "source_message_id": None,
            },
        )
        return {
            "status": "pending_confirmation",
            "pending_id": pending["id"],
            "transcript": transcript,
            "intent": result.model_dump(),
            "message": f"Confirm: Add {_money(float(result.amount))} udhaar for {result.customer_name.strip()}? Reply YES or NO.",
        }

    return {"status": "error", "message": "Unknown intent."}


@router.post("/confirm")
def demo_confirm(body: DemoConfirmIn) -> dict:
    pending = get_pending_action(shop_phone=None, pending_id=body.pending_id)
    if not pending:
        raise HTTPException(status_code=404, detail="pending action not found")

    # Expiry is enforced in DB query for "latest" only; for direct id lookup, we check here.
    # WHY: prevents late confirmations writing to DB.
    if pending.get("expires_at"):
        try:
            expires_raw = str(pending["expires_at"]).replace("Z", "+00:00")
            expires_at = dt.datetime.fromisoformat(expires_raw)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=dt.timezone.utc)
            if dt.datetime.now(dt.timezone.utc) > expires_at:
                set_pending_action_status(int(pending["id"]), "expired")
                return {"status": "expired", "message": "Confirmation timeout. Please resend."}
        except Exception:
            logger.exception("Failed parsing pending action expires_at")

    return _commit_pending(pending, decision=body.decision)
