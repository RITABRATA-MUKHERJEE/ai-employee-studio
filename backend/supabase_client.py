from __future__ import annotations

import os
from typing import Optional

from supabase import Client, create_client


def get_supabase_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = (
        os.getenv("SUPABASE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or os.getenv("SUPABASE_PUBLISHABLE_KEY")
    )
    if not url or not key:
        raise RuntimeError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY "
            "(or SUPABASE_ANON_KEY / SUPABASE_PUBLISHABLE_KEY)."
        )
    return create_client(url, key)


def ensure_telegram_chat_links_table() -> None:
    """Best-effort bootstrap for master-bot chat routing."""
    supabase = get_supabase_client()
    create_sql = """
create table if not exists telegram_chat_links (
  chat_id text primary key,
  assistant_id text not null,
  updated_at timestamp default now()
);
""".strip()

    try:
        supabase.table("telegram_chat_links").select("chat_id").limit(1).execute()
        return
    except Exception:
        pass

    for fn_name in ("exec_sql", "execute_sql", "run_sql"):
        try:
            supabase.rpc(fn_name, {"sql": create_sql}).execute()
            return
        except Exception:
            continue

    raise RuntimeError(
        "Table `telegram_chat_links` appears missing and SQL RPC is unavailable. "
        f"Run this SQL in Supabase SQL Editor:\n\n{create_sql}"
    )


def upsert_telegram_chat_link(chat_id: str, assistant_id: str) -> None:
    supabase = get_supabase_client()
    ensure_telegram_chat_links_table()
    payload = {
        "chat_id": str(chat_id),
        "assistant_id": assistant_id,
    }
    res = supabase.table("telegram_chat_links").upsert(payload).execute()
    if getattr(res, "error", None):
        raise RuntimeError(f"Supabase telegram_chat_links upsert failed: {res.error}")


def get_telegram_chat_link(chat_id: str) -> Optional[str]:
    supabase = get_supabase_client()
    ensure_telegram_chat_links_table()
    res = (
        supabase.table("telegram_chat_links")
        .select("assistant_id")
        .eq("chat_id", str(chat_id))
        .limit(1)
        .execute()
    )
    if getattr(res, "error", None):
        raise RuntimeError(f"Supabase telegram_chat_links query failed: {res.error}")
    rows = list(getattr(res, "data", res))
    if not rows:
        return None
    return str(rows[0].get("assistant_id"))


__all__ = [
    "get_supabase_client",
    "ensure_telegram_chat_links_table",
    "upsert_telegram_chat_link",
    "get_telegram_chat_link",
]
