from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from supabase import Client, create_client


class Booking(BaseModel):
    customer_name: str
    phone_number: Optional[str] = None
    party_size: int
    datetime: str = Field(..., description="ISO 8601 datetime string")
    notes: Optional[str] = None


class DeployedAgent(BaseModel):
    assistant_id: str
    name: str


def get_supabase_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_PUBLISHABLE_KEY")
    if not url or not key:
        raise RuntimeError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY (or SUPABASE_PUBLISHABLE_KEY)."
        )
    return create_client(url, key)


def create_booking(booking: Booking) -> Dict[str, Any]:
    """Insert a booking into the mock `bookings` table."""
    supabase = get_supabase_client()
    # Expects a `bookings` table with matching columns.
    res = supabase.table("bookings").insert(booking.model_dump()).execute()
    if getattr(res, "error", None):
        raise RuntimeError(f"Supabase booking insert failed: {res.error}")
    return getattr(res, "data", res)


def list_bookings(limit: int = 50) -> List[Dict[str, Any]]:
    supabase = get_supabase_client()
    res = supabase.table("bookings").select("*").order("datetime", desc=True).limit(limit).execute()
    if getattr(res, "error", None):
        raise RuntimeError(f"Supabase booking query failed: {res.error}")
    return list(getattr(res, "data", res))


def create_deployed_agent(assistant_id: str, business_name: str) -> Dict[str, Any]:
    """Insert a record into the `deployed_agents` table."""
    supabase = get_supabase_client()
    payload = DeployedAgent(assistant_id=assistant_id, name=business_name).model_dump()
    res = supabase.table("deployed_agents").insert(payload).execute()
    if getattr(res, "error", None):
        raise RuntimeError(f"Supabase deployed_agents insert failed: {res.error}")
    return getattr(res, "data", res)


def ensure_deployed_agents_table() -> None:
    """Best-effort table bootstrap.

    We first probe the table. If missing, we attempt a SQL RPC if available.
    If RPC is not available in the project, we raise with the exact SQL to run manually.
    """
    supabase = get_supabase_client()
    create_sql = """
create table if not exists deployed_agents (
  id uuid default gen_random_uuid() primary key,
  assistant_id text,
  name text,
  created_at timestamp default now()
);
""".strip()

    try:
        supabase.table("deployed_agents").select("assistant_id").limit(1).execute()
        return
    except Exception:
        pass

    # Try common SQL RPC helper names used in many projects.
    for fn_name in ("exec_sql", "execute_sql", "run_sql"):
        try:
            supabase.rpc(fn_name, {"sql": create_sql}).execute()
            return
        except Exception:
            continue

    raise RuntimeError(
        "Table `deployed_agents` appears missing and SQL RPC is unavailable. "
        f"Run this SQL in Supabase SQL Editor:\n\n{create_sql}"
    )


def list_deployed_agents(limit: int = 100) -> List[Dict[str, Any]]:
    supabase = get_supabase_client()
    res = (
        supabase.table("deployed_agents")
        .select("assistant_id,name,created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    if getattr(res, "error", None):
        raise RuntimeError(f"Supabase deployed_agents query failed: {res.error}")
    return list(getattr(res, "data", res))


__all__ = [
    "Booking",
    "DeployedAgent",
    "get_supabase_client",
    "create_booking",
    "list_bookings",
    "create_deployed_agent",
    "ensure_deployed_agents_table",
    "list_deployed_agents",
]

