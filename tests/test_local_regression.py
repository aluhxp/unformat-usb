"""Optional check against a real drive image kept outside the repository.

    USBRESCUE_REAL_IMAGE=/path/to/drive.img
    USBRESCUE_EXPECTED="folders,files,orphan candidates"   e.g. "120,3400,12"

Real images hold personal data: never commit them, their listings or their paths."""

import os

import pytest

from helpers import run

IMAGE = os.environ.get("USBRESCUE_REAL_IMAGE")
EXPECTED = os.environ.get("USBRESCUE_EXPECTED")


@pytest.mark.skipif(not (IMAGE and EXPECTED), reason="no real image configured")
def test_real_image_still_lists_the_same():
    result, _, _ = run(IMAGE)
    got = (len(result.contents), len(result.plans), len(result.orphans))
    assert got == tuple(int(x) for x in EXPECTED.split(","))
