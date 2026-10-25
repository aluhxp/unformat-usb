"""The one place where the product name and the donation link live."""

import re
import urllib.parse

APP_NAME = "Unformat USB"
VERSION = "0.1.2"

# Voluntary donations. They are offered only after a rescue that worked,
# never before and never in the way. Empty: the offer is not shown at all.
PAYPAL_EMAIL = "aluhxp@gmail.com"    # the PayPal account donations go to
DONATION_AMOUNTS = (3, 5, 10)
DONATION_CURRENCY = "USD"
DONATION_MAX = 10000            # a typo like 5000000 should not reach PayPal


def donation_url(amount=None):
    """A PayPal payment to the account, with the amount filled in (without
    one, the person types it). PayPal's own Donate page refuses accounts from
    some countries (Ecuador among them), so this is a plain payment."""
    if not PAYPAL_EMAIL:
        return ""
    query = {"cmd": "_xclick", "business": PAYPAL_EMAIL, "item_name": f"Support {APP_NAME}",
             "currency_code": DONATION_CURRENCY, "no_shipping": "1"}
    if amount:
        query["amount"] = f"{amount:.2f}"
    return "https://www.paypal.com/cgi-bin/webscr?" + urllib.parse.urlencode(query)


def parse_amount(text):
    """What someone typed as an amount ('7', '7,50', '$ 12') or None."""
    m = re.fullmatch(r"\s*\$?\s*(\d{1,6})(?:[.,](\d{1,2}))?\s*", text or "")
    if not m:
        return None
    value = int(m.group(1)) + (int(m.group(2).ljust(2, "0")) / 100 if m.group(2) else 0)
    return value if 0 < value <= DONATION_MAX else None
