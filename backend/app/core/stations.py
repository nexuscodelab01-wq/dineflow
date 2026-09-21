"""Kitchen stations: where a dish is made, so each screen shows only its own work."""

STATIONS = ("KITCHEN", "BAR", "DESSERT")
DEFAULT_STATION = "KITCHEN"

# Used when a restaurant is created from a template (category name -> station); anything else is the kitchen.
CATEGORY_STATIONS = {"Drinks": "BAR", "Coffee": "BAR", "Desserts": "DESSERT"}


def is_station(value: str) -> bool:
    return value in STATIONS
