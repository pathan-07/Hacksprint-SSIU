from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

from .settings import settings

logger = logging.getLogger(__name__)


def _graph_base_url() -> str:
    # Base Graph API URL (no trailing slash).
    return f"https://graph.facebook.com/{settings.meta_graph_version}"


def _messages_url() -> str:
    if not settings.whatsapp_phone_number_id:
        raise RuntimeError("Missing WHATSAPP_PHONE_NUMBER_ID")
    return f"{_graph_base_url()}/{settings.whatsapp_phone_number_id}/messages"


def verify_webhook(mode: str | None, token: str | None, challenge: str | None) -> str | None:
    if mode == "subscribe" and token == settings.whatsapp_verify_token and challenge:
        return challenge
    return None


def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Validates X-Hub-Signature-256 if WHATSAPP_APP_SECRET is configured.

    WHY: WhatsApp will POST to your webhook; validating prevents spoofed requests.
    """

    # In local/dev environments, signature validation often blocks progress
    # (misconfigured app secret, proxies, etc). Keep it strict in prod.
    if (settings.app_env or "").lower() not in {"prod", "production"}:
        return True

    if not settings.whatsapp_app_secret:
        return True

    if not signature_header or not signature_header.startswith("sha256="):
        return False

    their_sig = signature_header.removeprefix("sha256=").strip()
    mac = hmac.new(settings.whatsapp_app_secret.encode("utf-8"), msg=raw_body, digestmod=hashlib.sha256)
    our_sig = mac.hexdigest()
    return hmac.compare_digest(our_sig, their_sig)


def extract_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Pulls WhatsApp 'messages' list out of the Cloud API webhook payload."""

    out: list[dict[str, Any]] = []
    try:
        for entry in payload.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                value = (change or {}).get("value") or {}
                for msg in value.get("messages", []) or []:
                    out.append(msg)
    except Exception:
        logger.exception("Failed parsing webhook payload")
    return out


async def get_media_url(media_id: str) -> tuple[str, str | None]:
    """Returns (download_url, mime_type)."""

    url = f"{_graph_base_url()}/{media_id}"
    headers = {"Authorization": f"Bearer {settings.whatsapp_token}"}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["url"], data.get("mime_type")


async def download_media(download_url: str) -> bytes:
    headers = {"Authorization": f"Bearer {settings.whatsapp_token}"}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(download_url, headers=headers)
        resp.raise_for_status()
        return resp.content


async def send_text(to_phone: str, text: str) -> None:
    if settings.test_mode:
        print(f"\n[MOCK WHATSAPP] Sending to {to_phone}: {text}\n")
        return None

    url = _messages_url()
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": text},
    }

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, headers=headers, content=json.dumps(payload))
        if resp.status_code >= 400:
            logger.error("WhatsApp send failed: %s %s", resp.status_code, resp.text)
            resp.raise_for_status()
