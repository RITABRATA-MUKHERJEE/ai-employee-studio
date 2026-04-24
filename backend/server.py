from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from architect import AgentSpec, Provider
from runtime_agent import generate_chat_reply
from supabase_client import get_telegram_chat_link, upsert_telegram_chat_link

load_dotenv()
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# In-memory registry for local dev. For production, back this by Supabase/Redis.
REGISTRY: Dict[str, AgentSpec] = {}


class RegisterRequest(BaseModel):
    assistant_id: str
    spec: AgentSpec


class WebchatRequest(BaseModel):
    message: str
    provider: Provider = "openai"


class WebchatResponse(BaseModel):
    reply: str


@app.get("/")
def health() -> Dict[str, str]:
    return {"status": "running"}


@app.get("/health")
def health_detail() -> Dict[str, Any]:
    return {"ok": True, "registered": len(REGISTRY)}


@app.post("/register")
def register(req: RegisterRequest) -> Dict[str, Any]:
    REGISTRY[req.assistant_id] = req.spec
    logger.info("Registered assistant_id=%s", req.assistant_id)
    return {"ok": True, "assistant_id": req.assistant_id}


@app.post("/webchat/{assistant_id}", response_model=WebchatResponse)
def webchat(assistant_id: str, req: WebchatRequest) -> WebchatResponse:
    spec = REGISTRY.get(assistant_id)
    if not spec:
        raise HTTPException(status_code=404, detail="Unknown assistant_id. Register first.")
    reply = generate_chat_reply(spec=spec, user_message=req.message, provider=req.provider)
    return WebchatResponse(reply=reply)


@app.post("/telegram")
async def telegram_webhook(request: Request) -> Dict[str, Any]:
    update = await request.json()
    token = os.getenv("TELEGRAM_MASTER_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise HTTPException(status_code=500, detail="TELEGRAM_MASTER_BOT_TOKEN is not set.")

    message = (update.get("message") or {}).get("text")
    chat_id = (update.get("message") or {}).get("chat", {}).get("id")
    if not message or not chat_id:
        return {"ok": True, "ignored": True}

    chat_id_str = str(chat_id)

    # One-click flow: deep link is https://t.me/<master_bot>?start=assistant_<assistant_id>
    if message.startswith("/start"):
        parts = message.split(maxsplit=1)
        payload = parts[1] if len(parts) > 1 else ""
        if payload.startswith("assistant_"):
            assistant_id = payload.removeprefix("assistant_").strip()
            if assistant_id and assistant_id in REGISTRY:
                upsert_telegram_chat_link(chat_id=chat_id_str, assistant_id=assistant_id)
                resp = requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": "Connected successfully. You can now chat with your AI employee here.",
                    },
                    timeout=15,
                )
                if resp.status_code >= 400:
                    raise HTTPException(status_code=500, detail=f"Telegram sendMessage failed: {resp.text}")
                return {"ok": True, "linked": True, "assistant_id": assistant_id}

        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": "This chat is not linked yet. Open Telegram from your deploy link in Streamlit first.",
            },
            timeout=15,
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=500, detail=f"Telegram sendMessage failed: {resp.text}")
        return {"ok": True, "linked": False}

    assistant_id = get_telegram_chat_link(chat_id=chat_id_str)
    if not assistant_id:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": "No AI employee linked to this chat. Use the deploy link from Streamlit first.",
            },
            timeout=15,
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=500, detail=f"Telegram sendMessage failed: {resp.text}")
        return {"ok": True, "linked": False}

    spec = REGISTRY.get(assistant_id)
    if not spec:
        raise HTTPException(status_code=404, detail="Linked assistant_id is not registered on webhook server.")

    reply = generate_chat_reply(spec=spec, user_message=message, provider="openai")
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": reply},
        timeout=15,
    )
    if resp.status_code >= 400:
        raise HTTPException(status_code=500, detail=f"Telegram sendMessage failed: {resp.text}")
    return {"ok": True}


@app.post("/telegram/{assistant_id}")
def telegram_webhook_legacy(assistant_id: str, update: Dict[str, Any]) -> Dict[str, Any]:
    """Backward-compatible endpoint for old setup."""
    token = os.getenv("TELEGRAM_MASTER_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise HTTPException(status_code=500, detail="TELEGRAM_MASTER_BOT_TOKEN is not set.")

    spec = REGISTRY.get(assistant_id)
    if not spec:
        raise HTTPException(status_code=404, detail="Unknown assistant_id. Register first.")

    message = (update.get("message") or {}).get("text")
    chat_id = (update.get("message") or {}).get("chat", {}).get("id")
    if not message or not chat_id:
        return {"ok": True, "ignored": True}

    reply = generate_chat_reply(spec=spec, user_message=message, provider="openai")
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": reply},
        timeout=15,
    )
    if resp.status_code >= 400:
        raise HTTPException(status_code=500, detail=f"Telegram sendMessage failed: {resp.text}")
    return {"ok": True, "legacy": True}
