from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from architect import AgentSpec, Provider
from runtime_agent import generate_chat_reply


app = FastAPI(title="Agent Builder Studio — Webhooks")

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


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "registered": len(REGISTRY)}


@app.post("/register")
def register(req: RegisterRequest) -> Dict[str, Any]:
    REGISTRY[req.assistant_id] = req.spec
    return {"ok": True, "assistant_id": req.assistant_id}


@app.post("/webchat/{assistant_id}", response_model=WebchatResponse)
def webchat(assistant_id: str, req: WebchatRequest) -> WebchatResponse:
    spec = REGISTRY.get(assistant_id)
    if not spec:
        raise HTTPException(status_code=404, detail="Unknown assistant_id. Register first.")
    reply = generate_chat_reply(spec=spec, user_message=req.message, provider=req.provider)
    return WebchatResponse(reply=reply)
