"""Starts the window."""

import os
import sys

from PySide6.QtCore import QSettings, QTranslator
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from ..brand import APP_NAME
from . import texts
from .backend import Backend

QML_DIR = os.path.join(os.path.dirname(__file__), "qml")
I18N_DIR = os.path.join(os.path.dirname(__file__), "i18n")


os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")


def build(app, language=texts.DEFAULT, remember=False):
    """Returns (engine, backend) with the main window loaded. English is the
    language the screens are written in; others come from i18n/<lang>.qm."""
    backend = Backend(app, language=language)
    engine = QQmlApplicationEngine(app)
    translator = QTranslator(app)

    def apply(lang):
        app.removeTranslator(translator)
        if lang != "en" and translator.load(os.path.join(I18N_DIR, f"{lang}.qm")):
            app.installTranslator(translator)
        engine.retranslate()
        if remember:
            QSettings().setValue("language", lang)

    backend._on_language = apply
    if language != "en":
        apply(language)
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("appName", APP_NAME)
    engine.load(os.path.join(QML_DIR, "Main.qml"))
    return engine, backend


def run():
    app = QGuiApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    saved = str(QSettings().value("language", texts.DEFAULT))
    engine, backend = build(app, language=saved, remember=True)
    if not engine.rootObjects():
        sys.exit(1)
    backend.refreshDevices()
    code = app.exec()
    backend.cleanup()
    sys.exit(code)


if __name__ == "__main__":
    run()
