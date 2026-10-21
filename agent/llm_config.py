"""Shared LLM configuration and chat-model factory for every agent node.

Set provider, model, credentials, and behavior in the repository-root .env.
Supported providers: groq, openai, anthropic, and openai-compatible.
"""

from __future__ import annotations

import os
from typing import Any

from project_env import load_project_env

load_project_env()


def _float_setting(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    return float(value) if value else default


def _int_setting(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    return int(value) if value else default


LLM_SETTINGS: dict[str, Any] = {
    "provider": os.getenv("LLM_PROVIDER", "").strip().lower() or "groq",
    "model": os.getenv("LLM_MODEL", "").strip() or "openai/gpt-oss-20b",
    "api_key": os.getenv("LLM_API_KEY", "").strip(),
    "base_url": os.getenv("LLM_BASE_URL", "").strip() or None,
    "temperature": _float_setting("LLM_TEMPERATURE", 0.0),
    "timeout": _int_setting("LLM_TIMEOUT_SECONDS", 60),
    "max_retries": _int_setting("LLM_MAX_RETRIES", 2),
    "max_tokens": _int_setting("LLM_MAX_TOKENS", 0) or None,
    "structured_output_method": os.getenv("LLM_STRUCTURED_OUTPUT_METHOD", "").strip()
    or "json_schema",
}

_PURPOSE_TEMPERATURES = {
    "router": _float_setting("LLM_ROUTER_TEMPERATURE", LLM_SETTINGS["temperature"]),
    "specialist": _float_setting("LLM_SPECIALIST_TEMPERATURE", LLM_SETTINGS["temperature"]),
    "summarizer": _float_setting("LLM_SUMMARIZER_TEMPERATURE", LLM_SETTINGS["temperature"]),
}

_PROVIDER_KEY_ENV = {
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openai-compatible": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


def configured_api_key() -> str:
    """Return the explicit key or the selected provider's standard key."""
    provider = LLM_SETTINGS["provider"]
    provider_key_name = _PROVIDER_KEY_ENV.get(provider)
    return LLM_SETTINGS["api_key"] or (os.getenv(provider_key_name, "") if provider_key_name else "")


def create_chat_model(purpose: str = "specialist", **overrides: Any):
    """Create a configured LangChain chat model for the requested agent role."""
    provider = LLM_SETTINGS["provider"]
    if provider not in _PROVIDER_KEY_ENV:
        supported = ", ".join(_PROVIDER_KEY_ENV)
        raise ValueError(f"Unsupported LLM_PROVIDER '{provider}'. Choose: {supported}.")

    api_key = configured_api_key()
    if not api_key:
        key_name = _PROVIDER_KEY_ENV[provider]
        raise ValueError(
            f"No API key is configured for LLM_PROVIDER '{provider}'. "
            f"Set LLM_API_KEY or {key_name} in the repository-root .env."
        )
    kwargs: dict[str, Any] = {
        "model": LLM_SETTINGS["model"],
        "temperature": _PURPOSE_TEMPERATURES.get(purpose, LLM_SETTINGS["temperature"]),
        "timeout": LLM_SETTINGS["timeout"],
        "max_retries": LLM_SETTINGS["max_retries"],
    }
    if api_key:
        kwargs["api_key"] = api_key
    if LLM_SETTINGS["base_url"]:
        kwargs["base_url"] = LLM_SETTINGS["base_url"]
    if LLM_SETTINGS["max_tokens"] is not None:
        kwargs["max_tokens"] = LLM_SETTINGS["max_tokens"]
    kwargs.update(overrides)

    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(**kwargs)
    if provider in {"openai", "openai-compatible"}:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(**kwargs)
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(**kwargs)


def create_structured_model(schema: type, purpose: str = "router"):
    """Build structured output using the provider method selected in .env."""
    model = create_chat_model(purpose)
    return model.with_structured_output(
        schema,
        method=LLM_SETTINGS["structured_output_method"],
    )
