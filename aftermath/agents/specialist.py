import os
import json
import traceback
from langchain_core.messages import HumanMessage, SystemMessage
from ..state import DomainOutput, CausalNode, DOMAIN_CONTEXTS, MAX_NODES_PER_DOMAIN
from ..prompts import DOMAIN_SPECIALIST_SYSTEM, DOMAIN_SPECIALIST_USER
from ..llm import make_llm, set_api_key

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

    # Explicitly bind the BYOK key — ContextVar doesn't propagate into LangGraph's thread pool
    if key := state.get("google_api_key"):
        set_api_key(key)

    llm = make_llm(temperature=0.8)

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
        # Hard cap before validation — LLM sometimes ignores the 3–4 rule
        if isinstance(data.get("nodes"), list) and len(data["nodes"]) > MAX_NODES_PER_DOMAIN:
            print(f"[WARN] {domain}: LLM returned {len(data['nodes'])} nodes, truncating to {MAX_NODES_PER_DOMAIN}")
            data["nodes"] = data["nodes"][:MAX_NODES_PER_DOMAIN]
        output = DomainOutput.model_validate(data)

    output.domain = domain
    for node in output.nodes:
        node.domain = domain

    # Final hard cap — catches any path that slips past Pydantic Field max_length
    if len(output.nodes) > MAX_NODES_PER_DOMAIN:
        print(f"[WARN] {domain}: capping {len(output.nodes)} → {MAX_NODES_PER_DOMAIN} nodes")
        output = output.model_copy(update={"nodes": output.nodes[:MAX_NODES_PER_DOMAIN]})

    if DEBUG:
        print(f"[DEBUG] {domain}: {len(output.nodes)} nodes")

    return {"domain_outputs": [output]}
