from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Sequence

from openai import OpenAI

from architect import AgentSpec, Provider


def _openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing from your .env file.")
    return OpenAI(api_key=api_key)


def _anthropic_client() -> Any:
    try:
        from anthropic import Anthropic  # lazy import
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Claude provider selected but `anthropic` is not installed. Run `python -m pip install anthropic`."
        ) from exc

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is missing from your .env file.")
    return Anthropic(api_key=api_key)


def generate_chat_reply(
    *,
    spec: AgentSpec,
    user_message: str,
    history: Sequence[Dict[str, str]] = (),
    provider: Provider = "openai",
) -> str:
    """Generate a chat reply using the deployed AgentSpec.

    `history` should be a sequence of {"role": "user"|"assistant", "content": "..."}.
    """
    user_message = (user_message or "").strip()
    if not user_message:
        return "Tell me what you’d like help with, and I’ll take it from there."

    # A small wrapper to keep the runtime aligned with the spec’s explicit requirements.
    runtime_preamble = {
        "channels": spec.channels,
        "abilities": spec.abilities,
        "qualities": spec.qualities,
        "tools_required": spec.tools_required,
    }

    if provider == "openai":
        client = _openai_client()
        model = os.getenv("OPENAI_RUNTIME_MODEL", os.getenv("DEFAULT_AGENT_MODEL", "gpt-4.1-mini"))

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": spec.system_prompt},
            {
                "role": "system",
                "content": "Runtime requirements (must comply):\n" + json.dumps(runtime_preamble, indent=2),
            },
        ]
        messages.extend(list(history))
        messages.append({"role": "user", "content": user_message})

        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.4,
        )
        return (resp.choices[0].message.content or "").strip()

    if provider == "claude":
        client = _anthropic_client()
        model = os.getenv("CLAUDE_RUNTIME_MODEL", "claude-3-5-sonnet-latest")

        # Claude expects messages without a "system" role in the list; system is separate.
        anthropic_messages = []
        for m in history:
            role = m.get("role")
            if role in ("user", "assistant"):
                anthropic_messages.append({"role": role, "content": m.get("content", "")})
        anthropic_messages.append({"role": "user", "content": user_message})

        msg = client.messages.create(
            model=model,
            max_tokens=700,
            temperature=0.4,
            system=spec.system_prompt
            + "\n\nRuntime requirements (must comply):\n"
            + json.dumps(runtime_preamble, indent=2),
            messages=anthropic_messages,
        )

        out = ""
        for block in msg.content:
            if getattr(block, "type", None) == "text":
                out += block.text
        return out.strip()

    raise ValueError(f"Unknown provider: {provider}")


__all__ = ["generate_chat_reply"]
