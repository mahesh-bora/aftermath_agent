#!/usr/bin/env python3
import sys
import os
import traceback
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

    # Warn if all nodes are Established — adversarial check likely failed
    conf_counts = {}
    for node in fg.nodes:
        conf_counts[node.confidence] = conf_counts.get(node.confidence, 0) + 1
    total = len(fg.nodes)
    if total > 0:
        est_pct = conf_counts.get("Established", 0) / total
        parts = "  ".join(
            f"[{CONFIDENCE_STYLE.get(k, ('white','?'))[0]}]{CONFIDENCE_STYLE.get(k,('white','?'))[1]} {v} {k}[/{CONFIDENCE_STYLE.get(k,('white','?'))[0]}]"
            for k, v in conf_counts.items()
        )
        console.print(f"  [dim]Confidence distribution:[/dim]  {parts}")
        if est_pct == 1.0:
            console.print("  [yellow]⚠ All nodes Established — adversarial check may have been skipped[/yellow]")
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

    # Causal order — numbered list, not flat arrow chain
    if fg.causal_order:
        lines = [f"[dim]0.[/dim]  [yellow]{fg.trigger_event}[/yellow]  [dim](trigger)[/dim]"]
        for i, entity in enumerate(fg.causal_order, 1):
            indent = "   " * min(i, 4)  # visual nesting hint
            lines.append(f"[dim]{i}.[/dim]{indent}[white]{entity}[/white]")
        console.print(Panel(
            "\n".join(lines),
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

    debug = os.getenv("AFTERMATH_DEBUG", "0") == "1"
    final_state = None

    try:
        with console.status("[yellow]Running Aftermath agents...[/yellow]", spinner="dots") as status:
            # stream_mode="values" emits full state after each node — last emission is final state
            for state_snapshot in graph.stream(initial_state, stream_mode="values"):
                # derive which node just ran from what changed
                briefings = state_snapshot.get("orchestrator_briefings", {})
                outputs = state_snapshot.get("domain_outputs", [])
                fg = state_snapshot.get("final_graph")

                is_valid = state_snapshot.get("is_valid_event", True)
                if not is_valid:
                    status.update("[yellow]Orchestrator: invalid event — stopping[/yellow]")
                elif fg is not None:
                    status.update("[yellow]Synthesizing — done[/yellow]")
                elif outputs:
                    last = outputs[-1].domain
                    col = DOMAIN_COLORS.get(last, "white")
                    status.update(
                        f"[dim]{len(outputs)}/{len(selected)} specialists done[/dim] "
                        f"← [{col}]{last}[/{col}]"
                    )
                elif briefings:
                    status.update(
                        f"[yellow]Orchestrator briefed {len(briefings)} specialists — running...[/yellow]"
                    )

                final_state = state_snapshot

    except Exception as e:
        console.print(f"\n[red bold]ERROR:[/red bold] {type(e).__name__}: {e}")
        if debug:
            traceback.print_exc()
        else:
            console.print("[dim]Set AFTERMATH_DEBUG=1 for full traceback.[/dim]")
        sys.exit(1)

    if final_state and not final_state.get("is_valid_event", True):
        console.print()
        console.print(Panel(
            final_state.get("invalid_message", "Invalid event."),
            title="[yellow]AFTERMATH[/yellow]",
            border_style="yellow",
            width=72,
        ))
        sys.exit(0)

    final_graph = final_state.get("final_graph") if final_state else None

    if final_graph:
        display_graph(final_graph)
    else:
        console.print("[red]Synthesis failed — final_graph is None.[/red]")
        console.print("[dim]Re-run with AFTERMATH_DEBUG=1 to see agent errors.[/dim]")
        sys.exit(1)


if __name__ == "__main__":
    main()
