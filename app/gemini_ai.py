from __future__ import annotations

import json
import logging
from typing import Any

from google import genai
from google.genai import types

from .settings import settings
from .types import IntentResult

logger = logging.getLogger(__name__)


_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


async def transcribe_audio(audio_bytes: bytes, mime_type: str | None) -> str:
    """Transcribe WhatsApp voice note to text using Gemini.

    WHY: Keeps the demo dependency-light and handles Hindi/Hinglish well.
    """

    if not audio_bytes:
        return ""

    mt = mime_type or "audio/ogg"
    prompt = (
        "Transcribe this WhatsApp voice note. "
        "Return ONLY the transcription text (no markdown). "
        "The speaker may use Hindi/Hinglish. Preserve numbers as digits." 
    )

    client = _get_client()
    # google-genai is sync; keep it simple for hackathon scale.
    try:
        resp = client.models.generate_content(
            model=settings.gemini_transcribe_model,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=prompt),
                        types.Part.from_bytes(data=audio_bytes, mime_type=mt),
                    ],
                )
            ],
        )
        text = (resp.text or "").strip()
        return text
    except Exception:
        logger.exception("Gemini transcription failed")
        raise


def _intent_prompt(transcript: str) -> str:
    return (
        "You are an assistant for an Indian kirana shop's udhaar (credit) notebook. "
        "Given the user's message (Hindi/Hinglish possible), extract intent in STRICT JSON only. "
        "Valid intents: add_udhaar, record_payment, undo_last, get_summary. "
        "Rules: "
        "- For add_udhaar: detect customer_name and amount (number). "
        "- For record_payment: detect customer_name and amount (number). Amount should be a positive number in JSON (we will reduce udhaar internally). "
        "- For undo_last: customer_name can be empty. amount must be null. "
        "- For get_summary: customer_name can be empty. amount must be null. "
        "- confidence is 0 to 1 (float). "
        "Return exactly this JSON shape and nothing else: "
        "{\"intent\":\"add_udhaar | record_payment | undo_last | get_summary\",\"customer_name\":\"string\",\"amount\":number|null,\"confidence\":0-1}"
        "\n\nMessage:\n" + transcript
    )


def extract_intent(transcript: str) -> IntentResult:
    if not transcript.strip():
        return IntentResult(intent="get_summary", customer_name="", amount=None, confidence=0.0)

    client = _get_client()

    try:
        resp = client.models.generate_content(
            model=settings.gemini_intent_model,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=_intent_prompt(transcript))])],
            config=types.GenerateContentConfig(
                temperature=0.0,
                # Best-effort: encourage strict JSON.
                response_mime_type="application/json",
            ),
        )
        raw = (resp.text or "").strip()

        # Defensive parsing: models sometimes wrap JSON in text.
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw = raw[start : end + 1]

        data: dict[str, Any] = json.loads(raw)
        return IntentResult.model_validate(data)
    except Exception:
        logger.exception("Gemini intent extraction failed")
        # Fail safe: ask for clarification
        return IntentResult(intent="get_summary", customer_name="", amount=None, confidence=0.0)
