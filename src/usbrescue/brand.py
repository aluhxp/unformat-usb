"""The one place where the product name and the donation link live."""

import re
import urllib.parse

APP_NAME = "Unformat USB"
VERSION = "0.1.0"

# Voluntary donations. They are offered only after a rescue that worked,
# never before and never in the way. Empty: the offer is not shown at all.
PAYPAL_EMAIL = "aluhxp@gmail.com"    # the PayPal account donations go to
DONATION_AMOUNTS = (3, 5, 10)
DONATION_CURRENCY = "USD"
DONATION_MAX = 10000            # a typo like 5000000 should not reach PayPal


def donation_url(amount=None):
    """PayPal's donation page for the account, with the amount filled in."""
    if not PAYPAL_EMAIL:
        return ""
    query = {"business": PAYPAL_EMAIL, "currency_code": DONATION_CURRENCY,
             "item_name": f"{APP_NAME}"}
    if amount:
        query["amount"] = f"{amount:.2f}"
    return "https://www.paypal.com/donate/?" + urllib.parse.urlencode(query)


def parse_amount(text):
    """What someone typed as an amount ('7', '7,50', '$ 12') or None."""
    m = re.fullmatch(r"\s*\$?\s*(\d{1,6})(?:[.,](\d{1,2}))?\s*", text or "")
    if not m:
        return None
    value = int(m.group(1)) + (int(m.group(2).ljust(2, "0")) / 100 if m.group(2) else 0)
    return value if 0 < value <= DONATION_MAX else None
