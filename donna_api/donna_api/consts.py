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
    "": "free",
    # "prod_SfBenX57C9P5Gk": "pro",
    # "prod_SfBjjdd9eOeonR": "studio"
    # test
    "prod_SfCXpkM5MHwplv": "pro",
}

REVERSED_TIER_MAP = {v: k for k, v in TIER_MAP.items()}

CREDITS_BY_TIER = {"free": 15, "pro": 200, "studio": 1000}

# TODO: sync this to the stripe api
PRICE_BY_TIER = {"free": 0, "pro": 24, "studio": 99}

CARD_BRAND_LOGOS = {
    "visa": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d6/Visa_2021.svg/1200px-Visa_2021.svg.png",
    "mastercard": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2a/Mastercard-logo.svg/1200px-Mastercard-logo.svg.png",
    "amex": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fa/American_Express_logo_%282018%29.svg/1200px-American_Express_logo_%282018%29.svg.png",
    "discover": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/57/Discover_Card_logo.svg/2560px-Discover_Card_logo.svg.png",
}
