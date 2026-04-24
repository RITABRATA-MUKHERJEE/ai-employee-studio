from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

from openai import OpenAI
from pydantic import BaseModel, Field


Provider = Literal["openai", "claude"]


class AgentSpec(BaseModel):
    """Deployment-ready identity spec for a voice/web agent."""

    name: str = Field(..., description="Human-friendly agent name, e.g. 'Sarah — Sushi Receptionist'.")
    system_prompt: str = Field(
        ...,
        description=(
            "Prompt written as instructions to the assistant. Must start like "
            "'You are Sarah, the receptionist for ...' and include concrete business details."
        ),
    )
    voice_id: str = Field(..., description="High-quality voice ID, e.g. 'jennifer-playht' or 'shimmer-openai'.")
    tools_required: List[str] = Field(default_factory=list, description="List of tool names the agent should have.")
    channels: List[str] = Field(
        default_factory=list,
        description="Deployment channels the user wants (e.g. ['phone','whatsapp','telegram','instagram','linkedin','web']).",
    )
    abilities: List[str] = Field(
        default_factory=list,
        description="Concrete abilities requested (e.g. ['outbound_calls','lead_qualification','appointment_booking']).",
    )
    qualities: List[str] = Field(
        default_factory=list,
        description="Personality/behavior traits (e.g. ['friendly','calm','concise']).",
    )


def _openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing from your .env file.")
    return OpenAI(api_key=api_key)


def _anthropic_client() -> Any:
    try:
        from anthropic import Anthropic  # lazy import so OpenAI-only installs still work
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Claude provider selected but `anthropic` is not installed. "
            "Run: `python -m pip install anthropic` (or reinstall from requirements.txt)."
        ) from exc

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is missing from your .env file.")
    return Anthropic(api_key=api_key)


def _agent_spec_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "system_prompt": {"type": "string"},
            "voice_id": {"type": "string"},
            "tools_required": {"type": "array", "items": {"type": "string"}},
            "channels": {"type": "array", "items": {"type": "string"}},
            "abilities": {"type": "array", "items": {"type": "string"}},
            "qualities": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["name", "system_prompt", "voice_id", "tools_required", "channels", "abilities", "qualities"],
        "additionalProperties": False,
    }


def _compose_architect_input(
    description: str,
    extracted_text: str,
    file_summaries: Sequence[str],
) -> str:
    description = description.strip()
    extracted_text = (extracted_text or "").strip()
    files_block = "\n".join(f"- {s}" for s in file_summaries if s)

    parts = [
        "BUSINESS BRIEF (owner input):",
        description,
    ]
    if files_block:
        parts.extend(["", "UPLOADED FILES:", files_block])
    if extracted_text:
        parts.extend(["", "EXTRACTED REFERENCE CONTENT (use as ground truth):", extracted_text])

    return "\n".join(parts).strip()


def _format_preferences(preferences: Optional[Dict[str, Any]]) -> str:
    if not preferences:
        return ""
    try:
        return json.dumps(preferences, indent=2, ensure_ascii=False)
    except Exception:
        return str(preferences)


def _generate_agent_spec_openai(
    architect_input: str,
    images: Sequence[Tuple[str, bytes]],
) -> AgentSpec:
    client = _openai_client()
    model = os.getenv("OPENAI_ARCHITECT_MODEL", os.getenv("DEFAULT_AGENT_MODEL", "gpt-4.1-mini"))

    schema = _agent_spec_schema()

    system = (
        "You are a Senior AI Architect. Convert the provided business brief into a STRICT JSON object.\n"
        "Rules:\n"
        "- The JSON MUST match the provided schema exactly.\n"
        "- `system_prompt` MUST begin with: 'You are <NAME>,' and be written as instructions to the assistant.\n"
        "- Include specific business details from the brief (industry, location, hours/policies if provided, tasks).\n"
        "- Pick a high-quality `voice_id`: prefer 'jennifer-playht' or 'shimmer-openai'.\n"
        "- `tools_required` should be a short list of tool names like 'booking_tool', 'faq_tool', 'billing_tool'.\n"
        "- Use the OWNER SELECTED PREFERENCES section to fill `channels`, `abilities`, and `qualities`.\n"
        "Return ONLY JSON."
    )

    content: List[Dict[str, Any]] = [{"type": "input_text", "text": architect_input}]
    # If images were uploaded, attach them so the model can see visual content (menus, brochures, etc).
    for _, img_bytes in images:
        import base64

        b64 = base64.b64encode(img_bytes).decode("utf-8")
        content.append({"type": "input_image", "image_url": f"data:image/png;base64,{b64}"})

    # Use Chat Completions JSON mode for broad SDK compatibility.
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": architect_input},
    ]
    if images:
        # If images exist, append a short marker so text-only fallback still accounts for them.
        image_names = ", ".join(name for name, _ in images)
        messages.append(
            {
                "role": "user",
                "content": (
                    "Referenced uploaded images are part of the brief and should influence the spec: "
                    f"{image_names}"
                ),
            }
        )

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.5,
    )

    raw = resp.choices[0].message.content or "{}"
    data = json.loads(raw)
    # Enforce schema with Pydantic and a light normalization pass.
    if "channels" not in data:
        data["channels"] = []
    if "abilities" not in data:
        data["abilities"] = []
    if "qualities" not in data:
        data["qualities"] = []
    return AgentSpec(**data)


def _generate_agent_spec_claude(architect_input: str) -> AgentSpec:
    client = _anthropic_client()
    model = os.getenv("CLAUDE_ARCHITECT_MODEL", "claude-3-5-sonnet-latest")

    # Claude doesn't have the same strict json_schema mode in the same way; we enforce via
    # prompt + validation and do one automatic repair attempt if needed.
    schema = _agent_spec_schema()

    system = (
        "You are a Senior AI Architect. Return ONLY a JSON object matching this JSON Schema:\n"
        f"{json.dumps(schema, indent=2)}\n\n"
        "Rules:\n"
        "- `system_prompt` MUST begin with: 'You are <NAME>,' and include specific details from the brief.\n"
        "- `voice_id` should be 'jennifer-playht' or 'shimmer-openai' unless the brief implies otherwise.\n"
        "- `tools_required` must be an array of tool names.\n"
        "Return ONLY JSON (no markdown, no commentary)."
    )

    msg = client.messages.create(
        model=model,
        max_tokens=1200,
        temperature=0.5,
        system=system,
        messages=[{"role": "user", "content": architect_input}],
    )

    text = ""
    for block in msg.content:
        if getattr(block, "type", None) == "text":
            text += block.text

    try:
        data = json.loads(text)
        return AgentSpec(**data)
    except Exception:
        # Repair attempt: ask Claude to output valid JSON only.
        repair = client.messages.create(
            model=model,
            max_tokens=900,
            temperature=0.0,
            system="Output only valid JSON. No markdown. No explanations.",
            messages=[
                {"role": "user", "content": "Fix this to match the schema exactly and output only JSON:\n\n" + text}
            ],
        )
        repair_text = ""
        for block in repair.content:
            if getattr(block, "type", None) == "text":
                repair_text += block.text
        data = json.loads(repair_text)
        return AgentSpec(**data)


def generate_agent_spec(
    description: str,
    *,
    provider: Provider = "openai",
    extracted_text: str = "",
    file_summaries: Optional[Sequence[str]] = None,
    images: Optional[Sequence[Tuple[str, bytes]]] = None,
    preferences: Optional[Dict[str, Any]] = None,
) -> AgentSpec:
    """Convert a business brief (+ optional uploaded docs) into a structured AgentSpec."""
    description = (description or "").strip()
    if not description:
        raise ValueError("Business description cannot be empty.")

    file_summaries = list(file_summaries or [])
    images = list(images or [])

    architect_input = _compose_architect_input(description, extracted_text, file_summaries)
    prefs = _format_preferences(preferences)
    if prefs:
        architect_input = architect_input + "\n\nOWNER SELECTED PREFERENCES (treat as requirements):\n" + prefs

    if provider == "openai":
        return _generate_agent_spec_openai(architect_input, images)
    if provider == "claude":
        return _generate_agent_spec_claude(architect_input)

    raise ValueError(f"Unknown provider: {provider}")


__all__ = ["AgentSpec", "Provider", "generate_agent_spec"]
