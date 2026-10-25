# Unformat USB

**Get back the folders and files of a USB drive you formatted by mistake. Free, no limits, and it never writes to the drive.**

[Leer en español](README.es.md)

## Formatted your USB drive by mistake?

Stop and don't copy anything new onto it. A quick format (the default on Windows, macOS and Linux) wipes the index but almost always leaves the files in place. Unformat USB reads what is left and copies it to your computer:

- **Rebuilds the folders** with their names and contents, including large files stored in pieces.
- **Shows what it finds while it searches**, and you can rescue a folder without waiting for the end.
- **Safe mode**: copies the whole drive to your computer first and works on the copy. Recommended if the drive is failing.
- **Loose files**: the ones that were outside any folder come back too, named after their content (a document's title, a photo's date), without duplicates.
- **Lost names**: suggests a name for folders that lost theirs and renames only what you approve. It can be undone.
- **Only photos and videos**, each in its folder, if that is all you need.
- **Never writes to the drive**, and refuses to save rescued files onto it.

Works with USB drives and cards formatted as **exFAT** and **FAT32**.

## Download

- **Windows**: [UnformatUSB.exe](https://github.com/aluhxp/unformat-usb/releases/latest). Windows asks for administrator rights when it opens: a whole drive cannot be read without them.
- **Linux**: `pip install "unformat-usb[gui] @ git+https://github.com/aluhxp/unformat-usb"`, then run `unformat-usb`. It asks for your password to read the drive.
- **macOS**: [UnformatUSB-macOS.zip](https://github.com/aluhxp/unformat-usb/releases/latest). The app is not signed yet: the first time, right-click it and choose **Open**. It asks for your password to read the drive.

## When it cannot help

To be clear: after a **full format** (which writes zeros everywhere), heavy use after the format, or on an **SSD/NVMe** (the system erases free blocks with TRIM), there may be nothing left. Unformat USB tells you so instead of promising what it cannot do.

## Supporting the project

Unformat USB is free and will stay free. If it helped, the screen at the end of a rescue offers a way to buy us a coffee. It is optional.

---

## For developers

```
python -m venv .venv && .venv/bin/pip install -e ".[dev,gui]"
.venv/bin/python -m pytest -q          # tests (Linux formats test images with mkfs.exfat / mkfs.vfat)
.venv/bin/unformat-usb                  # the window
.venv/bin/unformat-usb-cli --help       # the command line (still in Spanish only)
```

- `src/usbrescue/core/`: the engine, plain Python with no dependencies. Every step is a generator of events.
- `src/usbrescue/gui/`: the window, PySide6 + Qt Quick.
- `tests/factory/`: builds formatted test images without mounting anything. On Windows and macOS the formatter's output is replayed from `tests/factory/recorded/`.

License: [GPL-3.0-or-later](LICENSE).
