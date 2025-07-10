BASE_URL = "http://localhost:8000"


# pricing info
TIER_FEATURES = {
    "free": ["Generate 3D models from text", "Decent queue priority"],
    "pro": [
        "Everything in Free",
        # "Download community models",
        # "Access to all public style collections",
        # "2 custom style collections",
        "Good queue priority",
    ],
    "studio": [
        "Everything in Pro",
        # "10 custom style collections",
        "Better queue priority",
    ],
    "enterprise": [
        "Everything in Studio",
        # "Unlimited style collections",
        "Best queue priority",
    ],
}

TIER_MAP = {
    "":"free",
    "prod_Scu7PE0RUE0bkF": "pro",
    "prod_ScyEebHjNsSFAa": "studio"
}
REVERSED_TIER_MAP = {v: k for k, v in TIER_MAP.items()}

CREDITS_BY_TIER = {
    "free": 15,
    "pro": 200,
    "studio": 1000
}

# TODO: sync this to the stripe api
PRICE_BY_TIER = {
    "free": 0,
    "pro": 24,
    "studio": 99
}