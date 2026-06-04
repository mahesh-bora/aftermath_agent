from langgraph.graph import StateGraph, START, END
from langgraph.constants import Send
from .state import AftermathState
from .agents.orchestrator import orchestrator_brief_node
from .agents.specialist import domain_specialist_node
from .agents.synthesizer import synthesizer_node


def _route_after_orchestrator(state: AftermathState):
    """Gate: invalid event → END. Valid event → fan-out to domain specialists."""
    if not state.get("is_valid_event", True):
        return END
    return [
        Send("domain_specialist", {
            "trigger_event": state["trigger_event"],
            "domain": domain,
            "briefing": briefing,
            "google_api_key": state.get("google_api_key", ""),
        })
        for domain, briefing in state["orchestrator_briefings"].items()
    ]


def build_graph():
    builder = StateGraph(AftermathState)

    builder.add_node("orchestrator_brief", orchestrator_brief_node)
    builder.add_node("domain_specialist", domain_specialist_node)
    builder.add_node("synthesizer", synthesizer_node)

    builder.add_edge(START, "orchestrator_brief")
    builder.add_conditional_edges(
        "orchestrator_brief",
        _route_after_orchestrator,
        ["domain_specialist", END],
    )
    builder.add_edge("domain_specialist", "synthesizer")
    builder.add_edge("synthesizer", END)

    return builder.compile()


graph = build_graph()
