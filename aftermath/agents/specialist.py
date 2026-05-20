import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from ..state import DomainOutput, DOMAIN_CONTEXTS
from ..prompts import DOMAIN_SPECIALIST_SYSTEM, DOMAIN_SPECIALIST_USER

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


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

    output: DomainOutput = structured_llm.invoke(messages)
    output.domain = domain  # Ensure domain tag is correct

    # Ensure all nodes carry the correct domain tag
    for node in output.nodes:
        node.domain = domain

    return {"domain_outputs": [output]}
