from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from .db import (
    create_pending_action,
    expire_pending_actions,
    get_latest_pending_action,
    get_or_create_customer,
    get_summary,
    insert_udhaar_entry,
    set_pending_action_status,
    undo_last_entry,
    get_customer_total,
)
from .demo import router as demo_router
from .gemini_ai import extract_intent, transcribe_audio
from .logging_config import setup_logging
from .settings import require_secrets, settings
from .types import Intent
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
app.include_router(demo_router)


@app.on_event("startup")
async def _startup() -> None:
    # WHY: Keep imports/tooling usable even without .env, but fail fast when actually running.
    require_secrets()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


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
        return False

    if _is_yes(text):
        action_id = int(pending["id"])
        action_type = pending["action_type"]
        payload = pending["action_json"]

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
        set_pending_action_status(int(pending["id"]), "cancelled")
        await send_text(shop_phone, "Okay, cancelled.")
        return True

    await send_text(shop_phone, "Please reply YES to confirm or NO to cancel.")
    return True


async def _process_intent(
    shop_phone: str,
    source_message_id: str | None,
    raw_text: str,
    transcript: str | None,
) -> None:
    result = extract_intent(raw_text)

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

    # IMPORTANT: Always return 200 quickly to avoid WhatsApp retries.
    for msg in messages:
        try:
            from_phone = msg.get("from")
            msg_type = msg.get("type")
            msg_id = msg.get("id")
            if not from_phone:
                continue

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

                await _process_intent(
                    shop_phone=from_phone,
                    source_message_id=msg_id,
                    raw_text=transcript,
                    transcript=transcript,
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
