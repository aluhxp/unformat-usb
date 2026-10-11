"""The safety copy of a drive."""

import json
import os

import pytest

from helpers import run
from test_exfat import build, expected_in_folders, in_folders
from usbrescue.core import imaging
from usbrescue.core.reader import Source

SIZE = 9 * 1024 * 1024 + 700            # not a whole number of blocks


@pytest.fixture
def drive(tmp_path):
    path = tmp_path / "drive.bin"
    path.write_bytes(os.urandom(SIZE))
    return path


def copy(source, image, stop_after=None):
    disk = Source(str(source))
    events = []
    for i, e in enumerate(imaging.make_image(disk, str(source), str(image))):
        events.append(e)
        if stop_after is not None and i + 1 >= stop_after:
            break
    disk.close()
    return events


def test_the_copy_is_identical(drive, tmp_path):
    image = tmp_path / "copy.img"
    events = copy(drive, image)
    assert isinstance(events[-1], imaging.ImageFinished) and events[-1].bad_bytes == 0
    assert image.read_bytes() == drive.read_bytes()
    assert events[-2].done == SIZE


def flaky(disk, bad_ranges):
    original = disk._raw

    def raw(off, n):
        if any(off < b + ln and off + n > b for b, ln in bad_ranges):
            raise OSError(5, "simulated bad sector")
        return original(off, n)

    disk._raw = raw


def test_bad_sectors_cost_only_themselves(drive, tmp_path):
    image = tmp_path / "copy.img"
    bad = [(3 * 1024 * 1024 + 4096, 1024), (7 * 1024 * 1024 + 512 * 9, 512)]
    disk = Source(str(drive))
    flaky(disk, bad)
    events = list(imaging.make_image(disk, str(drive), str(image)))
    assert events[-1].bad_bytes == 1536
    want = bytearray(drive.read_bytes())
    for start, length in bad:
        want[start:start + length] = b"\x00" * length
    assert image.read_bytes() == bytes(want)        # every readable sector around them came through
    assert any(e.retrying for e in events if isinstance(e, imaging.ImageProgress))
    assert json.load(open(imaging.map_path_of(str(image))))["bad"] == [[b, n] for b, n in bad]


def test_an_interrupted_copy_resumes_without_starting_over(drive, tmp_path):
    image = tmp_path / "copy.img"
    copy(drive, image, stop_after=4)                # stopped after 4 blocks
    assert json.load(open(imaging.map_path_of(str(image))))["position"] == 4 * imaging.BLOCK
    disk = Source(str(drive))
    reads = []
    original = disk._raw
    disk._raw = lambda off, n: (reads.append((off, n)), original(off, n))[1]
    list(imaging.make_image(disk, str(drive), str(image)))
    copied = [off for off, n in reads if n > 64 * 1024]     # leaves out the fingerprint read
    assert min(copied) == 4 * imaging.BLOCK         # nothing before that was read again
    assert image.read_bytes() == drive.read_bytes()


def test_a_finished_copy_is_not_made_again(drive, tmp_path):
    image = tmp_path / "copy.img"
    copy(drive, image)
    events = copy(drive, image)
    assert len(events) == 1 and isinstance(events[0], imaging.ImageFinished)


def test_a_map_from_another_drive_is_ignored(drive, tmp_path):
    image = tmp_path / "copy.img"
    copy(drive, image, stop_after=2)
    other = tmp_path / "other.bin"
    other.write_bytes(os.urandom(2 * 1024 * 1024))
    copy(other, image)
    assert image.read_bytes() == other.read_bytes()


def test_a_map_from_another_drive_of_the_same_size_is_ignored_too(drive, tmp_path):
    image = tmp_path / "copy.img"
    copy(drive, image, stop_after=2)
    twin = tmp_path / "twin.bin"
    twin.write_bytes(os.urandom(SIZE))
    copy(twin, image)
    assert image.read_bytes() == twin.read_bytes()


def test_space_is_checked_before_starting(tmp_path):
    free, fits, roomy = imaging.space_check(1024, tmp_path / "not" / "yet")
    assert fits and roomy and free > 0
    assert imaging.space_check(free * 4, tmp_path)[1:] == (False, False)


def test_the_rescue_works_from_the_copy(tmp_path):
    drive = tmp_path / "pendrive.img"
    img = build(drive)
    img.windows_quick_format()
    img.close()
    image = tmp_path / "copy.img"
    copy(drive, image)
    run(image, tmp_path / "out")
    assert in_folders(tmp_path / "out") == expected_in_folders()
