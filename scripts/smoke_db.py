from __future__ import annotations

import os

import httpx
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY")

    if not url or not key:
        raise SystemExit("Missing SUPABASE_URL and a SUPABASE key env var")

    rest = url.rstrip("/") + "/rest/v1/customers"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }

    # Simple read proves: schema exists, privileges OK, PostgREST reachable.
    r = httpx.get(rest, params={"select": "id,name", "limit": "1"}, headers=headers, timeout=20)
    print("status:", r.status_code)

    if r.status_code == 404 and "PGRST205" in r.text:
        print(
            "\nDB NOT READY: Supabase cannot find table public.customers.\n"
            "Action: In Supabase SQL Editor, run supabase/schema.sql once, then wait ~30s and re-run this script.\n"
        )
        print("raw:", r.text[:500])
        raise SystemExit(2)

    if r.status_code >= 400:
        print("raw:", r.text[:500])
        r.raise_for_status()

    print("DB READY: PostgREST reachable and customers table exists.")
    print("body:", r.text[:500])


if __name__ == "__main__":
    main()
