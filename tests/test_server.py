"""Tests for the MCP layer: what an MCP client sees when it talks to the server.

The client runs in memory against the server object, so these tests send real
MCP requests (list tools, call a tool, read a resource) without starting a
process. The bakery is swapped for one with a temporary orders file and a
fixed date, as in test_bakery.py.
"""

import json
from datetime import date

import pytest
from fastmcp import Client

import server
from bakery import Bakery

pytestmark = pytest.mark.anyio

TODAY = date(2026, 11, 1)    # a Sunday


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "bakery", Bakery(tmp_path / "orders.json", today=lambda: TODAY))
    return Client(server.mcp)


async def test_server_has_exactly_three_tools(client):
    async with client:
        tools = await client.list_tools()
    assert {tool.name for tool in tools} == {"check_availability", "reserve_order",
                                            "plan_event_order"}


async def test_resources_serve_the_menu_and_policies(client):
    async with client:
        menu = json.loads((await client.read_resource("bakery://menu"))[0].text)
        policies = json.loads((await client.read_resource("bakery://policies"))[0].text)
    assert len(menu) == 9
    assert policies["hours"].endswith("Closed on Mondays.")


async def test_check_availability_round_trip(client):
    async with client:
        result = await client.call_tool("check_availability", {
            "item_id": "lemon-tart", "quantity": 5, "pickup_date": "2026-11-07"})
    assert result.structured_content["available"] is True
    assert result.structured_content["remaining"] == 30


async def test_bakery_error_reaches_the_agent_as_a_tool_error(client):
    async with client:
        result = await client.call_tool("check_availability", {
            "item_id": "lemon-tart", "quantity": 5, "pickup_date": "2026-10-30"},
            raise_on_error=False)
    assert result.is_error
    assert result.content[0].text == "The pickup date 2026-10-30 is in the past."


async def test_schema_rejects_an_unknown_item(client):
    async with client:
        result = await client.call_tool("check_availability", {
            "item_id": "bagel", "quantity": 5, "pickup_date": "2026-11-07"},
            raise_on_error=False)
    assert result.is_error


async def test_plan_event_order_round_trip(client):
    async with client:
        result = await client.call_tool("plan_event_order", {
            "name": "Rana", "email": "rana@example.com", "guests": 25, "budget": 150,
            "pickup_date": "2026-11-07", "avoid_allergens": ["nuts"]})
    plan = result.structured_content
    assert plan["order"]["order_id"] == "MN-0001"
    assert plan["order"]["total"] == 140.0
    assert server.bakery.store.all()[0]["name"] == "Rana"
