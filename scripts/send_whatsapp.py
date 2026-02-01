from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx

# Allow running as a script: `python scripts/send_whatsapp.py`
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.settings import settings


def _graph_base_url() -> str:
    version = (settings.meta_graph_version or "v19.0").strip()
    if not version.startswith("v"):
        version = "v" + version
    return f"https://graph.facebook.com/{version}"


def _messages_url() -> str:
    if not settings.whatsapp_phone_number_id:
        raise SystemExit("Missing WHATSAPP_PHONE_NUMBER_ID in .env")
    return f"{_graph_base_url()}/{settings.whatsapp_phone_number_id}/messages"


def _auth_headers() -> dict[str, str]:
    if not settings.whatsapp_token:
        raise SystemExit("Missing WHATSAPP_TOKEN in .env")
    return {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type": "application/json",
    }


def _post(payload: dict[str, Any]) -> dict[str, Any]:
    url = _messages_url()
    with httpx.Client(timeout=20) as client:
        resp = client.post(url, headers=_auth_headers(), content=json.dumps(payload))
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}

        if resp.status_code >= 400:
            raise SystemExit(f"WhatsApp send failed ({resp.status_code}): {data}")
        return data


def send_text(*, to: str, body: str) -> dict[str, Any]:
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }
    return _post(payload)


def send_template(*, to: str, name: str, lang: str, body_params: list[str]) -> dict[str, Any]:
    components: list[dict[str, Any]] = []
    if body_params:
        components.append(
            {
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in body_params],
            }
        )

    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": name,
            "language": {"code": lang},
        },
    }
    if components:
        payload["template"]["components"] = components

    return _post(payload)


def main() -> None:
    p = argparse.ArgumentParser(description="Send a WhatsApp message via Cloud API using .env config")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_text = sub.add_parser("text", help="Send a plain text message")
    p_text.add_argument("--to", required=True, help="Recipient number in digits-only E.164 (e.g. 919574896517)")
    p_text.add_argument("--body", required=True, help="Message text")

    p_tpl = sub.add_parser("template", help="Send a template message")
    p_tpl.add_argument("--to", required=True, help="Recipient number in digits-only E.164 (e.g. 919574896517)")
    p_tpl.add_argument("--name", required=True, help="Template name")
    p_tpl.add_argument("--lang", default="en_US", help="Template language code (default: en_US)")
    p_tpl.add_argument(
        "--body-param",
        action="append",
        default=[],
        help="Repeat for each body parameter, in order (e.g. --body-param 'John' --body-param '123')",
    )

    args = p.parse_args()

    if args.cmd == "text":
        data = send_text(to=str(args.to), body=str(args.body))
        print(json.dumps(data, indent=2))
        return

    if args.cmd == "template":
        data = send_template(
            to=str(args.to),
            name=str(args.name),
            lang=str(args.lang),
            body_params=[str(x) for x in (args.body_param or [])],
        )
        print(json.dumps(data, indent=2))
        return


if __name__ == "__main__":
    main()
