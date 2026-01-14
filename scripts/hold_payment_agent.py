from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import logging
import os
import sys
from typing import Any


# Allow running as a script: `python scripts/hold_payment_agent.py`
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import db
from app.settings import settings

logger = logging.getLogger(__name__)


def _fmt_date(ts: str | None) -> str:
    if not ts:
        return ""
    try:
        # Supabase returns ISO with timezone
        d = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return d.strftime("%d %b %Y")
    except Exception:
        return ts


def _build_message(hold: dict[str, Any]) -> str:
    customer = hold.get("customer_name") or f"Customer {hold.get('customer_id')}"
    amount = float(hold.get("amount") or 0)
    base_date = hold.get("due_at") or hold.get("created_at")
    when = _fmt_date(base_date)
    reason = (hold.get("hold_reason") or "").strip()

    msg = f"Payment follow-up reminder: {customer} has ₹{amount:.0f} pending"
    if when:
        msg += f" since {when}" if not hold.get("due_at") else f" (due {when})"
    if reason:
        msg += f". Note: {reason}"
    msg += "."
    return msg


async def _send_whatsapp(shop_phone: str, text: str) -> None:
    # Import inside to avoid importing WhatsApp deps when not needed.
    from app.whatsapp import send_text

    await send_text(shop_phone, text)


async def run_agent(*, shop_phone: str, cutoff_days: int, dry_run: bool = False) -> int:
    holds = db.list_due_payment_holds(shop_phone, cutoff_days=cutoff_days)
    if not holds:
        logger.info("No due holds found.")
        return 0

    sent = 0
    for h in holds:
        hold_id = int(h["id"])
        text = _build_message(h)

        channel = "demo"
        status = "sent"
        err: str | None = None

        if settings.enable_whatsapp and settings.whatsapp_token and settings.whatsapp_phone_number_id:
            channel = "whatsapp"
            if dry_run:
                logger.info("[DRY RUN] Would WhatsApp %s: %s", shop_phone, text)
            else:
                try:
                    await _send_whatsapp(shop_phone, text)
                except Exception as e:
                    status = "failed"
                    err = str(e)
                    logger.exception("Failed sending WhatsApp notification")
        else:
            logger.info("[DEMO NOTIFY] %s -> %s", shop_phone, text)

        db.insert_notification_log(
            shop_phone=shop_phone,
            channel=channel,
            notification_type=f"payment_hold_{cutoff_days}d",
            entity_table="payment_holds",
            entity_id=hold_id,
            message=text,
            status=status,
            error=err,
        )

        if status == "sent" and not dry_run:
            db.mark_payment_hold_notified(hold_id)
            sent += 1

    return sent


def main() -> None:
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    p = argparse.ArgumentParser(description="VoiceKhata payment hold reminder agent")
    p.add_argument("--shop-phone", default="+919999999999", help="Shop phone to notify")
    p.add_argument("--cutoff-days", type=int, default=7, help="Days after which a hold becomes due")
    p.add_argument("--dry-run", action="store_true", help="Do not send or update DB")
    args = p.parse_args()

    sent = asyncio.run(run_agent(shop_phone=str(args.shop_phone), cutoff_days=int(args.cutoff_days), dry_run=bool(args.dry_run)))
    print(f"sent={sent}")


if __name__ == "__main__":
    main()
