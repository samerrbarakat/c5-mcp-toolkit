"""Maison Noisette ordering assistant: an OpenAI Agents SDK agent on top of the bakery MCP server.

The agent is the MCP host. It starts server.py as a subprocess, talks to it
over stdio through the SDK's MCP client, reads the menu and policies resources
into its instructions, and lets the model call the three tools. Every tool
call and its result is printed, so the round trip through the server is
visible.

Run it with:  uv run agent.py
It needs OPENAI_API_KEY=sk-... in a .env file next to this one.
"""

import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

from agents import Agent, Runner
from agents.items import ToolCallItem, ToolCallOutputItem
from agents.mcp import MCPServerStdio
from dotenv import load_dotenv

HERE = Path(__file__).parent
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

INSTRUCTIONS = """You are Camille, the ordering assistant of Maison Noisette, a French-Lebanese \
pâtisserie in Mar Mikhael, Beirut.

Today is {today}. Turn days the customer names, such as "Saturday", into YYYY-MM-DD dates yourself.

FACTS
Answer questions about the menu, prices and policies only from these. Never invent anything.

Menu (prices in USD):
{menu}

Policies:
{policies}

When a question is about allergens or dietary needs, go through every menu item, list all the ones
that match, and add the allergens policy: no item is guaranteed free of traces.

TOOLS
- check_availability: before promising that an item can be ordered for a date.
- reserve_order: when the customer has chosen exact items and quantities.
- plan_event_order: when the customer wants pastries for an event from a guest count and a budget.
Only reserve when the customer has clearly asked to order. Ask for their name and email first if
you do not have them. When a tool returns an error, explain it in plain words and suggest what the
customer could change.

REPLIES
Warm and short: two to four sentences, unless you are listing items. After an order, always give the
order ID (such as MN-0001) and the total, and say the team will email to confirm it. After an event
plan, list what was chosen and pass on the allergen notice."""


async def main() -> None:
    load_dotenv(HERE / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("Add OPENAI_API_KEY=sk-... to a .env file next to agent.py.")

    server = MCPServerStdio(
        name="Maison Noisette",
        params={"command": sys.executable, "args": [str(HERE / "server.py")]},
        cache_tools_list=True,
        client_session_timeout_seconds=30,
    )
    async with server:
        # Resources are read by the host, not chosen by the model, so the
        # agent's code loads them here and puts them in the instructions.
        menu = await read_json(server, "bakery://menu")
        policies = await read_json(server, "bakery://policies")
        today = date.today()
        agent = Agent(
            name="Camille",
            model=MODEL,
            instructions=INSTRUCTIONS.format(
                today=f"{today:%A} {today.isoformat()}",
                menu=format_menu(menu),
                policies=format_policies(policies),
            ),
            mcp_servers=[server],
        )
        await chat(agent)


async def read_json(server: MCPServerStdio, uri: str):
    result = await server.read_resource(uri)
    return json.loads(result.contents[0].text)


def format_menu(menu: list[dict]) -> str:
    """One line per item. Models read this more reliably than a block of JSON."""
    lines = []
    for item in menu:
        notice = f"; order {item['notice_days']} days ahead" if item["notice_days"] else ""
        lines.append(f"- {item['name']} [{item['id']}], {item['category']}: ${item['price']:.2f} each; "
                     f"contains {', '.join(item['allergens'])}{notice}")
    return "\n".join(lines)


def format_policies(policies: dict) -> str:
    return "\n".join(f"- {topic}: {text}" for topic, text in policies.items())


async def chat(agent: Agent) -> None:
    print(f"Chat with Camille ({MODEL}). Type 'quit' to stop.\n")
    history = []
    while True:
        try:
            message = (await asyncio.to_thread(input, "You: ")).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if message.lower() in {"", "quit", "exit"}:
            break
        result = await Runner.run(agent, history + [{"role": "user", "content": message}])
        show_tool_calls(result)
        print(f"\nCamille: {result.final_output}\n")
        history = result.to_input_list()


def show_tool_calls(result) -> None:
    """Print each tool call the model made and what the MCP server sent back."""
    for item in result.new_items:
        if isinstance(item, ToolCallItem):
            print(f"  -> {item.raw_item.name}({item.raw_item.arguments})")
        elif isinstance(item, ToolCallOutputItem):
            print(f"  <- {shorten(as_text(item.output))}")


def as_text(output) -> str:
    """MCP results arrive as one or more content parts; keep their text."""
    parts = output if isinstance(output, list) else [output]
    return " ".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in parts)


def shorten(text: str, limit: int = 300) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + " ..."


if __name__ == "__main__":
    # Windows terminals may not default to UTF-8; this keeps accents and
    # symbols in the model's replies from crashing print().
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    asyncio.run(main())
