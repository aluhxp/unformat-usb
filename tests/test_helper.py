"""The privileged reader, exercised without privileges on an image file."""

import os
import sys

import pytest

from helpers import files_under, run
from test_exfat import build, expected_in_folders, in_folders
from usbrescue import helper
from usbrescue.core.reader import HelperSource, Source

HELPER = [sys.executable, helper.__file__]


def test_reads_match_a_direct_read(tmp_path):
    path = tmp_path / "data.bin"
    path.write_bytes(os.urandom(300_000))
    direct, through = Source(str(path)), HelperSource(str(path), command=HELPER)
    assert through.size == direct.size
    for off, n in ((0, 512), (4096, 70_000), (299_000, 5000), (300_000, 10)):
        assert through.read(off, n) == direct.read(off, n)
    through.close()


def test_a_whole_recovery_works_through_the_helper(tmp_path):
    path = tmp_path / "pendrive.img"
    img = build(path)
    img.windows_quick_format()
    img.close()
    run(path, tmp_path / "out", disk=HelperSource(str(path), command=HELPER))
    assert in_folders(tmp_path / "out") == expected_in_folders()


def test_refusal_is_reported_as_missing_permission(tmp_path):
    with pytest.raises(PermissionError):
        HelperSource(str(tmp_path / "does-not-exist"), command=HELPER)
    with pytest.raises(PermissionError):
        HelperSource(str(tmp_path), command=["false"])     # like cancelling the password prompt


def test_the_helper_only_opens_for_reading():
    source = open(helper.__file__).read()
    assert "O_RDONLY" in source
    assert not any(flag in source for flag in ("O_WRONLY", "O_RDWR", "O_APPEND", "O_CREAT", "os.write"))


def test_with_privileges_only_removable_drives_are_served(monkeypatch, tmp_path):
    path = tmp_path / "secret.txt"
    path.write_text("x")
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    with pytest.raises(PermissionError):
        helper.open_source(str(path))
