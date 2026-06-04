#!/usr/bin/env python3
import os
import json
import secrets
import traceback
import asyncio
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Security, Depends
from fastapi.security import APIKeyHeader
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from aftermath.graph import graph
from aftermath.state import ALL_DOMAINS
from aftermath.llm import make_llm, set_api_key
from aftermath.prompts import DETAIL_SYSTEM, DETAIL_USER, KEY_TAKEAWAYS_SYSTEM, KEY_TAKEAWAYS_USER

# ── Auth: Aftermath API key ───────────────────────────────────────────────────

AFTERMATH_API_KEY = os.getenv("AFTERMATH_API_KEY")
if not AFTERMATH_API_KEY:
    raise RuntimeError("AFTERMATH_API_KEY not set in environment")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
google_key_header = APIKeyHeader(name="X-Google-API-Key", auto_error=False)


def verify_api_key(key: Optional[str] = Security(api_key_header)):
    if not key:
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "MISSING_API_KEY",
                "message": "No API key provided.",
                "hint": "Add header: X-API-Key: <your key>",
            },
        )
    if not secrets.compare_digest(key, AFTERMATH_API_KEY):
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "INVALID_API_KEY",
                "message": "API key is incorrect.",
                "hint": "Check your AFTERMATH_API_KEY value.",
            },
        )
    return key


def resolve_google_key(user_key: Optional[str] = Security(google_key_header)) -> str:
    """
    BYOK: prefer caller-supplied X-Google-API-Key header.
    Falls back to server GOOGLE_API_KEY env var (optional operator convenience).
    """
    key = user_key or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "MISSING_GOOGLE_KEY",
                "message": "No Google (Gemini) API key provided.",
                "hint": (
                    "Pass your key via header: X-Google-API-Key: AIza... "
                    "Get one free at https://aistudio.google.com/apikey"
                ),
            },
        )
    return key


# ── Rate limiting ─────────────────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Aftermath API",
    description=(
        "Causal intelligence graph over a trigger event.\n\n"
        "**Authentication:** two headers required on every call:\n"
        "- `X-API-Key` — your Aftermath service key\n"
        "- `X-Google-API-Key` — your own Gemini API key (BYOK). "
        "Get one free at https://aistudio.google.com/apikey"
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
_ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key", "X-Google-API-Key"],
)

app.state.limiter = limiter


# ── Error handlers ────────────────────────────────────────────────────────────

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    retry_after = getattr(exc, "retry_after", 60)
    return JSONResponse(
        status_code=429,
        content={
            "error_code": "RATE_LIMIT_EXCEEDED",
            "message": f"Too many requests. Limit: {exc.detail}.",
            "retry_after_seconds": retry_after,
            "hint": "Slow down — wait before sending the next request.",
        },
        headers={"Retry-After": str(retry_after)},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = [
        {"field": " → ".join(str(l) for l in e["loc"]), "issue": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error_code": "INVALID_REQUEST",
            "message": "Request body failed validation.",
            "errors": errors,
        },
    )


# ── Request / Response models ─────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    topic: str = Field(..., min_length=5, max_length=500, description="Trigger event to analyze")
    domains: Optional[list[str]] = Field(
        default=None,
        description="Subset of domains to analyze. Omit for all domains.",
    )

    @field_validator("domains")
    @classmethod
    def validate_domains(cls, v):
        if v is None:
            return v
        invalid = [d for d in v if d.upper() not in ALL_DOMAINS]
        if invalid:
            raise ValueError(f"Unknown domains: {invalid}. Valid: {ALL_DOMAINS}")
        seen = set()
        result = []
        for d in v:
            u = d.upper()
            if u not in seen:
                seen.add(u)
                result.append(u)
        if not result:
            raise ValueError("domains list is empty")
        return result


class ErrorResponse(BaseModel):
    detail: str


class NodeSummary(BaseModel):
    entity: str
    domain: str
    what: str
    how: str
    confidence: str
    confidence_pct: int = 0
    timeframe: str = ""


class SurpriseLink(BaseModel):
    from_entity: str
    to_entity: str
    verb: str
    mechanism: str


class KeyTakeawaysRequest(BaseModel):
    trigger_event: str = Field(..., min_length=5, max_length=500)
    nodes: list[NodeSummary] = Field(..., min_length=1)
    surprise_links: list[SurpriseLink] = Field(default=[])
    highlight_insights: list[str] = Field(default=[])
    causal_order: list[str] = Field(default=[])


class DetailRequest(BaseModel):
    trigger_event: str = Field(..., min_length=5, max_length=500, description="Original trigger event")
    domain: str = Field(..., description="Domain the entity belongs to (e.g. FINANCE)")
    entity: str = Field(..., min_length=1, max_length=200, description="Entity name from the causal graph")
    what: str = Field(default="", max_length=300, description="What happened to this entity")
    how: str = Field(default="", max_length=200, description="Causal mechanism / transmission channel")
    confidence: str = Field(default="Established", description="Established | Contested | Speculative")
    confidence_pct: int = Field(default=0, ge=0, le=100)
    timeframe: str = Field(default="", max_length=100)
    counter_narrative: Optional[str] = Field(default=None, max_length=500)

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v):
        u = v.strip().upper()
        if u not in ALL_DOMAINS:
            raise ValueError(f"Unknown domain '{v}'. Valid: {ALL_DOMAINS}")
        return u

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v):
        valid = {"Established", "Contested", "Speculative"}
        if v not in valid:
            raise ValueError(f"confidence must be one of: {valid}")
        return v


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "byok": "X-Google-API-Key header required"}


@app.get("/domains", tags=["meta"])
def list_domains():
    """Return all valid domain names for the domains parameter."""
    return {"domains": ALL_DOMAINS}


@app.post(
    "/analyze",
    tags=["analysis"],
    responses={
        200: {"description": "Causal graph for the trigger event"},
        400: {"model": ErrorResponse, "description": "Invalid event or bad input"},
        401: {"model": ErrorResponse, "description": "Unauthorized / missing key"},
        429: {"description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    },
)
@limiter.limit("10/minute")
async def analyze(
    request: Request,
    body: AnalyzeRequest,
    _: str = Depends(verify_api_key),
    google_key: str = Depends(resolve_google_key),
):
    set_api_key(google_key)

    selected = body.domains or ALL_DOMAINS
    trigger_event = " ".join(body.topic.strip().split())[:500]

    initial_state = {
        "trigger_event": trigger_event,
        "selected_domains": selected,
        "google_api_key": google_key,
        "acknowledged_query": "",
        "orchestrator_briefings": {},
        "domain_outputs": [],
        "final_graph": None,
    }

    debug = os.getenv("AFTERMATH_DEBUG", "0") == "1"

    def _run_graph():
        final = None
        for snapshot in graph.stream(
            initial_state,
            stream_mode="values",
            config={"max_concurrency": 3},
        ):
            final = snapshot
        return final

    try:
        loop = asyncio.get_event_loop()
        final_state = await loop.run_in_executor(None, _run_graph)
    except Exception as e:
        traceback.print_exc()
        err_type = type(e).__name__
        err_str = str(e).lower()

        if "ratelimit" in err_type.lower() or "rate_limit" in err_type.lower() or "429" in err_str or "rate limit" in err_str:
            raise HTTPException(
                status_code=429,
                detail={
                    "error_code": "LLM_RATE_LIMIT",
                    "message": "Gemini API rate limit hit.",
                    "hint": "Wait 30–60 seconds and retry. Upgrade your Google AI plan for higher limits.",
                    "retry_after_seconds": 60,
                },
            )

        if "authentication" in err_str or "api key" in err_str or "unauthorized" in err_str or "401" in err_str:
            raise HTTPException(
                status_code=502,
                detail={
                    "error_code": "LLM_AUTH_FAILED",
                    "message": "Gemini API key rejected by Google.",
                    "hint": "Verify your X-Google-API-Key is valid at aistudio.google.com.",
                },
            )

        if "timeout" in err_str or "timed out" in err_str:
            raise HTTPException(
                status_code=504,
                detail={
                    "error_code": "LLM_TIMEOUT",
                    "message": "Analysis timed out waiting for the LLM.",
                    "hint": "Try a shorter query or fewer domains. Retry in a moment.",
                },
            )

        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "PIPELINE_ERROR",
                "message": "Analysis pipeline failed.",
                "detail": f"{err_type}: {e}",
            },
        )

    if final_state is None:
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "EMPTY_STATE",
                "message": "Pipeline produced no output.",
                "hint": "Retry the request.",
            },
        )

    if not final_state.get("is_valid_event", True):
        raise HTTPException(
            status_code=400,
            detail={
                "message": final_state.get("invalid_message", "Invalid trigger event"),
                "acknowledged_query": final_state.get("acknowledged_query", ""),
            },
        )

    fg = final_state.get("final_graph")
    if fg is None:
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "SYNTHESIS_FAILED",
                "message": "Synthesizer produced no causal graph.",
                "hint": "Retry. If persistent, narrow the domains or rephrase the event.",
            },
        )

    return {
        "trigger_event": fg.trigger_event,
        "acknowledged_query": final_state.get("acknowledged_query", fg.trigger_event),
        "domains_analyzed": selected,
        "nodes": [n.model_dump() for n in fg.nodes],
        "edges": [e.model_dump() for e in fg.edges],
        "surprise_links": [e.model_dump() for e in fg.surprise_links],
        "highlight_insights": fg.highlight_insights,
        "causal_order": fg.causal_order,
    }


@app.post(
    "/key-takeaways",
    tags=["analysis"],
    responses={
        200: {"description": "Executive brief distilled from causal graph"},
        401: {"model": ErrorResponse, "description": "Unauthorized / missing key"},
        429: {"description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    },
)
@limiter.limit("20/minute")
async def key_takeaways(
    request: Request,
    body: KeyTakeawaysRequest,
    _: str = Depends(verify_api_key),
    google_key: str = Depends(resolve_google_key),
):
    from langchain_core.messages import SystemMessage, HumanMessage

    set_api_key(google_key)
    trigger_event = " ".join(body.trigger_event.strip().split())[:500]

    nodes_text = "\n".join(
        f"- [{n.domain}] {n.entity}: {n.what} (via {n.how}) [{n.confidence} {n.confidence_pct}%] {n.timeframe}"
        for n in body.nodes
    )
    surprise_text = "\n".join(
        f"- {s.from_entity} → {s.to_entity} ({s.verb}): {s.mechanism}"
        for s in body.surprise_links
    ) or "None"
    insights_text = "\n".join(f"- {i}" for i in body.highlight_insights) or "None"
    causal_text = " → ".join(body.causal_order) or "Not provided"

    messages = [
        SystemMessage(content=KEY_TAKEAWAYS_SYSTEM),
        HumanMessage(content=KEY_TAKEAWAYS_USER.format(
            trigger_event=trigger_event,
            nodes=nodes_text,
            surprise_links=surprise_text,
            highlight_insights=insights_text,
            causal_order=causal_text,
        )),
    ]

    def _extract_json(raw: str) -> dict:
        text = raw.strip()
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                candidate = part.strip()
                if candidate.startswith("json"):
                    candidate = candidate[4:].strip()
                if candidate.startswith("{"):
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        pass
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        raise json.JSONDecodeError("No valid JSON object found in LLM output", text, 0)

    llm = make_llm(temperature=0.3)
    loop = asyncio.get_event_loop()
    data = None
    last_err = None

    for attempt in range(1, 4):
        try:
            response = await loop.run_in_executor(None, lambda: llm.invoke(messages))
            data = _extract_json(response.content)
            break
        except json.JSONDecodeError as e:
            last_err = e
            print(f"[WARN] /key-takeaways attempt {attempt}/3: JSON parse failed — {e}")
        except Exception as e:
            traceback.print_exc()
            err_str = str(e).lower()
            if "429" in err_str or "rate limit" in err_str:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error_code": "LLM_RATE_LIMIT",
                        "message": "Gemini API rate limit hit.",
                        "hint": "Wait 30–60 seconds and retry.",
                        "retry_after_seconds": 60,
                    },
                )
            raise HTTPException(
                status_code=500,
                detail={
                    "error_code": "TAKEAWAYS_FAILED",
                    "message": "Failed to generate key takeaways.",
                    "detail": f"{type(e).__name__}: {e}",
                },
            )

    if data is None:
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "PARSE_FAILED",
                "message": "LLM returned malformed JSON after 3 attempts.",
                "detail": str(last_err),
            },
        )

    return {
        "trigger_event": trigger_event,
        "headline": data.get("headline", ""),
        "summary": data.get("summary", ""),
        "takeaways": data.get("takeaways", []),
        "biggest_surprise": data.get("biggest_surprise", ""),
        "watch_next": data.get("watch_next", ""),
    }


@app.post(
    "/detail",
    tags=["analysis"],
    responses={
        200: {"description": "Under-250-word deep-dive on a specific causal node"},
        400: {"model": ErrorResponse, "description": "Bad input"},
        401: {"model": ErrorResponse, "description": "Unauthorized / missing key"},
        429: {"description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    },
)
@limiter.limit("20/minute")
async def detail(
    request: Request,
    body: DetailRequest,
    _: str = Depends(verify_api_key),
    google_key: str = Depends(resolve_google_key),
):
    from langchain_core.messages import SystemMessage, HumanMessage

    set_api_key(google_key)
    trigger_event = " ".join(body.trigger_event.strip().split())[:500]
    entity = " ".join(body.entity.strip().split())[:200]

    messages = [
        SystemMessage(content=DETAIL_SYSTEM.format(domain=body.domain)),
        HumanMessage(content=DETAIL_USER.format(
            trigger_event=trigger_event,
            domain=body.domain,
            entity=entity,
            what=body.what or "Not specified",
            how=body.how or "Not specified",
            confidence=body.confidence,
            confidence_pct=body.confidence_pct,
            timeframe=body.timeframe or "Not specified",
            counter_narrative=body.counter_narrative or "None recorded",
        )),
    ]

    try:
        llm = make_llm(temperature=0.5)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: llm.invoke(messages))
        text = response.content.strip()
    except Exception as e:
        traceback.print_exc()
        err_str = str(e).lower()
        if "429" in err_str or "rate limit" in err_str:
            raise HTTPException(
                status_code=429,
                detail={
                    "error_code": "LLM_RATE_LIMIT",
                    "message": "Gemini API rate limit hit.",
                    "hint": "Wait 30–60 seconds and retry.",
                    "retry_after_seconds": 60,
                },
            )
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "DETAIL_FAILED",
                "message": "Failed to generate deep-dive.",
                "detail": f"{type(e).__name__}: {e}",
            },
        )

    return {
        "trigger_event": trigger_event,
        "domain": body.domain,
        "entity": entity,
        "detail": text,
        "word_count": len(text.split()),
    }


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("AFTERMATH_DEBUG", "0") == "1",
    )
