"""Development aid: drives the real window through a recovery of a synthetic
drive, without a display, and saves a picture of each screen.

    QT_QPA_PLATFORM=offscreen python tools/screens.py OUT_DIR [--dark]
"""

import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "src"), os.path.join(HERE, "..", "tests")]

from PySide6.QtCore import QUrl                       # noqa: E402
from PySide6.QtGui import QGuiApplication             # noqa: E402
from PySide6.QtQuick import QQuickWindow              # noqa: E402,F401  (types the root window)

from factory import exfat_image as X                  # noqa: E402
from test_exfat import build                          # noqa: E402
from usbrescue.gui.app import build as build_window   # noqa: E402


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    work = tempfile.mkdtemp(prefix="usbrescue-screens-")
    image = os.path.join(work, "Pendrive de prueba.img")
    img = build(image)
    img.windows_quick_format()
    img.close()

    app = QGuiApplication(sys.argv)
    engine, backend = build_window(app)
    window = engine.rootObjects()[0]
    window.setProperty("forceDark", "--dark" in sys.argv)

    def settle(until=None, seconds=0.4):
        end = time.time() + 30
        while time.time() < end:
            app.processEvents()
            time.sleep(0.01)
            if until is None:
                seconds -= 0.01
                if seconds <= 0:
                    return
            elif backend.state["phase"] == until:
                return settle()

    def shot(name):
        settle()
        window.grabWindow().save(os.path.join(out, name + ".png"))

    backend.addImage(QUrl.fromLocalFile(image))
    shot("1-pick")
    backend.choose(0)
    settle("diagnosed")
    shot("2-diagnosis")
    backend.scan()
    settle("scanned")
    backend.toggleExpanded(0)
    shot("3-tree")
    backend.recover(os.path.join(work, "out"))
    settle("done")
    shot("5-done")
    print("phase:", backend.state["phase"], {k: backend.state[k] for k in ("sumOk", "sumWarned", "sumOrphans", "sumUnnamed")})


if __name__ == "__main__":
    main()
