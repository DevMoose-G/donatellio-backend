from donna_common.settings import settings

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


if settings.debug:
    TIER_MAP = {
        "": "free",
        "prod_SfCXpkM5MHwplv": "pro",
    }
    PACKAGE_MAP = {
        "prod_Sgvbdr4C4lpCvr": "starter",
        "prod_SgvcdNFLJ1GOHq": "indie",
        "prod_SgvcdYDH1LG6hj": "studio",
    }
else:
    TIER_MAP = {
        "": "free",
        "prod_SfBenX57C9P5Gk": "pro",
        "prod_SfBjjdd9eOeonR": "studio",
    }

    PACKAGE_MAP = {
        "prod_SguUoV0ZU9X3Gd": "starter",
        "prod_SguVA1ZF7mPCCa": "indie",
        "prod_SguWmIZH5x48cL": "studio",
    }

REVERSED_TIER_MAP = {v: k for k, v in TIER_MAP.items()}
REVERSED_PACKAGE_MAP = {v: k for k, v in PACKAGE_MAP.items()}

CREDITS_BY_TIER = {"free": 20, "pro": 200, "studio": 1000}
CREDITS_BY_PACKAGE = {"starter": 50, "indie": 250, "studio": 1000}

# TODO: sync this to the stripe api
PRICE_BY_TIER = {"free": 0, "pro": 24, "studio": 99}

CARD_BRAND_LOGOS = {
    "visa": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d6/Visa_2021.svg/1200px-Visa_2021.svg.png",
    "mastercard": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2a/Mastercard-logo.svg/1200px-Mastercard-logo.svg.png",
    "amex": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fa/American_Express_logo_%282018%29.svg/1200px-American_Express_logo_%282018%29.svg.png",
    "discover": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/57/Discover_Card_logo.svg/2560px-Discover_Card_logo.svg.png",
}
