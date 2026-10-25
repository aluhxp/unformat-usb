"""The one place where the product name and the donation link live."""

import re

APP_NAME = "Rescatín"
VERSION = "0.1.0"

# Voluntary donations. They are offered only after a rescue that worked,
# never before and never in the way. Empty: the offer is not shown at all.
PAYPAL_ME = ""                  # the name after paypal.me/, e.g. "aluhxp"
DONATION_AMOUNTS = (3, 5, 10)
DONATION_CURRENCY = "USD"
DONATION_MAX = 10000            # a typo like 5000000 should not reach PayPal


def donation_url(amount=None):
    """PayPal.me link, with the amount filled in when one is given."""
    if not PAYPAL_ME:
        return ""
    url = f"https://www.paypal.com/paypalme/{PAYPAL_ME}"
    if amount:
        value = f"{amount:.2f}".rstrip("0").rstrip(".")
        url += f"/{value}{DONATION_CURRENCY}"
    return url


def parse_amount(text):
    """What someone typed as an amount ('7', '7,50', '$ 12') or None."""
    m = re.fullmatch(r"\s*\$?\s*(\d{1,6})(?:[.,](\d{1,2}))?\s*", text or "")
    if not m:
        return None
    value = int(m.group(1)) + (int(m.group(2).ljust(2, "0")) / 100 if m.group(2) else 0)
    return value if 0 < value <= DONATION_MAX else None
