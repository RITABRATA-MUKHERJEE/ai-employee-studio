from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests

from architect import AgentSpec

VAPI_BASE_URL = os.getenv("VAPI_BASE_URL", "https://api.vapi.ai")


class VapiError(RuntimeError):
    pass


def _get_vapi_headers() -> Dict[str, str]:
    api_key = os.getenv("VAPI_API_KEY")
    if not api_key:
        raise VapiError("VAPI_API_KEY is not set. Please add it to your .env or environment.")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def deploy_vapi_assistant(spec: AgentSpec) -> str:
    """Deploy a Vapi.ai assistant from an AgentSpec.

    Sends a POST to https://api.vapi.ai/assistant with the generated system_prompt
    and a high-quality default voice, and returns the assistant_id.
    """
    import json

    url = f"{VAPI_BASE_URL}/assistant"
    headers = _get_vapi_headers()

    # Prefer the spec's suggested voice, but fall back to a known-good default.
    voice_id = spec.voice_id or "jennifer-playht"

    payload: Dict[str, Any] = {
        "name": spec.name,
        "instructions": spec.system_prompt,
        "voice": {
            "id": voice_id,
        },
        # These fields may be adapted to the exact Vapi schema as needed.
        "model": "gpt-4.1-mini",
        "metadata": {
            "tools_required": spec.tools_required,
            "channels": getattr(spec, "channels", []),
            "abilities": getattr(spec, "abilities", []),
            "qualities": getattr(spec, "qualities", []),
        },
    }

    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=20)
    if resp.status_code >= 400:
        raise VapiError(f"Failed to deploy Vapi assistant: {resp.status_code} {resp.text}")

    data = resp.json()
    assistant_id = data.get("id") or data.get("assistant_id")
    if not assistant_id:
        raise VapiError(f"Vapi response missing assistant id: {data}")
    return str(assistant_id)


def get_phone_number(assistant_id: str) -> str:
    """Attach a Vapi-managed phone number to an assistant and return it."""
    import json

    url = f"{VAPI_BASE_URL}/phone-number"
    headers = _get_vapi_headers()

    payload: Dict[str, Any] = {
        "assistant_id": assistant_id,
    }

    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=20)
    if resp.status_code >= 400:
        raise VapiError(f"Failed to get Vapi phone number: {resp.status_code} {resp.text}")

    data = resp.json()
    phone_number = data.get("phone_number") or data.get("number")
    if not phone_number:
        raise VapiError(f"Vapi phone-number response missing phone_number: {data}")
    return str(phone_number)


__all__ = [
    "VapiError",
    "deploy_vapi_assistant",
    "get_phone_number",
]

