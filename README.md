# 🥐 Maison Noisette: MCP Toolkit

**EECE 503P/798S Agentic Systems · C5 Agent Tools**

An MCP server for *Maison Noisette*, the fictional French-Lebanese pâtisserie from my C3 and C4 assignments, and an OpenAI Agents SDK agent that uses it. The server is built with FastMCP and exposes exactly three tools and two resources. The agent, Camille, is the MCP host: she starts the server, reads its resources, and calls its tools to answer customers and take orders.

🎥 **Demo video:** _add link_

## The three tools

| Category | Tool | What it does | Failure it handles |
|---|---|---|---|
| Data | `check_availability(item_id, quantity, pickup_date)` | Says how many of an item are left for a pickup date. Changes nothing. | A date in the past or more than 30 days ahead is an error. A closed day, too little notice or too few left is a normal "no" with a reason. |
| Action | `reserve_order(name, email, items, pickup_date)` | Saves an order as pending; the team confirms it by email. | An invalid email, an item listed twice, or any unavailable item: nothing is saved, and the error says which item and why. |
| Orchestration | `plan_event_order(name, email, guests, budget, pickup_date, avoid_allergens)` | Plans 2 pastries per guest within the budget, leaving out avoided allergens. It checks each item with `check_availability`, then reserves the basket with `reserve_order`. | A budget below the cheapest possible basket, or too few safe pastries left, stops it before anything is reserved. |

| Resource | Content |
|---|---|
| `bakery://menu` | Every item with its price, allergens, daily capacity and the notice it needs |
| `bakery://policies` | Hours, location, pickup, ordering, cakes, events and allergens |

## How it works

```
customer ── agent.py   OpenAI Agents SDK agent: the MCP host and client
                │      reads bakery://menu and bakery://policies at startup
                │      the model chooses a tool and its arguments
                ▼ stdio
            server.py  FastMCP server: typed tools and resources
                │      BakeryError becomes an MCP tool error
                ▼
            bakery/    the business rules, with no MCP in them ── data/orders.json
```

- The type hints in `server.py` become each tool's schema: item IDs are an enum, quantities and guests have ranges, and dates must be valid. Bad input is rejected before the bakery code runs.
- `check_availability` treats a "no" as a normal answer. `reserve_order` and `plan_event_order` raise an error when they cannot act, and then nothing changes.
- `reserve_order` checks the stock again itself and saves every line or none, so no caller can overbook.
- Expected failures reach the agent as tool errors with a clear message. Unexpected bugs are masked so internals never leak.

## Project structure

```
c5-mcp-toolkit/
├── bakery/
│   ├── menu.py          # menu, policies and rule numbers (served as resources)
│   ├── store.py         # orders saved in one JSON file
│   └── core.py          # the three tool functions, as methods of Bakery
├── server.py            # FastMCP server: three tools, two resources
├── agent.py             # OpenAI Agents SDK agent (MCP host and client)
├── tests/
│   ├── test_bakery.py   # 27 tests of the logic, including every failure case
│   └── test_server.py   # 6 tests that send real MCP requests to the server
├── docs/
│   ├── part1_summary.md # Part 1: the MCP article and the Fetch server
│   └── reflection.md
├── .env.example
└── pyproject.toml       # dependencies, managed with uv
```

## Setup

You need [uv](https://docs.astral.sh/uv/) and an OpenAI API key. uv installs Python 3.13 if you don't have it.

```bash
git clone https://github.com/samerrbarakat/c5-mcp-toolkit.git
cd c5-mcp-toolkit
uv sync
cp .env.example .env    # then put your OpenAI key in .env (PowerShell: copy .env.example .env)
```

`.env` holds `OPENAI_API_KEY` and, optionally, `OPENAI_MODEL` (default `gpt-4.1-mini`). It is git-ignored.

## Run

**Tests** (no API key needed):

```bash
uv run pytest -v
```

**The server on its own**, using FastMCP's command line as an MCP client. Use a pickup date in the next 30 days that is not a Monday:

```bash
uv run fastmcp list server.py
uv run fastmcp call server.py check_availability item_id=lemon-tart quantity=5 pickup_date=YYYY-MM-DD
uv run fastmcp call server.py bakery://menu
```

**The agent:**

```bash
uv run agent.py
```

Each tool call is printed as `->` (the call the model made) and `<-` (what the server sent back). Try:

- `What do you have that contains no nuts?` (answered from the menu resource, no tool)
- `Can I get 20 lemon tarts on Saturday?` (`check_availability`)
- `I'm hosting 25 people on Saturday, budget $150, one guest has a nut allergy. I'm Rana, rana@example.com` (`plan_event_order`)

Orders are saved in `data/orders.json`. Delete the `data` folder to start over.

## Assignment checklist

| Requirement | Where |
|---|---|
| Part 1 summary of the article and an existing server | `docs/part1_summary.md` |
| FastMCP server with one Data, one Action and one Orchestration tool | `server.py`, with the logic in `bakery/` |
| Resources for pure data lookups | `bakery://menu` and `bakery://policies` in `server.py` |
| Descriptions, typed arguments and typed outputs | `server.py` (docstrings, type hints, Pydantic models) |
| A predictable failure case for each tool | `bakery/core.py`, tested in `tests/` |
| Agents SDK host and client connected to the server | `agent.py` |
| Tests, including the failure cases | `tests/test_bakery.py`, `tests/test_server.py` |
| Screencast | Demo video link above |
| Reflection | `docs/reflection.md` |
