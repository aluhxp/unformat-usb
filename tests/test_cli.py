"""The command line, in English and in Spanish."""

import os

from test_exfat import build
from usbrescue.cli import main as cli


def formatted(tmp_path):
    path = tmp_path / "pendrive.img"
    img = build(path)
    img.windows_quick_format()
    img.close()
    return str(path)


def system_language(monkeypatch, value):
    for var in ("LC_ALL", "LC_MESSAGES", "LANGUAGE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LANG", value)


def test_rescue_in_english(tmp_path, capsys, monkeypatch):
    system_language(monkeypatch, "en_US.UTF-8")
    out = tmp_path / "out"
    assert cli.main([formatted(tmp_path), str(out)]) == 0
    said = capsys.readouterr().out
    assert "read-only" in said and "Done:" in said
    assert "Unnamed folder 6" in os.listdir(out)
    assert (out / "_recovery_report.csv").read_text(encoding="utf-8").startswith("path,")


def test_rescue_in_spanish_from_the_system_language(tmp_path, capsys, monkeypatch):
    system_language(monkeypatch, "es_PE.UTF-8")
    out = tmp_path / "out"
    assert cli.main([formatted(tmp_path), str(out), "--only-photos"]) == 0
    assert "Listo:" in capsys.readouterr().out
    assert (out / "_informe_recuperacion.csv").read_text(encoding="utf-8").startswith("ruta,")


def test_old_spanish_options_still_work(tmp_path, capsys):
    assert cli.main([formatted(tmp_path), str(tmp_path / "out"), "--diagnostico", "--lang", "en"]) == 0
    assert "Current format" in capsys.readouterr().out
    assert cli.main([formatted(tmp_path), str(tmp_path / "out"), "--solo-listar", "--lang", "es"]) == 0
    assert "Carpetas:" in capsys.readouterr().out


def test_every_message_has_its_spanish():
    """A {} in a message is filled in the same way in Spanish."""
    for en, es in cli.ES.items():
        assert en.count("{") == es.count("{"), en
    for verdict in cli.VERDICTS.values():
        assert verdict in cli.ES, verdict


def test_undo_names_without_changes(tmp_path, capsys):
    assert cli.main(["--undo-names", str(tmp_path), "--lang", "en"]) == 0
    assert "no name changes" in capsys.readouterr().out
