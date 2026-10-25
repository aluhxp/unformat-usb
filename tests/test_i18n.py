"""Every text on the screens has its translation, in every language."""

import glob
import os
import re
import xml.etree.ElementTree as ET

import pytest

GUI = os.path.join(os.path.dirname(__file__), "..", "src", "usbrescue", "gui")


@pytest.mark.parametrize("lang", ["es", "pt"])
def test_every_screen_text_is_translated(lang):
    texts = set()
    for path in glob.glob(os.path.join(GUI, "qml", "*.qml")):
        for m in re.finditer(r'qsTr\("((?:[^"\\]|\\.)*)"\)', open(path, encoding="utf-8").read()):
            texts.add(m.group(1).replace('\\"', '"'))
    done = {}
    for msg in ET.parse(os.path.join(GUI, "i18n", f"{lang}.ts")).getroot().iter("message"):
        tr = msg.find("translation")
        if tr is not None and (tr.text or "").strip() and tr.get("type") is None:
            done[msg.findtext("source")] = tr.text
    missing = sorted(texts - done.keys())
    assert not missing, f"run tools/i18n.py and translate: {missing}"
    # what %1, %2... a text carries, its translation carries too
    for src, tr in done.items():
        assert sorted(re.findall(r"%\d", src)) == sorted(re.findall(r"%\d", tr)), src

