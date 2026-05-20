from typing import Annotated, TypedDict, Optional
import operator
from pydantic import BaseModel, Field

DOMAIN_CONTEXTS: dict[str, str] = {
    "ECONOMICS": (
        "Macroeconomics tracks how production, trade, employment, and inflation respond to shocks. "
        "Follow money flows, GDP contractions, unemployment cycles, and central bank responses. "
        "Second-order effects (austerity → demand collapse → political crisis) are more interesting than first-order."
    ),
    "FINANCE": (
        "Financial markets move faster than events. Credit markets price risk before equity does. "
        "Watch repo markets, credit default swaps, margin calls, and capital flows. "
        "The mechanism matters: not 'banks stopped lending' but why specifically they couldn't."
    ),
    "GEOPOLITICS": (
        "Power shifts between states happen slowly but irreversibly. Track alliances, sovereignty disputes, "
        "and which state gains leverage from the chaos. The overlooked middle power is usually more interesting "
        "than the obvious great-power narrative."
    ),
    "POLITICS": (
        "Domestic politics responds to economic pain with a lag. Track which coalitions form, "
        "which policies become politically possible that weren't before, and who gains power from instability. "
        "Outsider movements often originate from failed establishment responses."
    ),
    "TECHNOLOGY": (
        "Disruption creates vacuums that technology fills — but only when economic necessity aligns with "
        "technical feasibility. Track what becomes economically necessary, what incumbents cannot defend, "
        "and what previously unviable business models suddenly work."
    ),
    "SUPPLY_CHAIN": (
        "Physical goods move through chokepoints governed by letters of credit, port capacity, and "
        "just-in-time inventory buffers. Disruptions cascade non-linearly. The bottleneck is rarely "
        "the obvious one — trace the dependencies two layers deep."
    ),
    "CULTURE": (
        "Social movements emerge from broken legitimacy and economic anxiety. Track how people explain "
        "the world to themselves, who they blame, and what narratives fill the vacuum. "
        "Media ecosystems amplify or suppress these narratives in non-obvious ways."
    ),
    "MILITARY": (
        "Defense budgets respond to perceived threats with a 3–5 year procurement lag. "
        "Security vacuums invite adventurism from third parties. Track doctrine changes, "
        "readiness shifts, and which actors gain from the instability."
    ),
    "GEOGRAPHY": (
        "Physical terrain, climate zones, and borders shape what's economically and politically possible. "
        "Track migration patterns, resource flow rerouting, and how physical constraints "
        "force or block political choices."
    ),
    "CLIMATE": (
        "Environmental pressures operate on long timelines but interact with short-term shocks. "
        "Track energy market responses, agricultural disruption, and how resource scarcity "
        "creates political pressure that compounds existing instability."
    ),
    "HEALTHCARE": (
        "Public health systems respond to economic instability and social disruption. "
        "Mental health, life expectancy, pharmaceutical market shifts, and healthcare access "
        "all respond to macro shocks in ways that rarely appear in economic models."
    ),
    "HISTORY": (
        "Events rhyme. The most useful historical analysis names the specific precedent, "
        "explains the structural similarity, and identifies where the analogy breaks down. "
        "'This is like X' without 'except for Y' is lazy."
    ),
}

ALL_DOMAINS = list(DOMAIN_CONTEXTS.keys())


class CausalNode(BaseModel):
    entity: str = Field(description="Specific real entity — institution, person, country, market index. Never generic.")
    domain: str = Field(description="One of the 12 domains in uppercase")
    what: str = Field(description="What happened to this entity — 8 words max")
    how: str = Field(description="The specific causal mechanism — 5 words max, no vague verbs")
    confidence: str = Field(description="Established | Contested | Speculative")
    timeframe: str = Field(description="When this happened or begins — e.g. 'Oct 2008', '2011–2015'")
    counter_narrative: Optional[str] = Field(
        default=None,
        description="Strongest objection to this causal link. Required for Contested and Speculative."
    )


class CausalEdge(BaseModel):
    from_entity: str = Field(description="Source entity name (must match a node entity)")
    to_entity: str = Field(description="Target entity name (must match a node entity)")
    verb: str = Field(description="triggered | amplified | preceded | undermined | enabled | constrained")
    mechanism: str = Field(description="One-line specific mechanism connecting the two nodes")
    is_cross_domain_surprise: bool = Field(
        default=False,
        description="True only if this connects nodes from different domains in a non-obvious way"
    )


class DomainOutput(BaseModel):
    domain: str
    nodes: list[CausalNode]


class OrchestratorBriefings(BaseModel):
    briefings: dict[str, str] = Field(
        description="Maps domain name (e.g. FINANCE) to a specific briefing for that specialist agent"
    )


class FinalGraph(BaseModel):
    trigger_event: str
    nodes: list[CausalNode] = Field(description="10–14 sharp, specific nodes. Cut weak ones.")
    edges: list[CausalEdge] = Field(description="Directed causal edges between nodes")
    surprise_links: list[CausalEdge] = Field(
        description="2–3 non-obvious cross-domain connections. The insights a reader wouldn't expect."
    )
    highlight_insights: list[str] = Field(
        description="Exactly 3 highlight insights. Each should make a smart reader say 'I hadn't thought of that.'"
    )
    causal_order: list[str] = Field(
        description="Entity names ordered by causal distance from trigger: direct consequences first, then second-order, etc."
    )


class AftermathState(TypedDict):
    trigger_event: str
    selected_domains: list[str]
    orchestrator_briefings: dict[str, str]
    domain_outputs: Annotated[list[DomainOutput], operator.add]
    final_graph: Optional[FinalGraph]
