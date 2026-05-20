from langgraph.graph import StateGraph, START, END
from langgraph.constants import Send
from .state import AftermathState
from .agents.orchestrator import orchestrator_brief_node
from .agents.specialist import domain_specialist_node
from .agents.synthesizer import synthesizer_node


def _route_to_specialists(state: AftermathState) -> list[Send]:
    """Fan-out: dispatch one Send per briefed domain. All run before synthesizer."""
    return [
        Send("domain_specialist", {
            "trigger_event": state["trigger_event"],
            "domain": domain,
            "briefing": briefing,
        })
        for domain, briefing in state["orchestrator_briefings"].items()
    ]


def build_graph():
    builder = StateGraph(AftermathState)

    builder.add_node("orchestrator_brief", orchestrator_brief_node)
    builder.add_node("domain_specialist", domain_specialist_node)
    builder.add_node("synthesizer", synthesizer_node)

    builder.add_edge(START, "orchestrator_brief")
    # Fan-out: orchestrator_brief → N × domain_specialist (via Send)
    builder.add_conditional_edges(
        "orchestrator_brief",
        _route_to_specialists,
        ["domain_specialist"],
    )
    # Fan-in: all domain_specialist nodes complete → synthesizer
    builder.add_edge("domain_specialist", "synthesizer")
    builder.add_edge("synthesizer", END)

    return builder.compile()


# Module-level compiled graph — import and call .invoke() or .stream()
graph = build_graph()
