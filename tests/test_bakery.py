"""Tests for the bakery logic behind the three tools.

Every test gets a fresh Bakery with its own empty orders file in a temporary
folder and a fixed "today", so the results never depend on the real date and
no test can affect another.
"""

from datetime import date

import pytest

from bakery import Bakery, BakeryError

TODAY = date(2026, 11, 1)      # a Sunday
SATURDAY = date(2026, 11, 7)
MONDAY = date(2026, 11, 9)


@pytest.fixture
def bakery(tmp_path):
    return Bakery(tmp_path / "orders.json", today=lambda: TODAY)


def quantities(order):
    """An order's lines as {item_id: quantity}."""
    return {line["item_id"]: line["quantity"] for line in order["lines"]}


# ---------- Data tool: check_availability ----------

def test_check_reports_what_is_left(bakery):
    result = bakery.check_availability("lemon-tart", 5, SATURDAY)
    assert result["available"] is True
    assert result["remaining"] == 30
    assert result["reason"] is None


def test_check_says_no_when_too_few_are_left(bakery):
    bakery.reserve_order("Rana", "rana@example.com",
                         [{"item_id": "lemon-tart", "quantity": 25}], SATURDAY)
    result = bakery.check_availability("lemon-tart", 10, SATURDAY)
    assert result["available"] is False
    assert result["remaining"] == 5
    assert result["reason"] == "Only 5 left for that date."


def test_check_says_closed_on_mondays(bakery):
    result = bakery.check_availability("butter-croissant", 5, MONDAY)
    assert result["available"] is False
    assert result["reason"] == "Closed on Mondays."


def test_check_enforces_cake_notice(bakery):
    result = bakery.check_availability("celebration-cake", 1, date(2026, 11, 3))
    assert result["available"] is False
    assert "earliest pickup is 2026-11-04" in result["reason"]


def test_earliest_cake_pickup_skips_mondays(tmp_path):
    bakery = Bakery(tmp_path / "orders.json", today=lambda: date(2026, 11, 6))
    result = bakery.check_availability("celebration-cake", 1, date(2026, 11, 8))
    # Friday plus 3 days is a Monday, when the shop is closed.
    assert "earliest pickup is 2026-11-10" in result["reason"]


def test_check_changes_nothing(bakery):
    bakery.check_availability("lemon-tart", 5, SATURDAY)
    assert not bakery.store.path.exists()


@pytest.mark.parametrize("item_id, quantity, pickup_date, message", [
    ("lemon-tart", 1, date(2026, 10, 30), "in the past"),
    ("lemon-tart", 1, date(2026, 12, 15), "30 days ahead"),
    ("bagel", 1, SATURDAY, "no menu item"),
    ("lemon-tart", 0, SATURDAY, "between 1 and 500"),
], ids=["past-date", "beyond-window", "unknown-item", "zero-quantity"])
def test_check_rejects_invalid_requests(bakery, item_id, quantity, pickup_date, message):
    with pytest.raises(BakeryError, match=message):
        bakery.check_availability(item_id, quantity, pickup_date)


# ---------- Action tool: reserve_order ----------

def test_reserve_saves_a_pending_order(bakery):
    order = bakery.reserve_order("Rana", "rana@example.com",
                                 [{"item_id": "lemon-tart", "quantity": 4},
                                  {"item_id": "date-maamoul", "quantity": 10}], SATURDAY)
    assert order["order_id"] == "MN-0001"
    assert order["status"] == "pending"
    assert order["total"] == 33.0    # 4 x $4.50 + 10 x $1.50
    assert "rana@example.com" in order["next_step"]
    assert [saved["order_id"] for saved in bakery.store.all()] == ["MN-0001"]


def test_reserve_uses_up_capacity(bakery):
    bakery.reserve_order("Rana", "rana@example.com",
                         [{"item_id": "lemon-tart", "quantity": 10}], SATURDAY)
    assert bakery.check_availability("lemon-tart", 1, SATURDAY)["remaining"] == 20


def test_reserve_is_all_or_nothing(bakery):
    with pytest.raises(BakeryError, match="Nothing was reserved. lemon-tart: only 30 left"):
        bakery.reserve_order("Rana", "rana@example.com",
                             [{"item_id": "butter-croissant", "quantity": 5},
                              {"item_id": "lemon-tart", "quantity": 31}], SATURDAY)
    # The croissants were available, but they were not saved either.
    assert bakery.store.all() == []


def test_reserve_refuses_a_closed_day(bakery):
    with pytest.raises(BakeryError, match="Closed on Mondays"):
        bakery.reserve_order("Rana", "rana@example.com",
                             [{"item_id": "lemon-tart", "quantity": 1}], MONDAY)


@pytest.mark.parametrize("name, email, items, message", [
    ("  ", "rana@example.com", [{"item_id": "lemon-tart", "quantity": 1}], "customer's name"),
    ("Rana", "rana-at-example", [{"item_id": "lemon-tart", "quantity": 1}], "not a valid email"),
    ("Rana", "rana@example.com", [], "no items"),
    ("Rana", "rana@example.com", [{"item_id": "lemon-tart", "quantity": 1},
                                  {"item_id": "lemon-tart", "quantity": 2}], "List each item once"),
], ids=["blank-name", "bad-email", "no-items", "repeated-item"])
def test_reserve_rejects_invalid_requests(bakery, name, email, items, message):
    with pytest.raises(BakeryError, match=message):
        bakery.reserve_order(name, email, items, SATURDAY)
    assert bakery.store.all() == []


# ---------- Orchestration tool: plan_event_order ----------

def test_plan_builds_the_example_basket(bakery):
    result = bakery.plan_event_order("Rana", "rana@example.com", guests=25, budget=150,
                                     pickup_date=SATURDAY, avoid_allergens=["nuts"])
    assert quantities(result["order"]) == {"date-maamoul": 17, "butter-croissant": 17,
                                           "lemon-tart": 16}
    assert result["order"]["total"] == 140.0
    assert result["pieces"] == 50
    assert {"item_id": "pistachio-eclair", "reason": "contains nuts"} in result["skipped"]
    assert "nuts" in result["allergen_notice"]
    assert len(bakery.store.all()) == 1


def test_plan_adapts_to_what_is_left(bakery):
    # The first event takes 16 of the 30 lemon tarts.
    bakery.plan_event_order("Rana", "rana@example.com", 25, 150, SATURDAY, ["nuts"])
    second = bakery.plan_event_order("Omar", "omar@example.com", 25, 150, SATURDAY)
    # Only 14 tarts are left, so the gap goes to the cheapest item with stock.
    assert quantities(second["order"]) == {"date-maamoul": 19, "butter-croissant": 17,
                                           "lemon-tart": 14}


def test_plan_trims_the_basket_to_the_budget(bakery):
    result = bakery.plan_event_order("Lea", "lea@example.com", 20, 70, SATURDAY)
    assert quantities(result["order"]) == {"date-maamoul": 30, "butter-croissant": 10}
    assert result["order"]["total"] <= 70


@pytest.mark.parametrize("guests, budget, pickup_date, avoid, message", [
    (25, 60, SATURDAY, ["nuts"], r"costs at least \$75\.00"),
    (200, 5000, SATURDAY, ["nuts", "sesame"], "Only 300 pastries without nuts or sesame"),
    (10, 100, SATURDAY, ["gluten"], "No pastries without gluten"),
    (10, 100, MONDAY, [], "Closed on Mondays"),
    (0, 100, SATURDAY, [], "between 1 and 200"),
    (10, 100, SATURDAY, ["peanuts"], "Unknown allergen"),
], ids=["budget-too-low", "not-enough-left", "nothing-safe", "monday", "zero-guests",
        "unknown-allergen"])
def test_plan_rejects_what_it_cannot_do(bakery, guests, budget, pickup_date, avoid, message):
    with pytest.raises(BakeryError, match=message):
        bakery.plan_event_order("Rana", "rana@example.com", guests, budget, pickup_date, avoid)
    assert bakery.store.all() == []
