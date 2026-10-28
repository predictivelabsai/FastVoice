"""LLM provider factory (LangChain): Google Gemini, Mistral, or an offline mock."""

from __future__ import annotations

import os
import re
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from .config import Settings, has_key

LLM_KEYS = {
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "mistral": ("MISTRAL_API_KEY",),
    "mock": (),
}


class ExtractiveMockLLM:
    """Deterministic offline stand-in for a chat model.

    Answers with the first sentences of the retrieved context so the whole
    pipeline (and tests) run without network or keys. Mimics the LangChain
    ``invoke(messages) -> AIMessage`` interface.
    """

    name = "mock"

    def invoke(self, messages: list[BaseMessage], **_: Any) -> AIMessage:
        human = next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), "")
        ctx = re.findall(r"<šaltinis[^>]*>\s*(.*?)\s*</šaltinis>", str(human), flags=re.S)
        if not ctx:
            return AIMessage(content="Šiuo klausimu patikimos informacijos neturiu.")
        body = ctx[0].strip().split("\n", 1)
        text = body[1] if len(body) > 1 else body[0]  # drop the heading line
        sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
        answer = " ".join(s for s in sentences[:3] if s)
        return AIMessage(content=answer + " [1]")


def available_llm_providers() -> list[str]:
    return [p for p, keys in LLM_KEYS.items() if not keys or has_key(*keys)]


def resolve_llm_provider(settings: Settings, requested: str | None = None) -> str:
    p = (requested or settings.get("llm.provider") or "auto").lower()
    if p != "auto":
        if p not in LLM_KEYS:
            raise ValueError(f"Unknown LLM provider '{p}'. Choose from {sorted(LLM_KEYS)}")
        if LLM_KEYS[p] and not has_key(*LLM_KEYS[p]):
            raise RuntimeError(f"LLM provider '{p}' selected but none of {LLM_KEYS[p]} is set")
        return p
    for cand in settings.get("llm.fallback_order", ["gemini", "mistral", "mock"]):
        if cand in available_llm_providers():
            return cand
    return "mock"


def make_llm(settings: Settings, provider: str | None = None, model: str | None = None):
    """Return (provider_name, model_name, chat_model)."""
    p = resolve_llm_provider(settings, provider)
    temperature = float(settings.get("llm.temperature", 0.1))
    max_tokens = int(settings.get("llm.max_output_tokens", 600))
    timeout = float(settings.get("llm.timeout_s", 30))
    m = model or settings.get(f"llm.models.{p}")
    if p == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        extra = {}
        tb = settings.get("llm.gemini_thinking_budget", 0)
        if tb is not None and str(m).startswith("gemini-2.5"):
            extra["thinking_budget"] = int(tb)  # 0 = no thinking: lower latency for a phone line
        return p, m, ChatGoogleGenerativeAI(
            model=m, google_api_key=key, temperature=temperature,
            max_output_tokens=max_tokens, timeout=timeout, max_retries=2, **extra,
        )
    if p == "mistral":
        from langchain_mistralai import ChatMistralAI

        return p, m, ChatMistralAI(
            model=m, api_key=os.environ["MISTRAL_API_KEY"], temperature=temperature,
            max_tokens=max_tokens, timeout=int(timeout), max_retries=2,
        )
    return "mock", "extractive", ExtractiveMockLLM()


def as_messages(system: str, user: str) -> list[BaseMessage]:
    return [SystemMessage(content=system), HumanMessage(content=user)]
