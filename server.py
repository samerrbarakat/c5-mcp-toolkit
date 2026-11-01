"""Maison Noisette MCP server.

Exposes the bakery logic to any MCP client:
    Data tool:           check_availability
    Action tool:         reserve_order
    Orchestration tool:  plan_event_order
    Resources:           bakery://menu, bakery://policies

The rules live in the bakery package. This file only declares the typed
interface the agent sees and turns BakeryError into an MCP tool error.

Run it with:  uv run server.py   (stdio, the transport the agent uses)
"""

from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

from bakery import ALLERGENS, ITEM_IDS, MENU, POLICIES, Bakery, BakeryError

ORDERS_PATH = Path(__file__).parent / "data" / "orders.json"

# mask_error_details: an unexpected bug reaches the agent as a generic error
# instead of leaking internals. Expected failures are raised as ToolError,
# whose message always gets through.
mcp = FastMCP("Maison Noisette", mask_error_details=True)
bakery = Bakery(ORDERS_PATH)

ItemId = Literal[ITEM_IDS]
Allergen = Literal[ALLERGENS]
Quantity = Annotated[int, Field(ge=1, le=500)]
PickupDate = Annotated[date, Field(description="Pickup date as YYYY-MM-DD.")]


def run(method, *args):
    """Call a bakery method, turning an expected failure into a ToolError."""
    try:
        return method(*args)
    except BakeryError as e:
        raise ToolError(str(e)) from e


# ---------- Typed inputs and outputs ----------

class OrderItem(BaseModel):
    item_id: ItemId
    quantity: Quantity


class Availability(BaseModel):
    item_id: str
    pickup_date: date
    requested: int
    remaining: int
    available: bool
    reason: str | None


class OrderLine(BaseModel):
    item_id: str
    name: str
    quantity: int
    unit_price: float
    line_total: float


class Order(BaseModel):
    order_id: str
    status: Literal["pending"]
    name: str
    email: str
    pickup_date: date
    lines: list[OrderLine]
    total: float
    next_step: str


class SkippedItem(BaseModel):
    item_id: str
    reason: str


class EventPlan(BaseModel):
    order: Order
    guests: int
    pieces: int
    budget: float
    skipped: list[SkippedItem]
    allergen_notice: str


# ---------- Tools ----------

@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
def check_availability(
    item_id: Annotated[ItemId, Field(description="The item's id from the menu.")],
    quantity: Annotated[Quantity, Field(description="How many the customer wants.")],
    pickup_date: PickupDate,
) -> Availability:
    """Check how many of one menu item are left for a pickup date. Read-only: it never reserves anything.

    Use it when a customer asks whether something can be ordered. A "no" is a
    normal result: available is false and reason says why (closed on Mondays,
    not enough notice, or too few left).
    """
    return Availability.model_validate(run(bakery.check_availability, item_id, quantity, pickup_date))


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False,
                       "openWorldHint": False})
def reserve_order(
    name: Annotated[str, Field(description="The customer's name.")],
    email: Annotated[str, Field(description="The customer's email, for the team's confirmation.")],
    items: Annotated[list[OrderItem], Field(min_length=1, description="Each item once, with its quantity.")],
    pickup_date: PickupDate,
) -> Order:
    """Reserve chosen menu items for a customer and save the order as pending; the team confirms it by email.

    Use it when the customer has picked exact items and quantities and has given
    their name and email. Every item is reserved or none is: if any item is
    unavailable, nothing is saved and the error says which item and why. To plan
    an event from a guest count and a budget, use plan_event_order instead.
    """
    lines = [item.model_dump() for item in items]
    return Order.model_validate(run(bakery.reserve_order, name, email, lines, pickup_date))


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False,
                       "openWorldHint": False})
def plan_event_order(
    name: Annotated[str, Field(description="The customer's name.")],
    email: Annotated[str, Field(description="The customer's email, for the team's confirmation.")],
    guests: Annotated[int, Field(ge=1, le=200, description="Number of guests.")],
    budget: Annotated[float, Field(gt=0, description="Most the customer wants to spend, in USD.")],
    pickup_date: PickupDate,
    avoid_allergens: Annotated[list[Allergen], Field(description="Allergens to leave out.")] = [],
) -> EventPlan:
    """Plan pastries for an event and reserve them, from a guest count and a budget.

    Plans 2 pastries per guest from up to three categories, leaves out avoided
    allergens and anything sold out, keeps within the budget, then saves the
    order as pending. Use it only when the customer wants to order for an event
    and has given their name and email. Always show the customer the
    allergen_notice in the result.
    """
    return EventPlan.model_validate(
        run(bakery.plan_event_order, name, email, guests, budget, pickup_date, avoid_allergens))


# ---------- Resources ----------

@mcp.resource("bakery://menu", mime_type="application/json",
              description="Every menu item: id, name, category, price in USD, pieces, allergens, "
                          "daily capacity and days of notice needed.")
def menu() -> list[dict]:
    return MENU


@mcp.resource("bakery://policies", mime_type="application/json",
              description="Opening hours, location, pickup, ordering, cakes, events and allergens.")
def policies() -> dict:
    return POLICIES


if __name__ == "__main__":
    # No startup banner: the agent shows this process's output in its own terminal.
    mcp.run(show_banner=False)
