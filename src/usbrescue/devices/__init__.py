"""Finding the drives a person may want to rescue. Never the system disk."""

import sys
from dataclasses import dataclass


@dataclass
class Device:
    path: str           # what to open: /dev/sdb, or an image file
    name: str           # model, as the person knows it
    size: int
    transport: str      # "usb", "mmc", ...
    fs: str             # file system it has now, if any
    readable: bool      # can this process open it without more permissions?


def list_removable():
    if sys.platform.startswith("linux"):
        from . import linux
        return linux.list_removable()
    if sys.platform == "win32":
        from . import windows
        return windows.list_removable()
    if sys.platform == "darwin":
        from . import macos
        return macos.list_removable()
    return []
