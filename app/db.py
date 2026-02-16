from __future__ import annotations

import datetime as dt
import logging
import difflib
import uuid
from typing import Any

import httpx

from .settings import settings

logger = logging.getLogger(__name__)


try:
    # Pure python dependency (recommended for voice-name matching)
    from metaphone import doublemetaphone  # type: ignore
except Exception:
    doublemetaphone = None

_http: httpx.Client | None = None


def _is_missing_table_error(e: Exception) -> bool:
    return isinstance(e, httpx.HTTPStatusError) and getattr(e.response, "status_code", None) == 404


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
    if r.status_code >= 400:
        raise RuntimeError(f"Supabase GET {table} failed ({r.status_code}): {r.text}")
    return r.json() or []


def _rest_insert(
    table: str,
    body: dict[str, Any] | list[dict[str, Any]],
    *,
    params: dict[str, str] | None = None,
    prefer: str = "return=representation",
) -> list[dict[str, Any]]:
    r = _get_http().post(_rest_url(table), params=params, json=body, headers=_headers(prefer))
    if r.status_code >= 400:
        raise RuntimeError(f"Supabase INSERT {table} failed ({r.status_code}): {r.text}")
    return r.json() or []


def _rest_patch(table: str, params: dict[str, str], body: dict[str, Any]) -> None:
    r = _get_http().patch(_rest_url(table), params=params, json=body, headers=_headers())
    if r.status_code >= 400:
        raise RuntimeError(f"Supabase PATCH {table} failed ({r.status_code}): {r.text}")


def _name_norm(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def _product_name_norm(name: str) -> str:
    return _name_norm(name)


def _product_stock(row: dict[str, Any]) -> int:
    if row.get("stock_quantity") is not None:
        return int(row.get("stock_quantity") or 0)
    return int(row.get("current_stock") or 0)


def _product_phone(row: dict[str, Any]) -> str:
    value = row.get("merchant_phone")
    if value is None:
        value = row.get("shop_phone")
    return _shop_phone_norm(str(value or ""))


def _shop_phone_norm(shop_phone: str) -> str:
    """Normalizes shop phone to a stable E.164-ish format: +<digits>.

    WHY: WhatsApp webhooks provide digits-only numbers (e.g. 9195...), while
    demo UI often uses +9195.... Without normalization, reads/writes hit
    different rows and the ledger appears empty.
    """

    digits = "".join(ch for ch in (shop_phone or "") if ch.isdigit())
    if digits.startswith("00"):
        digits = digits[2:]
    return f"+{digits}" if digits else ""


def _roman_key(name: str) -> str:
    """Best-effort romanized/normalized form for fuzzy matching."""

    try:
        from unidecode import unidecode  # type: ignore

        return _name_norm(unidecode(name or ""))
    except Exception:
        return _name_norm(name)


def _ascii_key(name: str) -> str:
    """Returns a phonetic code for matching pronunciation.

    Example: 'Raju' and 'Raaju' should land on the same phonetic key.
    Falls back to a romanized normalized string when phonetic encoding isn't available.
    """

    norm = _roman_key(name)

    if not norm:
        return ""

    if doublemetaphone:
        # Handle multi-word names by encoding each token.
        codes: list[str] = []
        for token in norm.split():
            primary = (doublemetaphone(token)[0] or "").strip()
            codes.append(primary or token)
        return " ".join(codes).strip()

    return norm


def _list_products(merchant_phone: str, *, limit: int = 500) -> list[dict[str, Any]]:
    merchant_phone = _shop_phone_norm(merchant_phone)
    limit = max(1, min(int(limit), 1000))
    try:
        rows = _rest_get(
            "products",
            {
                "select": "*",
                "limit": str(limit),
            },
        )
        return [r for r in rows if _product_phone(r) == merchant_phone]
    except Exception as e:
        if "PGRST" in str(e) or "does not exist" in str(e):
            return []
        raise


def get_products_by_names(merchant_phone: str, product_names: list[str]) -> dict[str, dict[str, Any]]:
    if not product_names:
        return {}
    names = {_product_name_norm(n) for n in product_names if (n or "").strip()}
    if not names:
        return {}
    rows = _list_products(merchant_phone)
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _product_name_norm(str(row.get("normalized_name") or row.get("name") or ""))
        if key in names:
            out[key] = row
    return out


def apply_inventory_sale(
    shop_phone: str,
    items: list[dict[str, Any]],
    *,
    notes: str | None = None,
) -> dict[str, Any]:
    merchant_phone = _shop_phone_norm(shop_phone)
    items = items or []
    if not items:
        return {"status": "empty", "total": 0.0, "line_items": []}

    product_names: list[str] = []
    for item in items:
        name = str(item.get("product_name") or item.get("name") or "").strip()
        if name:
            product_names.append(name)

    products = get_products_by_names(merchant_phone, product_names)

    missing_products: list[str] = []
    missing_prices: list[str] = []
    insufficient_stock: list[dict[str, Any]] = []
    line_items: list[dict[str, Any]] = []
    total = 0.0

    for item in items:
        name = str(item.get("product_name") or item.get("name") or "").strip()
        if not name:
            continue
        norm = _product_name_norm(name)
        product = products.get(norm)
        if not product:
            missing_products.append(name)
            continue

        try:
            qty = float(item.get("quantity") or 0)
        except Exception:
            qty = 0.0
        if qty <= 0:
            continue

        price = product.get("selling_price")
        if price is None:
            missing_prices.append(name)
            continue

        stock = _product_stock(product)
        if stock < qty:
            insufficient_stock.append(
                {
                    "product_name": product.get("name") or name,
                    "available": stock,
                    "requested": qty,
                }
            )
            continue

        line_total = float(price) * float(qty)
        total += line_total
        line_items.append(
            {
                "product_id": product.get("id"),
                "product_name": product.get("name") or name,
                "quantity": qty,
                "unit": item.get("unit") or product.get("unit"),
                "price": float(price),
                "line_total": line_total,
                "stock_before": stock,
                "stock_after": stock - int(qty),
            }
        )

    if missing_products or missing_prices or insufficient_stock:
        return {
            "status": "error",
            "missing_products": missing_products,
            "missing_prices": missing_prices,
            "insufficient_stock": insufficient_stock,
            "total": total,
            "line_items": line_items,
        }

    try:
        for line in line_items:
            pid = int(line["product_id"])
            stock_field = "stock_quantity"
            product = products.get(_product_name_norm(str(line.get("product_name") or ""))) or {}
            if product.get("stock_quantity") is None and product.get("current_stock") is not None:
                stock_field = "current_stock"
            _rest_patch(
                "products",
                {"id": f"eq.{pid}"},
                {stock_field: int(line["stock_after"])},
            )
            _rest_insert(
                "inventory_logs",
                {
                    "product_id": pid,
                    "change_type": "SALE",
                    "quantity_change": -int(line["quantity"]),
                    "notes": notes,
                },
            )
    except Exception as e:
        if _is_missing_table_error(e):
            raise RuntimeError("Supabase schema missing: run supabase/schema.sql (products, inventory_logs)")
        raise

    return {"status": "ok", "total": total, "line_items": line_items}


def apply_inventory_restock(
    shop_phone: str,
    items: list[dict[str, Any]],
    *,
    notes: str | None = None,
) -> dict[str, Any]:
    merchant_phone = _shop_phone_norm(shop_phone)
    items = items or []
    if not items:
        return {"status": "empty", "total": 0.0, "line_items": []}

    product_names: list[str] = []
    for item in items:
        name = str(item.get("product_name") or item.get("name") or "").strip()
        if name:
            product_names.append(name)

    products = get_products_by_names(merchant_phone, product_names)
    line_items: list[dict[str, Any]] = []
    total = 0.0

    for item in items:
        name = str(item.get("product_name") or item.get("name") or "").strip()
        if not name:
            continue
        norm = _product_name_norm(name)
        product = products.get(norm)

        try:
            qty = float(item.get("quantity") or 0)
        except Exception:
            qty = 0.0
        if qty <= 0:
            continue

        unit = item.get("unit") or (product.get("unit") if product else None) or "pcs"
        cost_price = item.get("cost_price")
        try:
            cost_price_f = float(cost_price) if cost_price is not None else None
        except Exception:
            cost_price_f = None

        if not product:
            payload_candidates: list[tuple[dict[str, Any], dict[str, str] | None, str]] = [
                (
                    {
                        "merchant_phone": merchant_phone,
                        "name": name,
                        "normalized_name": _product_name_norm(name),
                        "cost_price": cost_price_f,
                        "stock_quantity": 0,
                        "unit": unit,
                    },
                    {"on_conflict": "merchant_phone,normalized_name"},
                    "resolution=merge-duplicates,return=representation",
                ),
                (
                    {
                        "merchant_phone": merchant_phone,
                        "name": name,
                        "cost_price": cost_price_f,
                        "stock_quantity": 0,
                        "unit": unit,
                    },
                    None,
                    "return=representation",
                ),
                (
                    {
                        "merchant_phone": merchant_phone,
                        "name": name,
                        "cost_price": cost_price_f,
                        "current_stock": 0,
                        "unit": unit,
                    },
                    None,
                    "return=representation",
                ),
                (
                    {
                        "merchant_phone": merchant_phone,
                        "name": name,
                        "cost_price": cost_price_f,
                        "unit": unit,
                    },
                    None,
                    "return=representation",
                ),
                (
                    {
                        "merchant_phone": merchant_phone,
                        "name": name,
                    },
                    None,
                    "return=representation",
                ),
            ]

            last_exc: Exception | None = None
            for payload_i, params_i, prefer_i in payload_candidates:
                try:
                    rows = _rest_insert("products", payload_i, params=params_i, prefer=prefer_i)
                    product = rows[0] if rows else None
                    if product:
                        break
                except Exception as ex:
                    last_exc = ex
                    continue

            if not product and last_exc:
                raise last_exc

        if not product:
            continue

        stock = _product_stock(product)
        new_stock = stock + int(qty)
        stock_field = "stock_quantity" if product.get("stock_quantity") is not None or product.get("current_stock") is None else "current_stock"
        norm_field = "normalized_name" if product.get("normalized_name") is not None or product.get("name_norm") is None else "name_norm"
        patch_body: dict[str, Any] = {stock_field: new_stock}
        if "unit" in product:
            patch_body["unit"] = unit
        if norm_field in product:
            patch_body[norm_field] = _product_name_norm(name)
        if cost_price_f is not None and "cost_price" in product:
            patch_body["cost_price"] = cost_price_f
        _rest_patch(
            "products",
            {"id": f"eq.{int(product['id'])}"},
            patch_body,
        )

        _rest_insert(
            "inventory_logs",
            {
                "product_id": int(product["id"]),
                "change_type": "RESTOCK",
                "quantity_change": int(qty),
                "notes": notes,
            },
        )

        line_total = float(cost_price_f) * float(qty) if cost_price_f is not None else 0.0
        total += line_total
        line_items.append(
            {
                "product_id": product.get("id"),
                "product_name": product.get("name") or name,
                "quantity": qty,
                "unit": unit,
                "cost_price": cost_price_f,
                "line_total": line_total,
                "stock_before": stock,
                "stock_after": new_stock,
            }
        )

    return {"status": "ok", "total": total, "line_items": line_items}


def process_inventory_transaction(merchant_phone: str, data: dict[str, Any]) -> dict[str, Any]:
    """Process a transaction with optional inventory items.

    - If amount is provided (>0), it is used as final amount.
    - Otherwise, amount is derived from product prices.
    - Stock is updated and inventory_logs are written for CREDIT (sale) items.
    """

    shop_phone = _shop_phone_norm(merchant_phone)
    customer_name = str(data.get("customer_name") or "").strip()
    if not customer_name:
        return {"status": "error", "message": "customer_name is required"}

    customer = get_or_create_customer(shop_phone, customer_name)
    tx_type = str(data.get("transaction_type") or "CREDIT").upper()

    items = data.get("items") or []
    sale_result: dict[str, Any] = {"status": "empty", "total": 0.0, "line_items": []}
    inventory_notice = None
    if items:
        if tx_type == "CREDIT":
            sale_result = apply_inventory_sale(
                shop_phone,
                items,
                notes=f"Sale to {customer_name}",
            )
            if sale_result.get("status") == "error":
                return {
                    "status": "error",
                    "message": "inventory_check_failed",
                    "details": sale_result,
                }
        elif tx_type == "RESTOCK":
            sale_result = apply_inventory_restock(
                shop_phone,
                items,
                notes=f"Restock from {customer_name}",
            )
        else:
            inventory_notice = "items_ignored_for_payment"

    try:
        amt_raw = float(data.get("amount") or 0)
    except Exception:
        amt_raw = 0.0

    total_from_items = float(sale_result.get("total") or 0.0)
    final_amount = amt_raw if amt_raw > 0 else total_from_items

    if tx_type == "RESTOCK":
        signed_amount = 0.0
    elif tx_type == "PAYMENT":
        signed_amount = -abs(final_amount)
    else:
        signed_amount = abs(final_amount)

    if tx_type == "RESTOCK":
        items_summary = ", ".join(
            [
                f"{line.get('quantity')} {line.get('unit')} {line.get('product_name')}"
                for line in sale_result.get("line_items") or []
            ]
        )
        return {
            "status": "ok",
            "customer": customer.get("name"),
            "amount": float(final_amount),
            "items": items_summary or "Manual Entry",
            "new_balance": None,
            "inventory_notice": inventory_notice,
            "entry": None,
            "line_items": sale_result.get("line_items") or [],
        }

    entry = insert_udhaar_entry(
        shop_phone=shop_phone,
        customer_id=int(customer["id"]),
        amount=float(signed_amount),
        transcript=str(data.get("transcript") or "") or None,
        raw_text=str(data.get("raw_text") or "") or None,
        source_message_id=data.get("source_message_id"),
    )

    info = get_customer_total(shop_phone, customer_name)
    new_balance = None
    if info and info.get("status") == "ok":
        new_balance = float(info.get("total") or 0.0)

    items_summary = ", ".join(
        [f"{line.get('quantity')} {line.get('unit')} {line.get('product_name')}" for line in sale_result.get("line_items") or []]
    )

    return {
        "status": "ok",
        "customer": customer.get("name"),
        "amount": float(final_amount),
        "items": items_summary or "Manual Entry",
        "new_balance": new_balance,
        "inventory_notice": inventory_notice,
        "entry": entry,
        "line_items": sale_result.get("line_items") or [],
    }


def get_or_create_customer(shop_phone: str, customer_name: str) -> dict[str, Any]:
    shop_phone = _shop_phone_norm(shop_phone)
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
    customer = rows[0]

    # Ensure secure public link id exists for bill sharing.
    if not customer.get("link_id"):
        link_id = str(uuid.uuid4())
        try:
            _rest_patch("customers", {"id": f"eq.{int(customer['id'])}"}, {"link_id": link_id})
            customer["link_id"] = link_id
        except Exception:
            # Column may not exist until migration runs.
            pass

    return customer


def create_pending_action(shop_phone: str, action_type: str, action_json: dict[str, Any]) -> dict[str, Any]:
    shop_phone = _shop_phone_norm(shop_phone)
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
    shop_phone = _shop_phone_norm(shop_phone)
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
    shop_phone_n = _shop_phone_norm(shop_phone)
    expire_pending_actions(shop_phone_n)
    return get_latest_pending_action(shop_phone_n)


def expire_pending_actions(shop_phone: str) -> None:
    shop_phone = _shop_phone_norm(shop_phone)
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
    shop_phone = _shop_phone_norm(shop_phone)
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

    shop_phone = _shop_phone_norm(shop_phone)
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

    shop_phone = _shop_phone_norm(shop_phone)

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


def get_customer_total(shop_phone: str, customer_name: str) -> dict[str, Any] | None:
    """Returns net udhaar total for a given customer name.

    - Net includes payments (stored as negative amounts)
    - Ignores reversed entries
    - Aggregates across ALL matching customers (in case multiple rows exist for the same name)
    """

    shop_phone = _shop_phone_norm(shop_phone)
    name = (customer_name or "").strip()
    if not name:
        return None

    norm = _name_norm(name)

    # Fetch customers for this shop and fuzzy-match.
    # WHY: Users may say the same name in Hindi/English (e.g., "राजू" vs "Raju") or with minor spelling differences.
    all_customers = _rest_get(
        "customers",
        {
            "select": "id,name,name_norm",
            "shop_phone": f"eq.{shop_phone}",
            "order": "created_at.desc",
            "limit": "500",
        },
    )

    q_norm = norm
    q_roman = _roman_key(name)
    q_key = _ascii_key(name)

    matched: list[dict[str, Any]] = []
    for c in all_customers or []:
        cand_norm = str(c.get("name_norm") or "")
        cand_name = str(c.get("name") or "")
        cand_roman = _roman_key(cand_name)
        cand_key = _ascii_key(cand_name)

        # Strong matches
        if cand_norm == q_norm or (cand_key and q_key and cand_key == q_key):
            matched.append(c)
            continue

        # Fuzzy matches (avoid very short strings)
        if len(q_roman) >= 3 and len(cand_roman) >= 3:
            ratio = difflib.SequenceMatcher(None, q_roman, cand_roman).ratio()
            if ratio >= 0.74:
                matched.append(c)

    # De-dup by id
    seen: set[int] = set()
    customers: list[dict[str, Any]] = []
    for c in matched:
        cid = int(c["id"])
        if cid in seen:
            continue
        seen.add(cid)
        customers.append({"id": cid, "name": c.get("name")})

    if not customers:
        # Suggestions by partial match for UX
        suggestions = [str(c.get("name")) for c in (all_customers or []) if q_norm and q_norm in str(c.get("name_norm") or "")][:5]
        return {"status": "not_found", "suggestions": suggestions}

    customer_ids = sorted({int(c["id"]) for c in customers})
    in_list = ",".join(str(i) for i in customer_ids)

    rows = _rest_get(
        "udhaar_entries",
        {
            "select": "amount,reversed,customer_id",
            "shop_phone": f"eq.{shop_phone}",
            "customer_id": f"in.({in_list})",
            "order": "created_at.desc",
            "limit": "1000",
        },
    )

    total = 0.0
    by_customer: dict[int, float] = {int(c["id"]): 0.0 for c in customers}
    for r in rows or []:
        if r.get("reversed"):
            continue
        amt = float(r["amount"])
        total += amt
        cid = int(r["customer_id"])
        by_customer[cid] = by_customer.get(cid, 0.0) + amt

    breakdown = []
    for c in customers:
        cid = int(c["id"])
        breakdown.append({"id": cid, "name": c.get("name"), "total": by_customer.get(cid, 0.0)})
    breakdown.sort(key=lambda x: abs(float(x.get("total") or 0.0)), reverse=True)

    payload: dict[str, Any] = {"status": "ok", "customers": customers, "breakdown": breakdown, "total": total}
    if len(customers) == 1:
        payload["customer"] = customers[0]
    return payload


def get_recent_entries(shop_phone: str, limit: int = 20) -> list[dict[str, Any]]:
    """Returns recent entries with customer names.

    WHY: Used by the demo recorder page to show a live-updating ledger without requiring Supabase UI.
    """

    shop_phone = _shop_phone_norm(shop_phone)
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


def create_payment_hold(
    *,
    shop_phone: str,
    customer_id: int,
    amount: float,
    due_at: str | None = None,
    hold_reason: str | None = None,
) -> dict[str, Any]:
    shop_phone = _shop_phone_norm(shop_phone)
    try:
        rows = _rest_insert(
            "payment_holds",
            {
                "shop_phone": shop_phone,
                "customer_id": int(customer_id),
                "amount": float(amount),
                "status": "open",
                "due_at": due_at,
                "hold_reason": hold_reason,
            },
        )
        return rows[0]
    except Exception as e:
        if _is_missing_table_error(e):
            raise RuntimeError("Supabase schema missing: run supabase/schema.sql (payment_holds)")
        raise


def list_payment_holds(shop_phone: str, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    shop_phone = _shop_phone_norm(shop_phone)
    limit = max(1, min(int(limit), 200))
    params: dict[str, str] = {
        "select": "id,customer_id,amount,status,hold_reason,due_at,created_at,last_notified_at,notify_count,resolved_at",
        "shop_phone": f"eq.{shop_phone}",
        "order": "created_at.desc",
        "limit": str(limit),
    }
    if status:
        params["status"] = f"eq.{status}"
    try:
        rows = _rest_get("payment_holds", params)
        return _attach_customer_names(shop_phone, rows)
    except Exception as e:
        if _is_missing_table_error(e):
            return []
        raise


def list_due_payment_holds(
    shop_phone: str,
    *,
    cutoff_days: int = 7,
    notify_cooldown_hours: int = 24,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return open holds that are due/old enough AND not recently notified."""

    shop_phone = _shop_phone_norm(shop_phone)

    limit = max(1, min(int(limit), 500))
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = (now - dt.timedelta(days=int(cutoff_days))).isoformat()
    cooldown = (now - dt.timedelta(hours=int(notify_cooldown_hours))).isoformat()

    params: dict[str, str] = {
        "select": "id,customer_id,amount,status,hold_reason,due_at,created_at,last_notified_at,notify_count",
        "shop_phone": f"eq.{shop_phone}",
        "status": "eq.open",
        "order": "created_at.asc",
        "limit": str(limit),
        # due_at <= cutoff OR (due_at IS NULL AND created_at <= cutoff)
        "or": f"(due_at.lte.{cutoff},and(due_at.is.null,created_at.lte.{cutoff}))",
        # last_notified_at IS NULL OR last_notified_at <= cooldown
        "and": f"(or(last_notified_at.is.null,last_notified_at.lte.{cooldown}))",
    }

    try:
        rows = _rest_get("payment_holds", params)
        return _attach_customer_names(shop_phone, rows)
    except Exception as e:
        if _is_missing_table_error(e):
            return []
        raise


def mark_payment_hold_notified(hold_id: int) -> None:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    # Note: PostgREST doesn't support atomic increment without RPC; good enough for hackathon.
    try:
        current = _rest_get(
            "payment_holds",
            {"select": "id,notify_count", "id": f"eq.{int(hold_id)}", "limit": "1"},
        )
    except Exception as e:
        if _is_missing_table_error(e):
            return
        raise
    notify_count = int((current[0] or {}).get("notify_count") or 0) + 1 if current else 1
    _rest_patch(
        "payment_holds",
        {"id": f"eq.{int(hold_id)}"},
        {"last_notified_at": now, "notify_count": notify_count},
    )


def resolve_payment_hold(hold_id: int, *, note: str | None = None) -> None:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        _rest_patch(
            "payment_holds",
            {"id": f"eq.{int(hold_id)}"},
            {"status": "resolved", "resolved_at": now, "resolved_note": note},
        )
    except Exception as e:
        if _is_missing_table_error(e):
            return
        raise


def insert_notification_log(
    *,
    shop_phone: str,
    channel: str,
    notification_type: str,
    entity_table: str,
    entity_id: int,
    message: str,
    status: str = "sent",
    provider_message_id: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    shop_phone = _shop_phone_norm(shop_phone)
    try:
        rows = _rest_insert(
            "notification_log",
            {
                "shop_phone": shop_phone,
                "channel": channel,
                "notification_type": notification_type,
                "entity_table": entity_table,
                "entity_id": int(entity_id),
                "message": message,
                "status": status,
                "provider_message_id": provider_message_id,
                "error": error,
            },
        )
        return rows[0]
    except Exception as e:
        if _is_missing_table_error(e):
            # In demo mode we still want the app to run even if schema isn't updated yet.
            logger.warning("Supabase schema missing: notification_log")
            return {
                "shop_phone": shop_phone,
                "channel": channel,
                "notification_type": notification_type,
                "entity_table": entity_table,
                "entity_id": int(entity_id),
                "message": message,
                "status": "failed",
                "error": "missing_table:notification_log",
            }
        raise


def list_notifications(shop_phone: str, *, limit: int = 50) -> list[dict[str, Any]]:
    shop_phone = _shop_phone_norm(shop_phone)
    limit = max(1, min(int(limit), 200))
    try:
        return _rest_get(
            "notification_log",
            {
                "select": "id,channel,notification_type,entity_table,entity_id,message,status,created_at,error",
                "shop_phone": f"eq.{shop_phone}",
                "order": "created_at.desc",
                "limit": str(limit),
            },
        )
    except Exception as e:
        if _is_missing_table_error(e):
            return []
        raise


def _attach_customer_names(shop_phone: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    shop_phone = _shop_phone_norm(shop_phone)
    if not rows:
        return []
    cust_ids = sorted({int(r["customer_id"]) for r in rows if r.get("customer_id") is not None})
    if not cust_ids:
        return rows
    in_list = ",".join(str(i) for i in cust_ids)
    customers = _rest_get(
        "customers",
        {
            "select": "id,name",
            "shop_phone": f"eq.{shop_phone}",
            "id": f"in.({in_list})",
        },
    )
    id_to_name = {int(c["id"]): c.get("name") for c in (customers or [])}
    for r in rows:
        cid = int(r.get("customer_id") or 0)
        if cid:
            r["customer_name"] = id_to_name.get(cid)
    return rows
