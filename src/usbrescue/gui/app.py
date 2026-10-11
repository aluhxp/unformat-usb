"""Starts the window."""

import os
import sys

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from ..brand import APP_NAME
from .backend import Backend

QML_DIR = os.path.join(os.path.dirname(__file__), "qml")


os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")


def build(app):
    """Returns (engine, backend) with the main window loaded."""
    backend = Backend(app)
    engine = QQmlApplicationEngine(app)
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("appName", APP_NAME)
    engine.load(os.path.join(QML_DIR, "Main.qml"))
    return engine, backend


def run():
    app = QGuiApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    engine, backend = build(app)
    if not engine.rootObjects():
        sys.exit(1)
    backend.refreshDevices()
    code = app.exec()
    backend.cleanup()
    sys.exit(code)


if __name__ == "__main__":
    run()
