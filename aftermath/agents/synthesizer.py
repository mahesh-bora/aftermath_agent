import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from ..state import AftermathState, FinalGraph, DomainOutput
from ..prompts import SYNTHESIZER_SYSTEM, SYNTHESIZER_USER

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def _format_domain_outputs(outputs: list[DomainOutput]) -> str:
    lines = []
    for output in outputs:
        lines.append(f"\n=== {output.domain} ===")
        for node in output.nodes:
            lines.append(f"Entity:     {node.entity}")
            lines.append(f"What:       {node.what}")
            lines.append(f"How:        {node.how}")
            lines.append(f"Confidence: {node.confidence}")
            lines.append(f"Timeframe:  {node.timeframe}")
            if node.counter_narrative:
                lines.append(f"Counter:    {node.counter_narrative}")
            lines.append("---")
    return "\n".join(lines)


def synthesizer_node(state: AftermathState) -> dict:
    llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0.5)
    structured_llm = llm.with_structured_output(FinalGraph)

    domain_outputs_text = _format_domain_outputs(state["domain_outputs"])

    messages = [
        SystemMessage(content=SYNTHESIZER_SYSTEM),
        HumanMessage(content=SYNTHESIZER_USER.format(
            trigger_event=state["trigger_event"],
            domain_outputs=domain_outputs_text,
        )),
    ]

    final_graph: FinalGraph = structured_llm.invoke(messages)
    final_graph.trigger_event = state["trigger_event"]

    return {"final_graph": final_graph}
