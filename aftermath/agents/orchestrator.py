import os
import json
import traceback
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from ..state import AftermathState, OrchestratorBriefings, EventValidation
from ..prompts import ORCHESTRATOR_BRIEF_SYSTEM, ORCHESTRATOR_BRIEF_USER

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
DEBUG = os.getenv("AFTERMATH_DEBUG", "0") == "1"

_VALIDATION_SYSTEM = """\
You are the gatekeeper for Aftermath, a causal intelligence tool that traces how specific \
historical, economic, geopolitical, or cultural events ripple across 12 domains.

Aftermath ONLY works on:
- Specific named historical events (wars, crises, elections, policy decisions, treaties, disasters)
- Specific economic events (market crashes, currency crises, trade deals, sanctions)
- Specific geopolitical events (coups, invasions, summits, independence movements)
- Specific technological events (invention launches, platform collapses, regulations)
- Specific cultural events (social movements, major publications, cultural shifts with a clear origin)

Aftermath CANNOT work on:
- Greetings or meta-questions ("hi", "hello", "what can you do", "test")
- Vague topics without a specific trigger ("inequality", "climate change", "globalization")
- Questions about Aftermath itself ("how does this work", "what is this app")
- Fictional or hypothetical events
- Future events with no historical basis

Be generous on real events — even if the date is slightly wrong, if the event is real and traceable, mark valid.
"""

_VALIDATION_USER = """\
User input: "{trigger_event}"

Is this a valid trigger event Aftermath can analyze? \
Return JSON: {{"is_valid": true/false, "reason": "one sentence", \
"suggested_query": "only if invalid — suggest a real event they could ask about"}}
"""

_GUIDANCE_MESSAGE = """\
Aftermath traces causal chains from real historical events across 12 domains:
Economics · Finance · Geopolitics · Politics · Technology · Supply Chain
Culture · Military · Geography · Climate · Healthcare · History

Try asking about:
  → "Lehman Brothers bankruptcy, September 2008"
  → "India demonetization November 2016"
  → "Suez Canal blockage March 2021"
  → "Brexit referendum June 2016"
  → "COVID-19 WHO pandemic declaration March 2020"
  → "US-China trade war tariffs 2018"

Enter a specific event to trace its ripple effects.\
"""


def _validate_event(llm: ChatGoogleGenerativeAI, trigger_event: str) -> EventValidation:
    """Single API call to decide if the trigger is a real traceable event."""
    try:
        structured = llm.with_structured_output(EventValidation)
        result = structured.invoke([
            SystemMessage(content=_VALIDATION_SYSTEM),
            HumanMessage(content=_VALIDATION_USER.format(trigger_event=trigger_event)),
        ])
        if result is None:
            raise ValueError("structured output returned None")
        return result
    except Exception as e:
        if DEBUG:
            traceback.print_exc()
        # Fallback: parse JSON from text
        response = llm.invoke([
            SystemMessage(content=_VALIDATION_SYSTEM),
            HumanMessage(content=_VALIDATION_USER.format(trigger_event=trigger_event) +
                         "\nReturn ONLY valid JSON, no markdown."),
        ])
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.rsplit("```", 1)[0].strip()
        data = json.loads(text)
        return EventValidation.model_validate(data)


def orchestrator_brief_node(state: AftermathState) -> dict:
    llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0.3)
    selected_domains = state["selected_domains"]
    trigger_event = state["trigger_event"]

    # ── Step 1: validate the trigger event ───────────────────────────────────
    validation = _validate_event(llm, trigger_event)

    if DEBUG:
        print(f"[DEBUG] validation: is_valid={validation.is_valid}, reason={validation.reason}")

    if not validation.is_valid:
        msg = _GUIDANCE_MESSAGE
        if validation.suggested_query:
            msg += f"\n\nBased on your input, maybe you meant: \"{validation.suggested_query}\""
        return {
            "is_valid_event": False,
            "invalid_message": msg,
            "orchestrator_briefings": {},
        }

    # ── Step 2: brief domain specialists ─────────────────────────────────────
    messages = [
        SystemMessage(content=ORCHESTRATOR_BRIEF_SYSTEM),
        HumanMessage(content=ORCHESTRATOR_BRIEF_USER.format(
            trigger_event=trigger_event,
            selected_domains=", ".join(selected_domains),
        )),
    ]

    try:
        structured_llm = llm.with_structured_output(OrchestratorBriefings)
        result = structured_llm.invoke(messages)
        if result is None:
            raise ValueError("with_structured_output returned None")
        briefings = result.briefings
    except Exception as e:
        if DEBUG:
            traceback.print_exc()
        print(f"\n[WARN] orchestrator briefing failed ({type(e).__name__}: {e}), using JSON fallback...")
        fallback_messages = messages + [
            HumanMessage(content='Return ONLY valid JSON: {"briefings": {"DOMAIN_NAME": "briefing", ...}}')
        ]
        response = llm.invoke(fallback_messages)
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.rsplit("```", 1)[0].strip()
        data = json.loads(text)
        briefings = data.get("briefings", data)

    # Filter to selected domains (normalize case)
    selected = set(selected_domains)
    filtered = {k: v for k, v in briefings.items() if k in selected}
    if not filtered:
        filtered = {k.upper(): v for k, v in briefings.items() if k.upper() in selected}
    if not filtered:
        filtered = {d: f"Investigate second-order, non-obvious effects of this event on {d}. "
                      f"Avoid the obvious first-order connection." for d in selected_domains}

    if DEBUG:
        print(f"[DEBUG] orchestrator: briefed {list(filtered.keys())}")

    return {
        "is_valid_event": True,
        "invalid_message": "",
        "orchestrator_briefings": filtered,
    }
