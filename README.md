# Aftermath Agent

Multi-agent causal intelligence engine. Input any event → get a non-obvious causal graph across 12 domains.

Built with LangGraph + Gemini 2.5 Flash.

## Architecture

```
Trigger Event
     │
     ▼
┌─────────────────────┐
│  Orchestrator Brief │  ← Gemini 2.5 Flash
│  Analyzes event,    │    Writes non-obvious
│  briefs each domain │    angle per domain
└─────────┬───────────┘
          │  Send (fan-out, parallel)
    ┌─────┼─────┬──────┬──────┐
    ▼     ▼     ▼      ▼      ▼
 ECON  FINANCE  GEO  TECH  CULTURE  ...  (up to 12 domain specialists)
    │     │     │      │      │
    └─────┴─────┴──────┴──────┘
          │  operator.add (fan-in)
          ▼
┌─────────────────────┐
│     Synthesizer     │  ← Gemini 2.5 Flash
│  Cuts weak nodes,   │    Finds surprise links,
│  finds cross-domain │    writes insights
│  surprise links     │
└─────────┬───────────┘
          ▼
     Final Graph
```

## Setup

```bash
# 1. Clone / enter directory
cd aftermath-agent

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set API key
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY

# 4. Run
python run.py
```

## Usage

```
$ python run.py

Enter trigger event:
> Lehman Brothers files for bankruptcy, September 2008

Select domains (1–12, comma-separated, or ENTER for all):
> 1,2,3,5,7

Tracing across 5 domains...

[live progress per specialist]

AFTERMATH — CAUSAL GRAPH
...
```

## Domains

| # | Domain | Focus |
|---|--------|-------|
| 1 | ECONOMICS | Macro: GDP, trade, employment, inflation |
| 2 | FINANCE | Markets: credit, banking, capital flows |
| 3 | GEOPOLITICS | Power: alliances, sovereignty, leverage |
| 4 | POLITICS | Domestic: coalitions, policy, power |
| 5 | TECHNOLOGY | Innovation: disruption, infrastructure |
| 6 | SUPPLY_CHAIN | Physical: logistics, chokepoints |
| 7 | CULTURE | Social: movements, narratives, blame |
| 8 | MILITARY | Defense: budgets, readiness, vacuums |
| 9 | GEOGRAPHY | Physical: migration, resources, borders |
| 10 | CLIMATE | Environment: energy, agriculture |
| 11 | HEALTHCARE | Public health: mental health, pharma |
| 12 | HISTORY | Precedents: rhymes, patterns, breaks |

## Output

Each run produces:
- **Nodes** — specific entities with mechanism, confidence, timeframe
- **Edges** — directed causal connections with verbs (triggered/amplified/preceded...)
- **Surprise links** — non-obvious cross-domain connections
- **Highlight insights** — 3 findings a smart analyst wouldn't have expected
- **Causal order** — entities sorted by distance from trigger

## Confidence levels

- `●` Established — direct documented causation
- `◐` Contested — causal link debated, counter-narrative shown
- `○` Speculative — plausible mechanism, limited evidence

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_API_KEY` | required | Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Override model name |

## Note on parallelism

LangGraph's `Send` API dispatches domain specialists concurrently. In the default sync runtime, nodes execute sequentially but the state fan-in logic is identical to async. For true parallel I/O, use `await graph.ainvoke()` in an async context.
