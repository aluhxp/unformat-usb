from urllib.parse import parse_qs, urlparse

from usbrescue import brand


def test_no_account_means_no_offer(monkeypatch):
    monkeypatch.setattr(brand, "PAYPAL_EMAIL", "")
    assert brand.donation_url(5) == ""


def test_the_link_goes_to_the_account_with_the_amount(monkeypatch):
    monkeypatch.setattr(brand, "PAYPAL_EMAIL", "someone@example.com")
    url = urlparse(brand.donation_url(7.5))
    assert (url.netloc, url.path) == ("www.paypal.com", "/donate/")
    q = parse_qs(url.query)
    assert q["business"] == ["someone@example.com"]
    assert (q["amount"], q["currency_code"]) == (["7.50"], ["USD"])
    assert "amount" not in parse_qs(urlparse(brand.donation_url()).query)


def test_typed_amounts():
    assert brand.parse_amount("7") == 7
    assert brand.parse_amount("7,50") == 7.5
    assert brand.parse_amount(" $ 12.5 ") == 12.5
    for bad in ("", "0", "-3", "abc", "1e9", "5000000", "3,333"):
        assert brand.parse_amount(bad) is None
