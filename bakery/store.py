"""The order store: every order saved in one JSON file.

A JSON file keeps the Action tool's effect visible: open the file during the
demo and watch a new order appear.
"""

import json
from datetime import date
from pathlib import Path


class OrderStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def all(self) -> list[dict]:
        """Every saved order, oldest first. A missing file means no orders yet."""
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def reserved(self, item_id: str, pickup_date: date) -> int:
        """How many of an item are already ordered for a pickup date."""
        day = pickup_date.isoformat()
        return sum(
            line["quantity"]
            for order in self.all()
            if order["pickup_date"] == day
            for line in order["lines"]
            if line["item_id"] == item_id
        )

    def add(self, order: dict) -> dict:
        """Give the order the next ID, save it, and return it."""
        orders = self.all()
        order = {"order_id": f"MN-{len(orders) + 1:04d}", **order}
        orders.append(order)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write a temporary file, then swap it in, so a crash halfway
        # through never leaves a half-written orders file.
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(orders, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)
        return order
