import os
from contextvars import ContextVar
from typing import Optional
from langchain_google_genai import ChatGoogleGenerativeAI

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Per-request key — set by API layer before running the graph
_google_api_key: ContextVar[Optional[str]] = ContextVar("google_api_key", default=None)


def set_api_key(key: str) -> None:
    """Bind a Google API key to the current async context (propagates into thread executors)."""
    _google_api_key.set(key)


def make_llm(temperature: float = 0.3) -> ChatGoogleGenerativeAI:
    key = _google_api_key.get() or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError(
            "No Google API key available. Pass X-Google-API-Key header or set GOOGLE_API_KEY env var."
        )
    return ChatGoogleGenerativeAI(
        model=GEMINI_MODEL,
        google_api_key=key,
        temperature=temperature,
    )
