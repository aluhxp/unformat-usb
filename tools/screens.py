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
from PySide6.QtCore import QBuffer, QIODevice         # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter   # noqa: E402
from PySide6.QtQuick import QQuickWindow              # noqa: E402,F401  (types the root window)

from factory import exfat_image as X                  # noqa: E402
from helpers import standard_tree                     # noqa: E402
from usbrescue.gui.app import build as build_window   # noqa: E402


def sample_picture():
    image = QImage(480, 320, QImage.Format_RGB32)
    image.fill(QColor("#9FD8C5"))
    p = QPainter(image)
    p.setBrush(QColor("#FFC857"))
    p.drawEllipse(150, 70, 180, 180)
    p.end()
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    image.save(buf, "PNG")
    return bytes(buf.data())


def main():
    from usbrescue import brand
    brand.PAYPAL_ME = brand.PAYPAL_ME or "example"     # so the donation card shows
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    work = tempfile.mkdtemp(prefix="usbrescue-screens-")
    image = os.path.join(work, "Pendrive de prueba.img")
    app = QGuiApplication(sys.argv)
    X.mkfs(image)
    img = X.ExfatImage(image)
    for name, data in standard_tree().items():
        img.add(name, data)
    img.add("Fotos/Cumpleaños 2023/tarta.png", sample_picture())
    img.add("Fotos/Cumpleaños 2023/lista de invitados.txt", "Ana\nLuis\nMarta\nPedro\n".encode())
    img.add("Fotos/Cumpleaños 2023/video.mp4", b"\x00\x00\x00\x1cftypisom" + os.urandom(90000))
    img.add("notas.txt", b"una nota suelta\n" * 10)
    img.flush()
    img.windows_quick_format()
    img.close()

    engine, backend = build_window(app)
    backend._default_dest = os.path.join(work, "Recuperado")
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

    healthy = os.path.join(work, "Pendrive sano.img")
    X.mkfs(healthy)
    ok = X.ExfatImage(healthy)
    for name, data in standard_tree().items():
        ok.add(name, data)
    ok.flush()
    ok.close()
    backend.addImage(QUrl.fromLocalFile(healthy))
    backend.choose(0)
    settle("diagnosed")
    shot("2b-healthy")
    backend.back()

    backend.addImage(QUrl.fromLocalFile(image))
    shot("1-pick")
    backend.choose(0)
    settle("diagnosed")
    # an image file stands in for a real drive, so the safe/direct choice shows
    backend._set(isDevice=True, driveSize=61872793600, safeFits=True, safeRoomy=True, mode="safe")
    shot("2-diagnosis")
    raw = backend._session.disk._raw
    backend._session.disk._raw = lambda off, n: (time.sleep(0.03), raw(off, n))[1]
    backend._s["driveSize"] = os.path.getsize(image)
    backend.start()
    while backend.state["imgProgress"] < 0.4:
        app.processEvents()
        time.sleep(0.01)
    shot("2c-imaging")
    settle("scanned")
    backend.toggleExpanded(0)
    row = next(i for i, n in enumerate(backend.tree.rows) if n.name == "Cumpleaños 2023")
    backend.selectFolder(row)
    backend.selectFile(next(i for i, f in enumerate(backend.state["files"]) if f["name"] == "tarta.png"))
    settle(seconds=1.0)
    shot("3-tree")
    backend.recover(os.path.join(work, "out"))
    settle("done")
    shot("5-done")
    backend.suggestNames()
    end = time.time() + 30
    while (backend.state["phase"] != "naming" or backend.state["namesBusy"]) and time.time() < end:
        app.processEvents()
        time.sleep(0.01)
    shot("6-names")
    backend.deleteCopy()
    print("phase:", backend.state["phase"], {k: backend.state[k] for k in ("sumOk", "sumWarned", "sumOrphans", "sumUnnamed")})
    backend.cleanup()


if __name__ == "__main__":
    main()
