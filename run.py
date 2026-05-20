#!/usr/bin/env python3
import sys
import os
from dotenv import load_dotenv

load_dotenv()

if not os.getenv("GOOGLE_API_KEY"):
    print("ERROR: GOOGLE_API_KEY not set. Copy .env.example → .env and add your key.")
    sys.exit(1)

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from aftermath.graph import graph
from aftermath.state import ALL_DOMAINS, FinalGraph, DomainOutput

console = Console()

DOMAIN_COLORS = {
    "ECONOMICS": "yellow",
    "FINANCE": "gold1",
    "GEOPOLITICS": "steel_blue",
    "POLITICS": "red3",
    "TECHNOLOGY": "dodger_blue1",
    "SUPPLY_CHAIN": "cyan",
    "CULTURE": "green4",
    "MILITARY": "red1",
    "GEOGRAPHY": "dark_cyan",
    "CLIMATE": "green",
    "HEALTHCARE": "spring_green3",
    "HISTORY": "medium_purple",
}

CONFIDENCE_STYLE = {
    "Established": ("green", "●"),
    "Contested": ("yellow", "◐"),
    "Speculative": ("red", "○"),
}


def display_graph(fg: FinalGraph) -> None:
    console.print()
    console.rule("[bold yellow]AFTERMATH — CAUSAL GRAPH[/bold yellow]")
    console.print()

    console.print(Panel(
        f"[bold white]{fg.trigger_event}[/bold white]",
        title="[yellow]TRIGGER[/yellow]",
        border_style="yellow",
        width=80,
    ))
    console.print()

    # Nodes table
    tbl = Table(
        title="[bold]Causal Nodes[/bold]",
        border_style="dim",
        header_style="bold yellow",
        show_lines=True,
    )
    tbl.add_column("Domain", width=14)
    tbl.add_column("Entity", width=24)
    tbl.add_column("What", width=30)
    tbl.add_column("How (mechanism)", width=24)
    tbl.add_column("Conf", width=5)
    tbl.add_column("When", width=12)

    for node in fg.nodes:
        col = DOMAIN_COLORS.get(node.domain, "white")
        conf_col, conf_sym = CONFIDENCE_STYLE.get(node.confidence, ("white", "?"))
        tbl.add_row(
            f"[{col}]{node.domain}[/{col}]",
            f"[bold]{node.entity}[/bold]",
            node.what,
            f"[dim]{node.how}[/dim]",
            f"[{conf_col}]{conf_sym}[/{conf_col}]",
            node.timeframe,
        )

    console.print(tbl)
    console.print()

    # Edges
    if fg.edges:
        edge_lines = []
        for edge in fg.edges:
            style = "[yellow]★[/yellow] " if edge.is_cross_domain_surprise else "  "
            edge_lines.append(
                f"{style}[bold]{edge.from_entity}[/bold] "
                f"[dim]{edge.verb}[/dim] "
                f"[bold]{edge.to_entity}[/bold]\n"
                f"   [dim italic]{edge.mechanism}[/dim italic]"
            )
        console.print(Panel(
            "\n".join(edge_lines),
            title="[yellow]CAUSAL EDGES[/yellow]",
            border_style="dim",
        ))
        console.print()

    # Surprise cross-domain links
    if fg.surprise_links:
        surprise_lines = []
        for link in fg.surprise_links:
            surprise_lines.append(
                f"[yellow]★[/yellow] [bold]{link.from_entity}[/bold] "
                f"[yellow]{link.verb}[/yellow] "
                f"[bold]{link.to_entity}[/bold]\n"
                f"   [italic]{link.mechanism}[/italic]"
            )
        console.print(Panel(
            "\n".join(surprise_lines),
            title="[bold yellow]SURPRISE CROSS-DOMAIN LINKS[/bold yellow]",
            border_style="yellow",
        ))
        console.print()

    # Highlight insights
    if fg.highlight_insights:
        insights = "\n\n".join([
            f"[yellow]{i + 1}.[/yellow] {insight}"
            for i, insight in enumerate(fg.highlight_insights)
        ])
        console.print(Panel(
            insights,
            title="[bold green]HIGHLIGHT INSIGHTS[/bold green]",
            border_style="green",
        ))
        console.print()

    # Causal order
    if fg.causal_order:
        order_text = "  →  ".join(fg.causal_order)
        console.print(Panel(
            f"[dim]{order_text}[/dim]",
            title="[dim]Causal Order (trigger → downstream)[/dim]",
            border_style="dim",
        ))


def select_domains() -> list[str]:
    console.print("[yellow]Available domains:[/yellow]\n")
    for i, d in enumerate(ALL_DOMAINS, 1):
        col = DOMAIN_COLORS.get(d, "white")
        console.print(f"  [{col}]{i:2}. {d}[/{col}]")

    console.print()
    console.print("[dim]Select by number, comma-separated (e.g. 1,3,5) — or ENTER for all:[/dim]")
    raw = input("> ").strip()

    if not raw:
        return ALL_DOMAINS

    indices = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < len(ALL_DOMAINS):
                indices.append(idx)

    return [ALL_DOMAINS[i] for i in indices] if indices else ALL_DOMAINS


def main() -> None:
    console.print()
    console.print(Panel(
        "[bold yellow]AFTERMATH[/bold yellow]\n"
        "[dim]Personal Causal Intelligence Canvas\n"
        "Multi-agent · Gemini 2.5 Flash · LangGraph[/dim]",
        border_style="yellow",
        width=52,
    ))
    console.print()

    console.print("[yellow]Enter trigger event:[/yellow]")
    trigger = input("> ").strip()
    if not trigger:
        console.print("[red]No event entered.[/red]")
        sys.exit(1)

    console.print()
    selected = select_domains()
    console.print(f"\n[dim]Tracing across {len(selected)} domains: {', '.join(selected)}[/dim]\n")

    initial_state = {
        "trigger_event": trigger,
        "selected_domains": selected,
        "orchestrator_briefings": {},
        "domain_outputs": [],
        "final_graph": None,
    }

    final_graph = None
    domains_done: list[str] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("[yellow]Orchestrator analyzing trigger event...[/yellow]", total=None)

        for event in graph.stream(initial_state, stream_mode="updates"):
            for node_name, delta in event.items():
                if node_name == "orchestrator_brief":
                    n = len(delta.get("orchestrator_briefings", {}))
                    progress.update(
                        task,
                        description=f"[yellow]Orchestrator briefed {n} specialists — dispatching...[/yellow]",
                    )
                elif node_name == "domain_specialist":
                    outputs: list[DomainOutput] = delta.get("domain_outputs", [])
                    for o in outputs:
                        domains_done.append(o.domain)
                    col = DOMAIN_COLORS.get(domains_done[-1], "white") if domains_done else "white"
                    done_str = f"[{col}]{domains_done[-1]}[/{col}]" if domains_done else ""
                    progress.update(
                        task,
                        description=(
                            f"[dim]{len(domains_done)}/{len(selected)} specialists done[/dim] "
                            f"← {done_str}"
                        ),
                    )
                elif node_name == "synthesizer":
                    progress.update(task, description="[yellow]Synthesizing final graph...[/yellow]")
                    final_graph = delta.get("final_graph")

    if final_graph:
        display_graph(final_graph)
    else:
        console.print("[red]Synthesis failed — no final graph returned.[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
