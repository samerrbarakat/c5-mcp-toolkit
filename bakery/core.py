"""Maison Noisette's business logic, with no MCP in it.

The three functions the MCP server exposes are methods of Bakery:
check_availability (Data), reserve_order (Action) and plan_event_order
(Orchestration). Because they know nothing about MCP, the tests can call them
directly, and the server only translates between them and the protocol.
"""

import re
import threading
from collections.abc import Callable, Iterable, Mapping
from datetime import date, timedelta
from pathlib import Path

from .menu import (ALLERGEN_NOTICE, ALLERGENS, BOOKING_WINDOW_DAYS, MENU, MENU_BY_ID,
                   PIECES_PER_GUEST)
from .store import OrderStore

MAX_QUANTITY = 500
MAX_GUESTS = 200
MAX_CATEGORIES = 3
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class BakeryError(ValueError):
    """A request the bakery cannot carry out. The message is meant for the agent to relay."""


class Bakery:
    def __init__(self, orders_path: str | Path, today: Callable[[], date] = date.today):
        self.store = OrderStore(orders_path)
        # Tests pass a fixed date here; the server uses the computer's date.
        self._today = today
        # Every reservation runs under this lock, so nothing can change
        # between checking the stock and saving the order.
        self._lock = threading.RLock()

    # ---------- Data tool ----------

    def check_availability(self, item_id: str, quantity: int, pickup_date: date) -> dict:
        """How many of an item are left for a pickup date. Changes nothing.

        A "no" (closed, too little notice, not enough left) is a normal answer
        with a reason. Only an invalid request raises BakeryError.
        """
        item = self._item(item_id)
        self._check_quantity(quantity)
        self._check_date(pickup_date)
        remaining, reason = self._stock(item, pickup_date)
        if reason is None and quantity > remaining:
            reason = f"Only {remaining} left for that date." if remaining else "Sold out for that date."
        return {
            "item_id": item_id,
            "pickup_date": pickup_date.isoformat(),
            "requested": quantity,
            "remaining": remaining,
            "available": reason is None,
            "reason": reason,
        }

    # ---------- Action tool ----------

    def reserve_order(self, name: str, email: str, items: Iterable[Mapping],
                      pickup_date: date) -> dict:
        """Save an order as pending. Every line is reserved, or none is."""
        name = name.strip()
        if not name:
            raise BakeryError("Please give the customer's name.")
        if not EMAIL_RE.match(email.strip()):
            raise BakeryError(f"'{email}' is not a valid email address.")
        items = [{"item_id": line["item_id"], "quantity": line["quantity"]} for line in items]
        if not items:
            raise BakeryError("The order has no items.")
        ids = [line["item_id"] for line in items]
        repeated = sorted({i for i in ids if ids.count(i) > 1})
        if repeated:
            raise BakeryError(f"List each item once: {', '.join(repeated)} appears more than once.")
        self._check_date(pickup_date)

        with self._lock:
            # Check every line before saving anything.
            problems, lines = [], []
            for line in items:
                item = self._item(line["item_id"])
                self._check_quantity(line["quantity"])
                remaining, reason = self._stock(item, pickup_date)
                if reason is None and line["quantity"] > remaining:
                    reason = f"only {remaining} left" if remaining else "sold out"
                if reason:
                    problems.append(f"{item['id']}: {reason}")
                lines.append({
                    "item_id": item["id"],
                    "name": item["name"],
                    "quantity": line["quantity"],
                    "unit_price": item["price"],
                    "line_total": round(line["quantity"] * item["price"], 2),
                })
            if problems:
                raise BakeryError("Nothing was reserved. " + "; ".join(problems) + ".")
            order = self.store.add({
                "status": "pending",
                "name": name,
                "email": email.strip(),
                "pickup_date": pickup_date.isoformat(),
                "lines": lines,
                "total": round(sum(line["line_total"] for line in lines), 2),
            })
        return {**order, "next_step": f"The team will email {order['email']} to confirm."}

    # ---------- Orchestration tool ----------

    def plan_event_order(self, name: str, email: str, guests: int, budget: float,
                         pickup_date: date, avoid_allergens: Iterable[str] = ()) -> dict:
        """Plan pastries for an event, then reserve them.

        Asks check_availability what is left, chooses a basket that fits the
        stock and the budget, then hands the basket to reserve_order.
        """
        avoid = sorted(set(avoid_allergens))
        unknown = [a for a in avoid if a not in ALLERGENS]
        if unknown:
            raise BakeryError(f"Unknown allergen: {', '.join(unknown)}. "
                              f"Choose from {', '.join(ALLERGENS)}.")
        if not 1 <= guests <= MAX_GUESTS:
            raise BakeryError(f"Guests must be between 1 and {MAX_GUESTS}.")
        if budget <= 0:
            raise BakeryError("The budget must be more than $0.")
        self._check_date(pickup_date)
        pieces = guests * PIECES_PER_GUEST
        without = f" without {' or '.join(avoid)}" if avoid else ""

        with self._lock:
            # 1. Single pastries only, minus anything with an avoided allergen.
            skipped, safe = [], []
            for item in MENU:
                if item["pieces"] != 1:
                    continue
                bad = sorted(set(item["allergens"]) & set(avoid))
                if bad:
                    skipped.append({"item_id": item["id"], "reason": f"contains {', '.join(bad)}"})
                else:
                    safe.append(item)
            if not safe:
                raise BakeryError(f"No pastries{without} are on the menu.")

            # 2. Ask the Data tool how many of each are left.
            stock = []
            for item in safe:
                check = self.check_availability(item["id"], 1, pickup_date)
                if check["available"]:
                    stock.append((item, check["remaining"]))
                else:
                    skipped.append({"item_id": item["id"], "reason": check["reason"]})
            if not stock:
                reasons = " ".join(sorted({s["reason"] for s in skipped}))
                raise BakeryError(f"No pastries can be planned for {pickup_date}. {reasons}")
            left = sum(n for _, n in stock)
            if left < pieces:
                raise BakeryError(f"Only {left} pastries{without} are left for {pickup_date}; "
                                  f"{pieces} are needed.")

            # 3. Choose a basket that fits the stock and the budget.
            stock.sort(key=lambda s: (s[0]["price"], s[0]["id"]))
            minimum = _cheapest_cost(stock, pieces)
            if minimum > budget:
                raise BakeryError(f"A basket for {guests} guests costs at least ${minimum:.2f} "
                                  f"on that date; the budget is ${budget:.2f}.")
            basket = _choose_basket(stock, pieces, budget)

            # 4. Hand the basket to the Action tool.
            order = self.reserve_order(name, email, basket, pickup_date)
        return {
            "order": order,
            "guests": guests,
            "pieces": pieces,
            "budget": budget,
            "skipped": skipped,
            "allergen_notice": ALLERGEN_NOTICE,
        }

    # ---------- Shared rules ----------

    def _item(self, item_id: str) -> dict:
        if item_id not in MENU_BY_ID:
            raise BakeryError(f"There is no menu item called '{item_id}'.")
        return MENU_BY_ID[item_id]

    def _check_quantity(self, quantity: int) -> None:
        if not 1 <= quantity <= MAX_QUANTITY:
            raise BakeryError(f"Quantity must be between 1 and {MAX_QUANTITY}.")

    def _check_date(self, pickup_date: date) -> None:
        today = self._today()
        if pickup_date < today:
            raise BakeryError(f"The pickup date {pickup_date} is in the past.")
        latest = today + timedelta(days=BOOKING_WINDOW_DAYS)
        if pickup_date > latest:
            raise BakeryError(f"Orders open {BOOKING_WINDOW_DAYS} days ahead; "
                              f"the latest pickup date is {latest}.")

    def _stock(self, item: dict, pickup_date: date) -> tuple[int, str | None]:
        """How many are left, and why none can be ordered (None if some can)."""
        if pickup_date.weekday() == 0:
            return 0, "Closed on Mondays."
        earliest = self._today() + timedelta(days=item["notice_days"])
        while earliest.weekday() == 0:
            earliest += timedelta(days=1)
        if pickup_date < earliest:
            return 0, (f"{item['name']} needs {item['notice_days']} days' notice; "
                       f"earliest pickup is {earliest}.")
        remaining = max(0, item["daily_capacity"] - self.store.reserved(item["id"], pickup_date))
        return remaining, None


def _cheapest_cost(stock: list[tuple[dict, int]], pieces: int) -> float:
    """The cost of filling the order with the cheapest pastries first."""
    cost = 0.0
    for item, left in stock:
        take = min(pieces, left)
        cost += take * item["price"]
        pieces -= take
    return round(cost, 2)


def _choose_basket(stock: list[tuple[dict, int]], pieces: int, budget: float) -> list[dict]:
    """Spread the pieces over up to three categories, then trim to the budget.

    stock is sorted cheapest first and holds at least `pieces` in total.
    """
    price = {item["id"]: item["price"] for item, _ in stock}
    left = {item["id"]: n for item, n in stock}
    qty = dict.fromkeys(left, 0)

    # The cheapest item of each category, cheapest categories first.
    picks, categories = [], set()
    for item, _ in stock:
        if item["category"] not in categories and len(picks) < MAX_CATEGORIES:
            categories.add(item["category"])
            picks.append(item["id"])

    # Split the pieces evenly (the remainder goes to the cheapest), capped by stock.
    share, extra = divmod(pieces, len(picks))
    for i, item_id in enumerate(picks):
        qty[item_id] = min(share + (1 if i < extra else 0), left[item_id])

    # Fill any gap left by the caps with the cheapest items that still have stock.
    gap = pieces - sum(qty.values())
    for item_id in left:
        take = min(gap, left[item_id] - qty[item_id])
        qty[item_id] += take
        gap -= take

    # Over budget: move pieces from the dearest item to a cheaper one with stock.
    def cost() -> float:
        return sum(qty[i] * price[i] for i in qty)

    while cost() > budget:
        dear = max((i for i in qty if qty[i]), key=lambda i: price[i])
        cheaper = [i for i in left if qty[i] < left[i] and price[i] < price[dear]]
        if not cheaper:
            break  # already the cheapest basket; the caller checked it fits
        qty[dear] -= 1
        qty[cheaper[0]] += 1

    return [{"item_id": i, "quantity": qty[i]} for i in left if qty[i]]
