"""For the build check only: a formatted test drive, as an image file, and
optionally written onto a virtual disk the CI machine made for this.

    python tools/ci_make_test_drive.py drive.img [\\\\.\\PhysicalDriveN]

Writing to a disk is refused unless CI is set and Windows says the disk is
a virtual one (a .vhd attached by the workflow)."""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "tests"), os.path.join(HERE, "..", "src")]

from test_exfat import build   # noqa: E402


def virtual(number):
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          f"(Get-Disk -Number {number}).FriendlyName"],
                         capture_output=True, text=True).stdout
    return "virtual" in out.lower()


def main(image, drive=None):
    img = build(image)
    img.windows_quick_format()
    img.close()
    if not drive:
        return 0
    number = int(drive.lower().rsplit("physicaldrive", 1)[1])
    if not os.environ.get("CI") or not virtual(number):
        sys.exit(f"refusing to write to {drive}: not a CI virtual disk")
    with open(image, "rb") as src:
        fd = os.open(drive, os.O_RDWR | getattr(os, "O_BINARY", 0))
        try:
            while True:
                block = src.read(1 << 20)
                if not block:
                    break
                os.write(fd, block.ljust(-(-len(block) // 4096) * 4096, b"\0"))
        finally:
            os.close(fd)
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
