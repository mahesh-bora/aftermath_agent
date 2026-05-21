import os
import json
import traceback
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from ..state import AftermathState, FinalGraph, DomainOutput
from ..prompts import SYNTHESIZER_SYSTEM, SYNTHESIZER_USER

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
DEBUG = os.getenv("AFTERMATH_DEBUG", "0") == "1"

_JSON_SCHEMA = """
{
  "trigger_event": "string",
  "nodes": [
    {
      "entity": "string",
      "domain": "string",
      "what": "string (8 words max)",
      "how": "string (5 words max)",
      "confidence": "Established | Contested | Speculative",
      "timeframe": "string",
      "counter_narrative": "string or null"
    }
  ],
  "edges": [
    {
      "from_entity": "string",
      "to_entity": "string",
      "verb": "triggered | amplified | preceded | undermined | enabled | constrained",
      "mechanism": "string",
      "is_cross_domain_surprise": false
    }
  ],
  "surprise_links": [
    {
      "from_entity": "string",
      "to_entity": "string",
      "verb": "string",
      "mechanism": "string",
      "is_cross_domain_surprise": true
    }
  ],
  "highlight_insights": ["string", "string", "string"],
  "causal_order": ["entity1", "entity2", "entity3"]
}
"""


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


def _parse_json_response(text: str, trigger_event: str) -> FinalGraph:
    """Strip markdown fences and parse JSON into FinalGraph."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0]
    data = json.loads(text.strip())
    data["trigger_event"] = trigger_event
    return FinalGraph.model_validate(data)


def synthesizer_node(state: AftermathState) -> dict:
    if not state.get("domain_outputs"):
        raise ValueError("synthesizer received empty domain_outputs — all specialists failed")

    if DEBUG:
        print(f"\n[DEBUG] synthesizer: {len(state['domain_outputs'])} domain outputs")

    llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0.5)
    domain_outputs_text = _format_domain_outputs(state["domain_outputs"])

    messages = [
        SystemMessage(content=SYNTHESIZER_SYSTEM),
        HumanMessage(content=SYNTHESIZER_USER.format(
            trigger_event=state["trigger_event"],
            domain_outputs=domain_outputs_text,
        )),
    ]

    # Build domain → original nodes map for post-synthesis enforcement
    selected_domains = set(state.get("selected_domains", []))
    original_domain_map: dict[str, str] = {}  # entity → correct domain
    for do in state["domain_outputs"]:
        for node in do.nodes:
            original_domain_map[node.entity] = do.domain

    confidence_threshold = int(os.getenv("AFTERMATH_MIN_CONFIDENCE", "90"))

    def _enforce_domains(result: FinalGraph) -> FinalGraph:
        """Restore correct domain labels, filter unselected domains, filter low confidence."""
        for node in result.nodes:
            if node.entity in original_domain_map:
                node.domain = original_domain_map[node.entity]

        before = len(result.nodes)

        # Filter unselected domains
        if selected_domains:
            result.nodes = [n for n in result.nodes if n.domain in selected_domains]

        # Filter below confidence threshold
        # If confidence_pct is 0 (not set), derive from categorical label
        for node in result.nodes:
            if node.confidence_pct == 0:
                node.confidence_pct = {"Established": 90, "Contested": 60, "Speculative": 25}.get(
                    node.confidence, 0
                )
        result.nodes = [n for n in result.nodes if n.confidence_pct >= confidence_threshold]

        dropped = before - len(result.nodes)
        if dropped > 0:
            if DEBUG:
                print(f"[DEBUG] dropped {dropped} nodes (domain mismatch or confidence < {confidence_threshold}%)")
            else:
                print(f"[INFO] {dropped} nodes filtered (below {confidence_threshold}% confidence or wrong domain)")

        # Also filter edges/surprise_links to only reference remaining nodes
        remaining = {n.entity for n in result.nodes}
        result.edges = [
            e for e in result.edges
            if e.from_entity in remaining and e.to_entity in remaining
        ]
        result.surprise_links = [
            e for e in result.surprise_links
            if e.from_entity in remaining and e.to_entity in remaining
        ]
        result.causal_order = [e for e in result.causal_order if e in remaining]

        return result

    # Attempt 1: structured output via function calling
    try:
        structured_llm = llm.with_structured_output(FinalGraph)
        result = structured_llm.invoke(messages)
        if result is None:
            raise ValueError("with_structured_output returned None")
        result.trigger_event = state["trigger_event"]
        result = _enforce_domains(result)
        if DEBUG:
            print(f"[DEBUG] synthesizer: structured output OK, {len(result.nodes)} nodes")
        return {"final_graph": result}
    except Exception as e:
        if DEBUG:
            traceback.print_exc()
        print(f"\n[WARN] structured output failed ({type(e).__name__}: {e}), trying JSON fallback...")

    # Attempt 2: explicit JSON prompt + manual parse
    try:
        json_messages = messages + [
            HumanMessage(
                content=(
                    "Return ONLY valid JSON (no markdown fences, no explanation) "
                    f"matching this exact schema:\n{_JSON_SCHEMA}"
                )
            )
        ]
        response = llm.invoke(json_messages)
        result = _parse_json_response(response.content, state["trigger_event"])
        result = _enforce_domains(result)
        if DEBUG:
            print(f"[DEBUG] synthesizer: JSON fallback OK, {len(result.nodes)} nodes")
        return {"final_graph": result}
    except Exception as e2:
        traceback.print_exc()
        raise RuntimeError(f"Synthesizer failed both structured and JSON fallback: {e2}") from e2
