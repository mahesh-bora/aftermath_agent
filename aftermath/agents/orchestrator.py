import os
import json
import traceback
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from ..state import AftermathState, OrchestratorBriefings
from ..prompts import ORCHESTRATOR_BRIEF_SYSTEM, ORCHESTRATOR_BRIEF_USER

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
DEBUG = os.getenv("AFTERMATH_DEBUG", "0") == "1"


def orchestrator_brief_node(state: AftermathState) -> dict:
    llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0.7)
    selected_domains = state["selected_domains"]

    messages = [
        SystemMessage(content=ORCHESTRATOR_BRIEF_SYSTEM),
        HumanMessage(content=ORCHESTRATOR_BRIEF_USER.format(
            trigger_event=state["trigger_event"],
            selected_domains=", ".join(selected_domains),
        )),
    ]

    # Attempt 1: structured output
    try:
        structured_llm = llm.with_structured_output(OrchestratorBriefings)
        result = structured_llm.invoke(messages)
        if result is None:
            raise ValueError("with_structured_output returned None")
        briefings = result.briefings
    except Exception as e:
        if DEBUG:
            traceback.print_exc()
        print(f"\n[WARN] orchestrator structured output failed ({type(e).__name__}: {e}), trying JSON fallback...")

        # Attempt 2: JSON fallback
        fallback_messages = messages + [
            HumanMessage(
                content=(
                    'Return ONLY valid JSON (no markdown) like: '
                    '{"briefings": {"DOMAIN_NAME": "briefing text", ...}}'
                )
            )
        ]
        response = llm.invoke(fallback_messages)
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.rsplit("```", 1)[0].strip()
        data = json.loads(text)
        briefings = data.get("briefings", data)  # handle both {"briefings": {...}} and bare dict

    # Filter to only selected domains
    selected = set(selected_domains)
    filtered = {k: v for k, v in briefings.items() if k in selected}
    if not filtered:
        # model may have returned lowercase keys — normalize
        filtered = {k.upper(): v for k, v in briefings.items() if k.upper() in selected}
    if not filtered:
        filtered = {d: f"Investigate non-obvious effects of this event on {d}" for d in selected_domains}

    if DEBUG:
        print(f"[DEBUG] orchestrator: briefed {list(filtered.keys())}")

    return {"orchestrator_briefings": filtered}
