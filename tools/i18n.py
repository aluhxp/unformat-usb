"""Keeps the window's translations up to date.

The screens are written in English (qsTr("...")). Each other language has
a Qt Linguist file, src/usbrescue/gui/i18n/<lang>.ts, translated by hand
(pyside6-linguist opens it), and compiled into <lang>.qm, which the
program loads.

    python tools/i18n.py            pick up new texts, then compile
    python tools/i18n.py --check    fail if a text has no translation
"""

import glob
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QML = os.path.join(ROOT, "src", "usbrescue", "gui", "qml")
I18N = os.path.join(ROOT, "src", "usbrescue", "gui", "i18n")
LANGS = ["es"]


def tool(name):
    here = os.path.dirname(sys.executable)
    for candidate in (os.path.join(here, f"pyside6-{name}"), shutil.which(f"pyside6-{name}")):
        if candidate and os.path.exists(candidate):
            return candidate
    raise SystemExit(f"pyside6-{name} not found: install PySide6")


def untranslated(ts):
    missing = []
    for ctx in ET.parse(ts).getroot().iter("context"):
        for msg in ctx.iter("message"):
            tr = msg.find("translation")
            if tr is None or not (tr.text or "").strip() or tr.get("type") in ("unfinished", "obsolete"):
                if tr is None or tr.get("type") != "obsolete":
                    missing.append(msg.findtext("source"))
    return missing


def main():
    files = sorted(glob.glob(os.path.join(QML, "*.qml")))
    status = 0
    for lang in LANGS:
        ts = os.path.join(I18N, f"{lang}.ts")
        if "--check" not in sys.argv:
            subprocess.run([tool("lupdate"), *files, "-no-obsolete", "-source-language", "en",
                            "-target-language", lang, "-ts", ts], check=True, capture_output=True)
            subprocess.run([tool("lrelease"), ts, "-qm", ts[:-3] + ".qm"], check=True,
                           capture_output=True)
        missing = untranslated(ts)
        for text in missing:
            print(f"{lang}: no translation for {text!r}")
        status |= bool(missing)
    return status


if __name__ == "__main__":
    sys.exit(main())
