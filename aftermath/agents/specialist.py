import os
import json
import traceback
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from ..state import DomainOutput, CausalNode, DOMAIN_CONTEXTS
from ..prompts import DOMAIN_SPECIALIST_SYSTEM, DOMAIN_SPECIALIST_USER

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
DEBUG = os.getenv("AFTERMATH_DEBUG", "0") == "1"


def domain_specialist_node(state: dict) -> dict:
    """
    Runs as a single domain specialist.
    Receives: {trigger_event, domain, briefing} via Send.
    Returns: {domain_outputs: [DomainOutput]} merged into main state via operator.add.
    """
    domain: str = state["domain"]
    briefing: str = state["briefing"]
    trigger_event: str = state["trigger_event"]
    domain_context = DOMAIN_CONTEXTS.get(domain, f"Domain: {domain}")

    llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0.8)
    structured_llm = llm.with_structured_output(DomainOutput)

    messages = [
        SystemMessage(content=DOMAIN_SPECIALIST_SYSTEM.format(
            domain=domain,
            domain_context=domain_context,
        )),
        HumanMessage(content=DOMAIN_SPECIALIST_USER.format(
            trigger_event=trigger_event,
            briefing=briefing,
            domain=domain,
        )),
    ]

    # Attempt 1: structured output
    try:
        structured_llm = llm.with_structured_output(DomainOutput)
        output = structured_llm.invoke(messages)
        if output is None:
            raise ValueError("with_structured_output returned None")
    except Exception as e:
        if DEBUG:
            traceback.print_exc()
        print(f"\n[WARN] {domain} structured output failed ({type(e).__name__}: {e}), trying JSON fallback...")

        # Attempt 2: JSON fallback
        fallback_messages = messages + [
            HumanMessage(
                content=(
                    'Return ONLY valid JSON (no markdown) like: '
                    '{"domain": "' + domain + '", "nodes": ['
                    '{"entity": "...", "domain": "' + domain + '", '
                    '"what": "...", "how": "...", '
                    '"confidence": "Established|Contested|Speculative", '
                    '"timeframe": "...", "counter_narrative": null}]}'
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
        data["domain"] = domain
        output = DomainOutput.model_validate(data)

    output.domain = domain
    for node in output.nodes:
        node.domain = domain

    if DEBUG:
        print(f"[DEBUG] {domain}: {len(output.nodes)} nodes")

    return {"domain_outputs": [output]}
