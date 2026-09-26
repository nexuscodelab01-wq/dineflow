"""The 14 allergens the UK/EU require food businesses to declare (FIC / "Natasha's Law").

Stored as a plain JSONB list of these codes on `menu_items` — same pattern as `Restaurant.gallery`
and `Restaurant.social_links` (see `app/models/restaurant.py`). Kept as a fixed tuple, not a DB table:
the list itself is set by regulation, not by any restaurant, so there is nothing to manage.
"""

ALLERGENS: dict[str, str] = {
    "celery": "Celery",
    "cereals_gluten": "Cereals containing gluten",
    "crustaceans": "Crustaceans",
    "eggs": "Eggs",
    "fish": "Fish",
    "lupin": "Lupin",
    "milk": "Milk",
    "molluscs": "Molluscs",
    "mustard": "Mustard",
    "nuts": "Tree nuts",
    "peanuts": "Peanuts",
    "sesame": "Sesame",
    "soybeans": "Soybeans",
    "sulphites": "Sulphur dioxide / sulphites",
}


def is_allergen(value: str) -> bool:
    return value in ALLERGENS
