"""Maison Noisette's static facts: the menu, the policies and the rule numbers.

The MCP server exposes MENU and POLICIES as resources, and the tools read the
same objects, so every price, allergen and rule is written down once.
"""

ALLERGENS = ("gluten", "dairy", "eggs", "nuts", "sesame")

# How far ahead customers can order, and how many pastries an event gets.
BOOKING_WINDOW_DAYS = 30
PIECES_PER_GUEST = 2

ALLERGEN_NOTICE = (
    "Our kitchen handles nuts, gluten, dairy, eggs and sesame, so no item is "
    "guaranteed free of traces. Guests with a severe allergy should speak to "
    "the team before ordering."
)

# daily_capacity: how many the kitchen makes per day.
# notice_days: how many days ahead the item must be ordered (0 = same day).
MENU = [
    {"id": "butter-croissant", "name": "Butter croissant", "category": "viennoiserie",
     "price": 2.50, "pieces": 1, "allergens": ["gluten", "dairy", "eggs"],
     "daily_capacity": 80, "notice_days": 0},
    {"id": "zaatar-croissant", "name": "Za'atar croissant", "category": "viennoiserie",
     "price": 3.00, "pieces": 1, "allergens": ["gluten", "dairy", "eggs", "sesame"],
     "daily_capacity": 60, "notice_days": 0},
    {"id": "pain-au-chocolat", "name": "Pain au chocolat", "category": "viennoiserie",
     "price": 3.00, "pieces": 1, "allergens": ["gluten", "dairy", "eggs"],
     "daily_capacity": 60, "notice_days": 0},
    {"id": "pistachio-eclair", "name": "Pistachio and rose éclair", "category": "pastry",
     "price": 4.50, "pieces": 1, "allergens": ["gluten", "dairy", "eggs", "nuts"],
     "daily_capacity": 40, "notice_days": 0},
    {"id": "ashta-millefeuille", "name": "Orange-blossom ashta millefeuille", "category": "pastry",
     "price": 5.50, "pieces": 1, "allergens": ["gluten", "dairy", "eggs"],
     "daily_capacity": 30, "notice_days": 0},
    {"id": "lemon-tart", "name": "Batroun lemon tart", "category": "tart",
     "price": 4.50, "pieces": 1, "allergens": ["gluten", "dairy", "eggs"],
     "daily_capacity": 30, "notice_days": 0},
    {"id": "date-maamoul", "name": "Date maamoul", "category": "traditional",
     "price": 1.50, "pieces": 1, "allergens": ["gluten", "dairy"],
     "daily_capacity": 100, "notice_days": 0},
    {"id": "macaron-box", "name": "Box of 12 macarons", "category": "macarons",
     "price": 18.00, "pieces": 12, "allergens": ["nuts", "dairy", "eggs"],
     "daily_capacity": 15, "notice_days": 0},
    {"id": "celebration-cake", "name": "Celebration cake (serves 10)", "category": "cake",
     "price": 45.00, "pieces": 10, "allergens": ["gluten", "dairy", "eggs"],
     "daily_capacity": 4, "notice_days": 3},
]

MENU_BY_ID = {item["id"]: item for item in MENU}
ITEM_IDS = tuple(MENU_BY_ID)

POLICIES = {
    "hours": "Open Tuesday to Sunday, 7:30 to 19:30. Closed on Mondays.",
    "location": "Armenia Street, Mar Mikhael, Beirut. Phone +961 1 555 0142. "
                "Email hello@maisonnoisette.lb.",
    "pickup": "Orders placed through the assistant are collected in store on the pickup date. "
              "For delivery, please call the shop.",
    "orders": f"Orders can be placed up to {BOOKING_WINDOW_DAYS} days ahead. The assistant saves "
              "each order as pending; the team emails the customer to confirm it and arrange payment.",
    "custom_cakes": "Celebration cakes serve 10 and cost $45 each. Please order at least 3 days ahead.",
    "events": f"For events we plan {PIECES_PER_GUEST} pastries per guest, choosing from up to three "
              "categories to fit the budget.",
    "allergens": ALLERGEN_NOTICE,
}
