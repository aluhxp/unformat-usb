from usbrescue import brand


def test_no_link_means_no_offer(monkeypatch):
    monkeypatch.setattr(brand, "PAYPAL_ME", "")
    assert brand.donation_url(5) == ""


def test_the_link_carries_the_amount(monkeypatch):
    monkeypatch.setattr(brand, "PAYPAL_ME", "someone")
    assert brand.donation_url(5) == "https://www.paypal.com/paypalme/someone/5USD"
    assert brand.donation_url(7.5) == "https://www.paypal.com/paypalme/someone/7.5USD"
    assert brand.donation_url() == "https://www.paypal.com/paypalme/someone"


def test_typed_amounts():
    assert brand.parse_amount("7") == 7
    assert brand.parse_amount("7,50") == 7.5
    assert brand.parse_amount(" $ 12.5 ") == 12.5
    for bad in ("", "0", "-3", "abc", "1e9", "5000000", "3,333"):
        assert brand.parse_amount(bad) is None
