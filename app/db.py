from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import httpx

from .settings import settings

logger = logging.getLogger(__name__)

_http: httpx.Client | None = None


def _get_http() -> httpx.Client:
    global _http
    if _http is None:
        _http = httpx.Client(timeout=20)
    return _http


def _headers(prefer: str | None = None) -> dict[str, str]:
    h = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _rest_url(table: str) -> str:
    # Supabase PostgREST endpoint
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}"


def _rest_get(table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    r = _get_http().get(_rest_url(table), params=params, headers=_headers())
    r.raise_for_status()
    return r.json() or []


def _rest_insert(
    table: str,
    body: dict[str, Any] | list[dict[str, Any]],
    *,
    params: dict[str, str] | None = None,
    prefer: str = "return=representation",
) -> list[dict[str, Any]]:
    r = _get_http().post(_rest_url(table), params=params, json=body, headers=_headers(prefer))
    r.raise_for_status()
    return r.json() or []


def _rest_patch(table: str, params: dict[str, str], body: dict[str, Any]) -> None:
    r = _get_http().patch(_rest_url(table), params=params, json=body, headers=_headers())
    r.raise_for_status()


def _name_norm(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def get_or_create_customer(shop_phone: str, customer_name: str) -> dict[str, Any]:
    name = (customer_name or "").strip()
    if not name:
        raise ValueError("customer_name is required")

    payload = {
        "shop_phone": shop_phone,
        "name": name,
        "name_norm": _name_norm(name),
    }

    # WHY: Upsert makes demo robust to spelling/case repeats.
    rows = _rest_insert(
        "customers",
        payload,
        params={"on_conflict": "shop_phone,name_norm"},
        prefer="resolution=merge-duplicates,return=representation",
    )
    if not rows:
        raise RuntimeError("Failed to upsert customer")
    return rows[0]


def create_pending_action(shop_phone: str, action_type: str, action_json: dict[str, Any]) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    expires = now + dt.timedelta(seconds=settings.pending_action_ttl_seconds)

    rows = _rest_insert(
        "pending_actions",
        {
            "shop_phone": shop_phone,
            "action_type": action_type,
            "action_json": action_json,
            "status": "pending",
            "expires_at": expires.isoformat(),
        },
    )
    return rows[0]


def get_latest_pending_action(shop_phone: str) -> dict[str, Any] | None:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    rows = _rest_get(
        "pending_actions",
        {
            "select": "*",
            "shop_phone": f"eq.{shop_phone}",
            "status": "eq.pending",
            "expires_at": f"gt.{now}",
            "order": "created_at.desc",
            "limit": "1",
        },
    )
    return rows[0] if rows else None


def get_pending_action(*, shop_phone: str | None, pending_id: int | None) -> dict[str, Any] | None:
    """Fetch a pending action.

    - If pending_id is provided, fetch by id (any status).
    - Else fetch latest non-expired pending for shop_phone.
    """

    if pending_id is not None:
        rows = _rest_get(
            "pending_actions",
            {
                "select": "*",
                "id": f"eq.{pending_id}",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    if not shop_phone:
        return None
    expire_pending_actions(shop_phone)
    return get_latest_pending_action(shop_phone)


def expire_pending_actions(shop_phone: str) -> None:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    _rest_patch(
        "pending_actions",
        {
            "shop_phone": f"eq.{shop_phone}",
            "status": "eq.pending",
            "expires_at": f"lte.{now}",
        },
        {"status": "expired"},
    )


def set_pending_action_status(action_id: int, status: str) -> None:
    _rest_patch("pending_actions", {"id": f"eq.{action_id}"}, {"status": status})


def insert_udhaar_entry(
    shop_phone: str,
    customer_id: int,
    amount: float,
    transcript: str | None,
    raw_text: str | None,
    source_message_id: str | None,
) -> dict[str, Any]:
    rows = _rest_insert(
        "udhaar_entries",
        {
            "shop_phone": shop_phone,
            "customer_id": customer_id,
            "amount": amount,
            "transcript": transcript,
            "raw_text": raw_text,
            "source_message_id": source_message_id,
        },
    )
    return rows[0]


def undo_last_entry(shop_phone: str) -> dict[str, Any] | None:
    """Marks the most recent non-reversed entry as reversed.

    WHY: We never delete records; undo is a reversible audit trail.
    """

    rows = _rest_get(
        "udhaar_entries",
        {
            "select": "*",
            "shop_phone": f"eq.{shop_phone}",
            "reversed": "eq.false",
            "order": "created_at.desc",
            "limit": "1",
        },
    )
    if not rows:
        return None

    entry = rows[0]
    _rest_patch(
        "udhaar_entries",
        {"id": f"eq.{entry['id']}"},
        {"reversed": True, "reversed_at": dt.datetime.now(dt.timezone.utc).isoformat()},
    )
    entry["reversed"] = True
    return entry


def get_summary(shop_phone: str) -> list[dict[str, Any]]:
    """Returns per-customer net udhaar for this shop."""

    # Minimal approach: fetch recent and aggregate in Python.
    # WHY: keeps SQL/RPC complexity low for hackathon scale.
    rows = _rest_get(
        "udhaar_entries",
        {
            "select": "amount,reversed,customer_id",
            "shop_phone": f"eq.{shop_phone}",
            "order": "created_at.desc",
            "limit": "500",
        },
    )

    totals: dict[int, float] = {}
    for row in rows or []:
        if row.get("reversed"):
            continue
        cid = int(row["customer_id"])
        totals[cid] = totals.get(cid, 0.0) + float(row["amount"])

    if not totals:
        return []

    cust_ids = list(totals.keys())
    in_list = ",".join(str(i) for i in cust_ids)
    customers = _rest_get(
        "customers",
        {
            "select": "id,name",
            "id": f"in.({in_list})",
        },
    )
    id_to_name = {int(c["id"]): c["name"] for c in (customers or [])}

    items = [{"customer_name": id_to_name.get(cid, str(cid)), "amount": amt} for cid, amt in totals.items()]
    items.sort(key=lambda x: x["amount"], reverse=True)
    return items


def get_recent_entries(shop_phone: str, limit: int = 20) -> list[dict[str, Any]]:
    """Returns recent entries with customer names.

    WHY: Used by the demo recorder page to show a live-updating ledger without requiring Supabase UI.
    """

    limit = max(1, min(int(limit), 200))

    entries = _rest_get(
        "udhaar_entries",
        {
            "select": "id,customer_id,amount,reversed,created_at,transcript",
            "shop_phone": f"eq.{shop_phone}",
            "order": "created_at.desc",
            "limit": str(limit),
        },
    )
    if not entries:
        return []

    cust_ids = sorted({int(e["customer_id"]) for e in entries if e.get("customer_id") is not None})
    in_list = ",".join(str(i) for i in cust_ids)
    customers = _rest_get(
        "customers",
        {
            "select": "id,name",
            "shop_phone": f"eq.{shop_phone}",
            "id": f"in.({in_list})",
        },
    )
    id_to_name = {int(c["id"]): c["name"] for c in (customers or [])}

    out: list[dict[str, Any]] = []
    for e in entries:
        cid = int(e["customer_id"])
        out.append(
            {
                "id": e["id"],
                "customer_name": id_to_name.get(cid, str(cid)),
                "amount": float(e["amount"]),
                "reversed": bool(e.get("reversed")),
                "created_at": e.get("created_at"),
                "transcript": e.get("transcript"),
            }
        )
    return out
