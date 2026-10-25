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


def self_test(app, source, dest, report):
    """Drives the real window through a whole rescue, with no one clicking:
    lets a build be checked on a machine nobody sits at (see build.yml).
    Writes what happened to report (JSON); the exit code says if it worked."""
    import json
    import time

    from PySide6.QtCore import QTimer

    from ..devices import Device, list_removable

    problems = []
    from PySide6.QtCore import qInstallMessageHandler
    qInstallMessageHandler(lambda kind, ctx, text: problems.append(text))
    engine, backend = build(app)
    outcome = {"window": bool(engine.rootObjects())}
    try:
        outcome["drives_listed"] = [d.__dict__ for d in list_removable()]
    except Exception as e:      # noqa: BLE001 - the report must say it, not crash
        outcome["drives_listed"] = f"error: {e!r}"
    size = os.path.getsize(source) if os.path.isfile(source) else 0
    backend._devices = [Device(source, os.path.basename(source), size, "image", "", True)]
    started = time.time()
    steps = iter(["diagnose", "scan", "recover"])
    state = {"next": next(steps)}

    def tick():
        phase = backend.state["phase"]
        if phase in ("error", "nothing") or time.time() - started > 600:
            finish()
        elif state["next"] == "diagnose":
            backend.choose(0)
            state["next"] = next(steps)
        elif state["next"] == "scan" and phase == "diagnosed":
            backend.scan()
            state["next"] = next(steps)
        elif state["next"] == "recover" and phase == "scanned":
            backend.recover(dest)
            state["next"] = None
        elif state["next"] is None and phase == "done":
            finish()

    def finish():
        timer.stop()
        s = backend.state
        outcome.update(phase=s["phase"], error=s["error"], rescued=s["sumOk"] + s["sumWarned"],
                       orphans=s["sumOrphans"], seconds=round(time.time() - started, 1),
                       qml_problems=[p for p in problems if ".qml" in p or "QML" in p])
        with open(report, "w", encoding="utf-8") as fh:
            json.dump(outcome, fh, indent=1, default=str)
        backend.cleanup()
        ok = outcome["window"] and s["phase"] == "done" and outcome["rescued"] > 0 \
            and not outcome["qml_problems"]
        app.exit(0 if ok else 1)

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(200)
    return app.exec()


def run():
    if "--self-test" in sys.argv:
        i = sys.argv.index("--self-test")
        source, dest, report = sys.argv[i + 1:i + 4]
        app = QGuiApplication(sys.argv[:1])
        sys.exit(self_test(app, source, dest, report))
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
