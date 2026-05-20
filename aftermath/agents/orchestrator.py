import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from ..state import AftermathState, OrchestratorBriefings
from ..prompts import ORCHESTRATOR_BRIEF_SYSTEM, ORCHESTRATOR_BRIEF_USER

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def orchestrator_brief_node(state: AftermathState) -> dict:
    llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0.7)
    structured_llm = llm.with_structured_output(OrchestratorBriefings)

    messages = [
        SystemMessage(content=ORCHESTRATOR_BRIEF_SYSTEM),
        HumanMessage(content=ORCHESTRATOR_BRIEF_USER.format(
            trigger_event=state["trigger_event"],
            selected_domains=", ".join(state["selected_domains"]),
        )),
    ]

    result: OrchestratorBriefings = structured_llm.invoke(messages)

    # Filter to only selected domains (model may add extras)
    selected = set(state["selected_domains"])
    filtered = {k: v for k, v in result.briefings.items() if k in selected}

    # Fallback: if model returns no matching keys, use raw briefings
    if not filtered:
        filtered = result.briefings

    return {"orchestrator_briefings": filtered}
