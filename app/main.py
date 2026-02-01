from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse

from .db import (
    create_pending_action,
    expire_pending_actions,
    get_latest_pending_action,
    get_recent_entries,
    get_or_create_customer,
    get_summary,
    insert_udhaar_entry,
    set_pending_action_status,
    undo_last_entry,
    get_customer_total,
)
from .demo import router as demo_router
from .gemini_ai import analyze_image, extract_intent, transcribe_audio
from .logging_config import setup_logging
from .settings import require_secrets, settings
from .types import Intent, IntentResult
from .whatsapp import (
    download_media,
    extract_messages,
    get_media_url,
    send_text,
    verify_signature,
    verify_webhook,
)

setup_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="VoiceKhata")


def _shop_phone_key(shop_phone: str) -> str:
    # Keep consistent with DB normalization: "+<digits>".
    digits = "".join(ch for ch in (shop_phone or "") if ch.isdigit())
    return f"+{digits}" if digits else (shop_phone or "")


class _LiveHub:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._subs: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}

    async def subscribe(self, key: str) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        async with self._lock:
            self._subs.setdefault(key, set()).add(q)
        return q

    async def unsubscribe(self, key: str, q: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            bucket = self._subs.get(key)
            if not bucket:
                return
            bucket.discard(q)
            if not bucket:
                self._subs.pop(key, None)

    async def publish(self, shop_phone: str, kind: str, data: dict[str, Any] | None = None) -> None:
        key = _shop_phone_key(shop_phone)
        event: dict[str, Any] = {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
            "shop_phone": key,
            "kind": kind,
            "data": data or {},
        }
        async with self._lock:
            targets = list(self._subs.get(key, set())) + list(self._subs.get("*", set()))

        for q in targets:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Best-effort; drop if consumer is too slow.
                pass


_live = _LiveHub()

# Allow the hackathon landing-page (live-server) to call demo endpoints.
# This is restricted to localhost origins (any port) to keep it safe.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(demo_router)


@app.get("/")
async def root() -> RedirectResponse:
    # Friendly default when opened in a browser.
    return RedirectResponse(url="/docs")


@app.get("/favicon.ico")
async def favicon() -> Response:
    # Avoid noisy 404s from browsers.
    return Response(status_code=204)


@app.on_event("startup")
async def _startup() -> None:
    # WHY: Keep imports/tooling usable even without .env, but fail fast when actually running.
    require_secrets()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/debug/shop")
async def debug_shop(shop_phone: str) -> dict[str, Any]:
    """Dev-only helper to confirm whether WhatsApp is hitting the DB layer.

    Returns latest pending action + recent entries for a given shop phone.
    """

    if (settings.app_env or "").lower() in {"prod", "production"}:
        raise HTTPException(status_code=404, detail="Not found")

    expire_pending_actions(shop_phone)
    pending = get_latest_pending_action(shop_phone)
    entries = get_recent_entries(shop_phone, limit=10)
    return {
        "shop_phone": shop_phone,
        "pending": pending,
        "entries": entries,
    }


@app.get("/debug/live", response_class=HTMLResponse)
async def debug_live_page() -> HTMLResponse:
        if (settings.app_env or "").lower() in {"prod", "production"}:
                raise HTTPException(status_code=404, detail="Not found")

        html = """<!doctype html>
<html lang=\"en\">
    <head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
        <title>VoiceKhata Live Monitor</title>
        <style>
            body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 20px; }
            .row { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
            input { padding: 10px 12px; border-radius: 10px; border: 1px solid #ddd; min-width: 320px; }
            button { padding: 10px 14px; border-radius: 10px; border: 1px solid #ddd; cursor: pointer; }
            pre { background:#0b1020; color:#e7e9ee; padding:12px; border-radius:12px; max-height: 260px; overflow:auto; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border-bottom: 1px solid #eee; padding: 8px 10px; text-align: left; font-size: 14px; }
            th { background: #fafafa; position: sticky; top: 0; }
            .hint { color: #555; }
        </style>
    </head>
    <body>
        <h2>VoiceKhata: Live Monitor</h2>
        <div class=\"hint\">Shows webhook events + latest entries. Use your phone in digits (e.g., 9199...) or +91... (both work).</div>

        <div class=\"row\" style=\"margin: 12px 0;\">
            <label>Shop phone:</label>
            <input id=\"shopPhone\" value=\"919999999999\" />
            <button id=\"btnStart\" type=\"button\">Start</button>
            <button id=\"btnStop\" type=\"button\" disabled>Stop</button>
        </div>

        <h3>Live events</h3>
        <pre id=\"events\">(not started)</pre>

        <h3>Latest entries (auto refresh)</h3>
        <div class=\"hint\">Refreshes every 2 seconds from /debug/shop.</div>
        <div style=\"height: 8px\"></div>
        <div style=\"max-height: 320px; overflow:auto; border: 1px solid #eee; border-radius: 12px;\">
            <table>
                <thead>
                    <tr><th>ID</th><th>Customer</th><th>Amount</th><th>Reversed</th><th>When</th></tr>
                </thead>
                <tbody id=\"rows\"></tbody>
            </table>
        </div>

        <script>
            const eventsEl = document.getElementById('events');
            const rowsEl = document.getElementById('rows');
            const shopPhoneEl = document.getElementById('shopPhone');
            const btnStart = document.getElementById('btnStart');
            const btnStop = document.getElementById('btnStop');
            let es = null;
            let timer = null;

            function appendEvent(obj) {
                const s = typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2);
                eventsEl.textContent = s + "\\n\\n" + eventsEl.textContent;
            }

            async function refreshLedger() {
                const sp = shopPhoneEl.value.trim();
                if (!sp) return;
                const resp = await fetch(`/debug/shop?shop_phone=${encodeURIComponent(sp)}`);
                const data = await resp.json();
                const entries = data.entries || [];
                rowsEl.innerHTML = '';
                if (!entries.length) {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `<td colspan=\"5\" class=\"hint\">No entries yet.</td>`;
                    rowsEl.appendChild(tr);
                    return;
                }
                for (const r of entries) {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `<td>${r.id}</td><td>${r.customer_name || ''}</td><td>${r.amount}</td><td>${r.reversed ? 'yes' : 'no'}</td><td>${r.created_at}</td>`;
                    rowsEl.appendChild(tr);
                }
            }

            function start() {
                const sp = shopPhoneEl.value.trim();
                if (!sp) return;
                appendEvent({status:'starting', shop_phone: sp});

                if (es) es.close();
                es = new EventSource(`/debug/stream?shop_phone=${encodeURIComponent(sp)}`);
                es.onmessage = (e) => {
                    try { appendEvent(JSON.parse(e.data)); }
                    catch { appendEvent(e.data); }
                };
                es.onerror = () => appendEvent({error:'eventsource error'});

                if (timer) clearInterval(timer);
                refreshLedger();
                timer = setInterval(refreshLedger, 2000);

                btnStart.disabled = true;
                btnStop.disabled = false;
            }

            function stop() {
                if (es) es.close();
                es = null;
                if (timer) clearInterval(timer);
                timer = null;
                btnStart.disabled = false;
                btnStop.disabled = true;
                appendEvent({status:'stopped'});
            }

            btnStart.addEventListener('click', start);
            btnStop.addEventListener('click', stop);
        </script>
    </body>
</html>"""

        return HTMLResponse(content=html)


@app.get("/debug/stream")
async def debug_stream(shop_phone: str = Query(default="*")) -> StreamingResponse:
        if (settings.app_env or "").lower() in {"prod", "production"}:
                raise HTTPException(status_code=404, detail="Not found")

        key = "*" if (shop_phone or "").strip() == "*" else _shop_phone_key(shop_phone)
        q = await _live.subscribe(key)

        async def gen() -> Any:
                try:
                        hello = {
                                "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
                                "kind": "connected",
                                "shop_phone": key,
                        }
                        yield f"data: {json.dumps(hello)}\n\n"
                        while True:
                                event = await q.get()
                                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except asyncio.CancelledError:
                        raise
                finally:
                        await _live.unsubscribe(key, q)

        return StreamingResponse(
                gen(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )


@app.get("/webhook/whatsapp")
async def whatsapp_verify(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> Any:
    if not settings.enable_whatsapp:
        raise HTTPException(status_code=503, detail="WhatsApp disabled. Set ENABLE_WHATSAPP=true")
    challenge = verify_webhook(hub_mode, hub_verify_token, hub_challenge)
    if challenge is None:
        raise HTTPException(status_code=403, detail="Verification failed")
    return PlainTextResponse(content=challenge)


def _is_yes(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in {"y", "yes", "haan", "haanji", "ha", "ok", "okay", "confirm", "✅"}


def _is_no(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in {"n", "no", "nahin", "nahi", "cancel", "❌"}


def _money(amount: float) -> str:
    # Simple INR formatting for WhatsApp.
    return f"₹{amount:.0f}" if float(amount).is_integer() else f"₹{amount:.2f}"

def _net_label(total: float) -> str:
    if total < 0:
        return f"Advance {_money(abs(total))}"
    return f"Net {_money(total)}"

async def _handle_confirmation(shop_phone: str, text: str) -> bool:
    expire_pending_actions(shop_phone)
    pending = get_latest_pending_action(shop_phone)
    if not pending:
        logger.info("No pending action for %s (text=%s)", shop_phone, (text or "").strip()[:64])
        await _live.publish(shop_phone, "confirm_no_pending", {"text": (text or "").strip()[:128]})
        return False

    if _is_yes(text):
        action_id = int(pending["id"])
        action_type = pending["action_type"]
        payload = pending["action_json"]

        logger.info("Confirm YES: shop=%s action=%s pending_id=%s", shop_phone, action_type, action_id)
        await _live.publish(shop_phone, "confirm_yes", {"pending_id": action_id, "action_type": action_type})

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
                set_pending_action_status(action_id, "confirmed")
                await _live.publish(shop_phone, "db_entry_created", {"entry_id": entry.get("id"), "amount": entry.get("amount")})
                await send_text(
                    shop_phone,
                    f"Done. Added {_money(float(entry['amount']))} udhaar for {customer['name']}.",
                )
                return True

            if action_type == Intent.undo_last.value:
                entry = undo_last_entry(shop_phone)
                set_pending_action_status(action_id, "confirmed")
                if not entry:
                    await send_text(shop_phone, "Nothing to undo.")
                    return True
                await _live.publish(shop_phone, "db_entry_undone", {"entry_id": entry.get("id")})
                await send_text(shop_phone, "Done. Last entry has been undone (marked reversed).")
                return True

            # Unknown action
            set_pending_action_status(action_id, "cancelled")
            await send_text(shop_phone, "Cancelled (unknown pending action).")
            return True
        except Exception:
            logger.exception("Failed committing pending action")
            await send_text(shop_phone, "Sorry, something went wrong while saving. Please try again.")
            return True

    if _is_no(text):
        logger.info("Confirm NO: shop=%s pending_id=%s", shop_phone, pending.get("id"))
        await _live.publish(shop_phone, "confirm_no", {"pending_id": pending.get("id")})
        set_pending_action_status(int(pending["id"]), "cancelled")
        await send_text(shop_phone, "Okay, cancelled.")
        return True

    await _live.publish(shop_phone, "confirm_need_yes_no", {"pending_id": pending.get("id"), "text": (text or "").strip()[:128]})
    await send_text(shop_phone, "Please reply YES to confirm or NO to cancel.")
    return True


async def _process_intent(
    shop_phone: str,
    source_message_id: str | None,
    raw_text: str,
    transcript: str | None,
    pre_calculated_result: IntentResult | None = None,
) -> None:
    result = pre_calculated_result or extract_intent(raw_text)

    logger.info(
        "Intent: shop=%s intent=%s conf=%.2f customer=%s amount=%s",
        shop_phone,
        getattr(result.intent, "value", str(result.intent)),
        float(result.confidence),
        (result.customer_name or "").strip()[:32],
        result.amount,
    )

    if result.confidence < settings.confidence_threshold:
        await send_text(
            shop_phone,
            "I couldn't understand confidently. Please repeat clearly with customer name and amount.\n"
            "Example: 'Ramesh ko 200 udhaar'",
        )
        return

    if result.intent == Intent.get_summary:
        items = get_summary(shop_phone)
        if not items:
            await send_text(shop_phone, "No udhaar entries yet.")
            return

        lines = ["Udhaar summary:"]
        for row in items[:10]:
            lines.append(f"- {row['customer_name']}: {_money(float(row['amount']))}")
        await send_text(shop_phone, "\n".join(lines))
        return

    if result.intent == Intent.undo_last:
        create_pending_action(
            shop_phone,
            Intent.undo_last.value,
            {"source_message_id": source_message_id, "raw_text": raw_text},
        )
        await _live.publish(shop_phone, "pending_created", {"action_type": Intent.undo_last.value})
        await send_text(shop_phone, "Confirm undo last entry? Reply YES or NO.")
        return

    if result.intent == Intent.add_udhaar:
        if not result.customer_name.strip() or result.amount is None:
            await send_text(
                shop_phone,
                "Please say customer name and amount.\nExample: 'Sita ko 150 udhaar add karo'",
            )
            return

        create_pending_action(
            shop_phone,
            Intent.add_udhaar.value,
            {
                "customer_name": result.customer_name.strip(),
                "amount": float(result.amount),
                "transcript": transcript,
                "raw_text": raw_text,
                "source_message_id": source_message_id,
            },
        )
        await _live.publish(
            shop_phone,
            "pending_created",
            {"action_type": Intent.add_udhaar.value, "customer": result.customer_name.strip(), "amount": float(result.amount)},
        )
        await send_text(
            shop_phone,
            f"Confirm: Add {_money(float(result.amount))} udhaar for {result.customer_name.strip()}? Reply YES or NO.",
        )
        return

    if result.intent == Intent.get_customer_total:
        if not result.customer_name.strip():
            await send_text(shop_phone, "Which customer? Example: 'Raju ka total udhaar kitna hai?'")
            return
        info = get_customer_total(shop_phone, result.customer_name.strip())
        if not info or info.get("status") != "ok":
            sug = (info or {}).get("suggestions") or []
            msg = "Customer not found."
            if sug:
                msg += " Did you mean: " + ", ".join(sug)
            await send_text(shop_phone, msg)
            return

        total = float(info["total"])
        label = result.customer_name.strip()
        if info.get("customer"):
            label = str(info["customer"]["name"])
        customers = info.get("customers") or []
        msg = f"{label} total: {_net_label(total)}"
        if len(customers) > 1:
            msg += f" (matched {len(customers)} customers)"
        await send_text(shop_phone, msg)
        return

    await send_text(shop_phone, "Sorry, I couldn't map that to an action.")


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
) -> dict[str, str]:
    if not settings.enable_whatsapp:
        raise HTTPException(status_code=503, detail="WhatsApp disabled. Set ENABLE_WHATSAPP=true")
    raw = await request.body()
    if not verify_signature(raw, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        logger.exception("Invalid JSON payload")
        return {"status": "ok"}

    messages = extract_messages(payload)

    logger.info("WhatsApp webhook: %s message(s)", len(messages))

    # IMPORTANT: Always return 200 quickly to avoid WhatsApp retries.
    for msg in messages:
        try:
            from_phone = msg.get("from")
            msg_type = msg.get("type")
            msg_id = msg.get("id")
            if not from_phone:
                continue

            logger.info("Incoming WhatsApp msg: from=%s type=%s id=%s", from_phone, msg_type, msg_id)
            await _live.publish(from_phone, "incoming", {"type": msg_type, "id": msg_id})

            if msg_type == "text":
                text = ((msg.get("text") or {}).get("body") or "").strip()
                if not text:
                    continue

                # If user is responding to a confirmation, handle that first.
                handled = await _handle_confirmation(from_phone, text)
                if handled:
                    continue

                # Otherwise treat text like a command.
                await _process_intent(
                    shop_phone=from_phone,
                    source_message_id=msg_id,
                    raw_text=text,
                    transcript=None,
                )
                continue

            # Voice notes commonly come as type="audio" with audio.voice==True.
            if msg_type == "audio":
                audio = msg.get("audio") or {}
                media_id = audio.get("id")
                if not media_id:
                    await send_text(from_phone, "Couldn't find audio media id. Please try again.")
                    continue

                download_url, mime_type = await get_media_url(media_id)
                audio_bytes = await download_media(download_url)

                transcript = await transcribe_audio(audio_bytes, mime_type)
                if not transcript:
                    await send_text(from_phone, "I couldn't transcribe that. Please resend the voice note.")
                    continue

                await _live.publish(from_phone, "transcribed", {"text": transcript[:200]})

                await _process_intent(
                    shop_phone=from_phone,
                    source_message_id=msg_id,
                    raw_text=transcript,
                    transcript=transcript,
                )
                continue

            # Image messages (receipts/notes)
            if msg_type == "image":
                image = msg.get("image") or {}
                media_id = image.get("id")
                caption = image.get("caption") or ""
                if not media_id:
                    await send_text(from_phone, "Couldn't find image media id. Please try again.")
                    continue

                await send_text(from_phone, "Analyzing image... please wait.")
                download_url, mime_type = await get_media_url(media_id)
                image_bytes = await download_media(download_url)

                # Analyze image with Gemini
                result = await analyze_image(image_bytes, mime_type)

                # If caption exists, maybe we can use it to improve confidence or context?
                # For now, let's just use the image result.
                
                await _process_intent(
                    shop_phone=from_phone,
                    source_message_id=msg_id,
                    raw_text=f"[Image detected] {caption}",
                    transcript=caption,
                    pre_calculated_result=result,
                )
                continue

            # Ignore other message types for demo stability.
        except Exception:
            logger.exception("Failed processing message")
            # Best-effort user feedback; avoid infinite loops.
            try:
                if msg.get("from"):
                    await send_text(msg["from"], "Sorry, I hit an error. Please try again.")
            except Exception:
                pass

    return {"status": "ok"}
