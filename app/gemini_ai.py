from __future__ import annotations

import json
import logging
import re
from typing import Any

from google import genai
from google.genai import types

from .settings import settings
from .types import Intent, IntentResult

logger = logging.getLogger(__name__)


_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


_transaction_schema: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["ADD_TRANSACTION", "CHECK_BALANCE", "UNKNOWN"]},
        "customer_name": {"type": "string"},
        "amount": {"type": "number"},
        "transaction_type": {"type": "string", "enum": ["CREDIT", "PAYMENT"]},
        "item_description": {"type": "string"},
    },
    "required": ["intent"],
}


_PAYMENT_HINTS = [
    "jama",
    "de diya",
    "de diye",
    "de gaya",
    "payment",
    "paid",
    "received",
    "collect",
]

_CREDIT_HINTS = [
    "udhar",
    "udhaar",
    "baaki",
    "le gaya",
    "le liya",
    "liya",
    "credit",
]


def _heuristic_text_parse(text: str) -> dict[str, Any]:
    t = " ".join((text or "").strip().lower().split())
    if not t:
        return {"intent": "UNKNOWN"}

    maybe_total = _maybe_total_query(text)
    if maybe_total:
        return {"intent": "CHECK_BALANCE", "customer_name": maybe_total}

    amount_match = re.search(r"\d+(?:\.\d+)?", t)
    amount = float(amount_match.group(0)) if amount_match else None

    tx_type = "CREDIT"
    if any(h in t for h in _PAYMENT_HINTS):
        tx_type = "PAYMENT"
    elif any(h in t for h in _CREDIT_HINTS):
        tx_type = "CREDIT"

    name = ""
    if amount_match:
        before = t[: amount_match.start()].strip()
        for token in ["ne", "ko", "se", "ka", "ki", "ke", "rs", "rupay", "rupees"]:
            before = before.replace(f" {token} ", " ").replace(f" {token}", " ").replace(f"{token} ", " ")
        before = " ".join(before.split())
        name = before
    else:
        tokens = t.split()
        if tokens:
            name = tokens[0]

    if not amount:
        return {"intent": "UNKNOWN"}

    return {
        "intent": "ADD_TRANSACTION",
        "customer_name": name.title() if name else "",
        "amount": amount,
        "transaction_type": tx_type,
        "item_description": "Text entry",
    }


def _safe_json_parse(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    try:
        data = json.loads(text)
    except Exception:
        return {}

    return data if isinstance(data, dict) else {}


async def parse_text_message(text: str) -> dict[str, Any]:
    """Parse a plain text message into a transaction intent.

    Returns a dict that matches _transaction_schema.
    """

    if not (text or "").strip():
        return {"intent": "UNKNOWN"}

    heuristic = _heuristic_text_parse(text)
    if heuristic.get("intent") in {"ADD_TRANSACTION", "CHECK_BALANCE"}:
        return heuristic

    prompt = (
        "Analyze this shopkeeper's message and extract transaction details. "
        "Rules: 'udhar', 'baaki', 'le gaya' => CREDIT. "
        "'jama', 'de gaya', 'received' => PAYMENT. "
        "Return ONLY JSON matching the schema.\n\n"
        f"Message: {text}"
    )

    client = _get_client()
    try:
        resp = client.models.generate_content(
            model=settings.gemini_intent_model,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )
        data = _safe_json_parse(resp.text or "")
        if data:
            return data
    except Exception:
        logger.exception("Gemini text parsing failed")

    return _heuristic_text_parse(text)


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
        "The speaker may use Hindi/Hinglish. Preserve numbers as digits. "
        "CRITICAL RULE: Always write names in English Script (Roman Alphabet). Never use Devanagari/Hindi script. "
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

        # Safety net: the model may still output Devanagari sometimes.
        # Convert to best-effort Roman script so we don't create separate customer rows.
        try:
            from unidecode import unidecode  # type: ignore

            text = unidecode(text)
        except Exception:
            pass

        # Remove any remaining Devanagari characters.
        text = re.sub(r"[\u0900-\u097F]+", " ", text)
        text = " ".join(text.split())

        return text
    except Exception:
        logger.exception("Gemini transcription failed")
        raise


def _intent_prompt(transcript: str) -> str:
    return (
        "You are a smart assistant for an Indian kirana shop. "
        "Your job is to specificially extract transaction details from the user's message (which may be Hindi/English/Hinglish text, or a description of an image/receipt). "
        "Valid intents: add_udhaar, record_payment, undo_last, get_summary, get_customer_total. "
        "\n\nRules: "
        "1. **add_udhaar**: User wants to add credit (udhaar). Extract 'customer_name' and 'amount'. "
        "2. **record_payment**: User receives money (payment). Extract 'customer_name' and 'amount'. "
        "3. **undo_last**: User wants to undo/delete the last entry. "
        "4. **get_summary**: User wants a list of who owes what. "
        "5. **get_customer_total**: User asks for a specific person's total. "
        "\n\nOutput Format MUST be a single JSON object: "
        "{\"intent\": \"...\", \"customer_name\": \"...\", \"amount\": 123.0, \"confidence\": 0.9}"
        "\n\n- If amount is not mentioned, use null. "
        "\n- If multiple people are mentioned, pick the clearest one. "
        "\n- Convert all numbers to float. "
        "\n\nInput Context:\n" + transcript
    )


_TOTAL_RE = re.compile(
    r"^\s*(?P<name>[\w\u0900-\u097F\s\.']{2,40}?)\s*(?:ne\s+)?(?:ka\s+)?(?:total\s+)?(?:kitna|kitne|kitni|how\s+much)\s+(?:ka\s+)?(?:udhaar|udhar)\b",
    re.IGNORECASE,
)


def _maybe_total_query(text: str) -> str | None:
    # Hindi/Hinglish patterns like:
    # - "Raju ne total kitne ka udhar liya"
    # - "Raju ka total udhaar kitna hai"
    t = (text or "").strip()
    if not t:
        return None
    m = _TOTAL_RE.search(t)
    if not m:
        return None
    name = (m.group("name") or "").strip()
    # Avoid matching generic questions without a real name.
    if len(name) < 2:
        return None
    return name


def extract_intent(transcript: str) -> IntentResult:
    if not transcript.strip():
        return IntentResult(intent="get_summary", customer_name="", amount=None, confidence=0.0)

    # Fast local heuristic: allow "X ka total udhaar?" even if Gemini is unavailable.
    maybe_name = _maybe_total_query(transcript)
    if maybe_name:
        return IntentResult(intent=Intent.get_customer_total, customer_name=maybe_name, amount=None, confidence=1.0)

    client = _get_client()

    def _extract_numbers(text: str) -> list[float]:
        # Extract numeric values from text (e.g., "10", "10.5", "₹10").
        nums: list[float] = []
        for m in re.finditer(r"\d+(?:\.\d+)?", text or ""):
            try:
                nums.append(float(m.group(0)))
            except Exception:
                continue
        return nums

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
        result = IntentResult.model_validate(data)

        # If digits are present in the user's text, prefer those over hallucinated numbers.
        nums = _extract_numbers(transcript)
        if nums:
            # If model returned an amount not present in the text, override with first number.
            if result.amount is None or all(abs(float(result.amount) - n) > 0.001 for n in nums):
                result.amount = float(nums[0])

        return result
    except Exception:
        logger.exception("Gemini intent extraction failed")
        # Fail safe: ask for clarification
        return IntentResult(intent="get_summary", customer_name="", amount=None, confidence=0.0)


async def analyze_image(image_bytes: bytes, mime_type: str) -> IntentResult:
    """Analyze WhatsApp image (e.g. receipt/handwritten note) using Gemini.

    WHY: Allows extracting transaction details from photos.
    """
    if not image_bytes:
        return IntentResult(intent="get_summary", customer_name="", amount=None, confidence=0.0)

    # Re-use the same intent prompt logic but adapted for image context if needed.
    # For now, we ask the model to look at the image and extract the same JSON.
    prompt = (
        "Analyze this image (receipt, handwritten note, or shop counter photo). "
        "Extract the transaction detail in STRICT JSON."
        "\n\n" + _intent_prompt("IMAGE CONTENT")
    )

    client = _get_client()
    try:
        resp = client.models.generate_content(
            model=settings.gemini_intent_model,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=prompt),
                        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    ],
                )
            ],
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )
        raw = (resp.text or "").strip()

        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw = raw[start : end + 1]

        data: dict[str, Any] = json.loads(raw)
        return IntentResult.model_validate(data)

    except Exception:
        logger.exception("Gemini image analysis failed")
        return IntentResult(intent="get_summary", customer_name="", amount=None, confidence=0.0)
