"""Draws the program's icon (the happy little pen drive of the window) into
packaging/icon.png, icon.ico (Windows) and icon.icns (macOS).

    python tools/make_icon.py
"""

import os
import sys

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "packaging")


def draw(size):
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    u = size / 36.0          # the mascot is 30 x 36 units; centred in a square
    ox = 3 * u

    def box(x, y, w, h, r, color):
        p.setBrush(QColor(color))
        p.drawRoundedRect(QRectF(ox + x * u, y * u, w * u, h * u), r * u, r * u)

    box(9, 1, 12, 10, 2, "#B9C9C2")            # the plug
    box(2, 9, 26, 26, 8, "#FFC857")            # the body
    box(9.5, 20.5, 3.2, 1.6, 0.8, "#17302B")   # happy eyes
    box(17.5, 20.5, 3.2, 1.6, 0.8, "#17302B")
    # smile: flat on top, round below
    smile = QPainterPath()
    smile.moveTo(ox + 10 * u, 25 * u)
    smile.lineTo(ox + 20 * u, 25 * u)
    smile.arcTo(QRectF(ox + 10 * u, 20.5 * u, 10 * u, 9.5 * u), 0, -180)
    smile.closeSubpath()
    p.setBrush(QColor("#17302B"))
    p.drawPath(smile)
    p.end()
    return image


def main():
    QGuiApplication(sys.argv[:1] + ["-platform", "offscreen"])
    draw(512).save(os.path.join(OUT, "icon.png"))
    if not draw(512).save(os.path.join(OUT, "icon.icns")):
        raise SystemExit("Qt could not write .icns")
    # one .ico holding the usual sizes
    big = draw(256)
    if not big.save(os.path.join(OUT, "icon.ico")):
        raise SystemExit("Qt could not write .ico")


if __name__ == "__main__":
    main()
