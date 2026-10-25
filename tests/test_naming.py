"""Names for folders that lost theirs: from paths inside files, or from content."""

import datetime
import json
import os

from factory import exfat_image as X
from helpers import blob, make_zip, run
from usbrescue.core import model as ev
from usbrescue.core import naming
from usbrescue.core.naming import Item, paths_in, suggest

NAMES = ev.Names(unnamed_folder="Folder {}")


def item(path, data=b"", year=2023):
    return Item(tuple(path.split("/")), len(data) or 1000,
                datetime.datetime(year, 5, 1), lambda limit, d=data: d[:limit])


def workbook(abs_path):
    """An .xlsx as Excel saves it: it remembers the folder it was saved in."""
    return make_zip({
        "[Content_Types].xml": "<Types/>",
        "xl/workbook.xml": f'<workbook><mc:AlternateContent><x15ac:absPath url="{abs_path}" '
                           'xmlns:x15ac="http://schemas.microsoft.com/office/spreadsheetml/2010/11/ac"/>'
                           '</mc:AlternateContent></workbook>',
    })


def shortcut(target):
    """Enough of a Windows shortcut (.lnk): the target path, plain and in UTF-16."""
    return b"L\x00\x00\x00" + b"\x01" * 60 + target.encode("cp1252") + b"\x00" * 8 + \
        target.encode("utf-16-le") + b"\x00\x00"


# ------------------------------------------------------------ finding paths

def test_paths_are_found_in_office_files_shortcuts_and_notes():
    assert ["Trabajo", "Informes"] in paths_in(workbook("E:\\Trabajo\\Informes\\"), "xlsx")
    found = paths_in(shortcut("E:\\Música\\Rock\\canción.mp3"), "lnk")
    assert ["Música", "Rock", "canción.mp3"] in found
    note = "el respaldo está en file:///media/ana/USB/Tesis%20final/cap1.docx y nada más".encode()
    assert ["media", "ana", "USB", "Tesis final", "cap1.docx"] in paths_in(note, "txt")
    note = b"copiado de D:\\Clientes\\Perez\\contrato firmado.pdf, ver"
    assert ["Clientes", "Perez", "contrato firmado.pdf"] in paths_in(note, "txt")


def test_code_that_looks_like_a_path_is_not_one():
    view = b'<xpath expr="//form/notebook/page[@name=\'x\']" position="after"/> /api/{id}/items'
    assert paths_in(view, "xml") == []


def test_a_playlist_with_relative_paths_counts():
    playlist = b"#EXTM3U\r\n..\\Viaje 2019\\Rock\\cancion uno.mp3\r\n"
    assert ["Viaje 2019", "Rock", "cancion uno.mp3"] in paths_in(playlist, "m3u")


# ------------------------------------------------------------ original names

def test_the_original_name_comes_from_a_path_that_matches_what_the_folder_holds():
    items = [
        item("Folder 7/Informes/ventas.xlsx", workbook("E:\\Trabajo\\Informes\\")),
        item("Folder 7/Informes/gastos.xlsx"),
        item("Folder 9/playa.jpg"),
    ]
    out = {s.folder: s for s in suggest(items, [("Folder 7",), ("Folder 9",)])}
    s = out[("Folder 7",)]
    assert (s.source, s.name) == ("original", "Trabajo")
    assert "Informes" in s.example
    assert out[("Folder 9",)].source == "content"


def test_a_clue_can_live_in_another_folder():
    items = [
        item("Folder 3/Rock/cancion uno.mp3"),
        item("Folder 3/Rock/cancion dos.mp3"),
        item("Listas/favoritas.m3u", b"#EXTM3U\n..\\Musica\\Rock\\cancion uno.mp3\n"
                                      b"..\\Musica\\Rock\\cancion dos.mp3\n"),
    ]
    [s] = suggest(items, [("Folder 3",)])
    assert (s.source, s.name, s.evidence) == ("original", "Musica", 4)


def test_one_common_name_in_common_is_not_enough():
    # 'notas.txt' could be anywhere: it says nothing about the folder
    items = [item("Folder 2/notas.txt"), item("Folder 2/b.jpg"),
             item("otra/x.txt", b"ver C:\\Varios\\notas.txt")]
    [s] = suggest(items, [("Folder 2",)])
    assert s.source == "content"


def test_a_distinctive_file_name_twice_is_enough():
    items = [item("Folder 4/presupuesto final 2024.xlsx"),
             item("a.txt", b"en E:\\Obra\\presupuesto final 2024.xlsx"),
             item("b.txt", b"tambien D:\\Obra\\presupuesto final 2024.xlsx")]
    [s] = suggest(items, [("Folder 4",)])
    assert (s.source, s.name) == ("original", "Obra")


def test_a_name_already_used_beside_it_is_not_proposed():
    items = [item("Trabajo/x.docx"),
             item("Folder 1/Informes/ventas.xlsx", workbook("E:\\Trabajo\\Informes\\"))]
    [s] = suggest(items, [("Folder 1",)])
    assert s.source == "content"


def test_two_folders_never_get_the_same_name():
    items = [item("Folder 1/Informes/a.xlsx", workbook("E:\\Trabajo\\Informes\\")),
             item("Folder 1/Informes/b.xlsx", workbook("E:\\Trabajo\\Informes\\")),
             item("Folder 2/Informes/c.xlsx", workbook("E:\\Trabajo\\Informes\\")),
             item("Folder 5/a.jpg"), item("Folder 6/b.jpg")]
    out = suggest(items, [("Folder 1",), ("Folder 2",), ("Folder 5",), ("Folder 6",)])
    names = [s.name.lower() for s in out]
    assert len(set(names)) == len(names)
    assert out[0].name == "Trabajo"
    assert {out[2].name, out[3].name} == {"Photos 2023", "Photos 2023 (2)"}


# ----------------------------------------------------------- from content

def test_content_names_say_what_most_files_are_and_when():
    items = [item(f"Folder 1/IMG_{i}.jpg", year=2021) for i in range(9)] + \
            [item("Folder 1/clip.mp4", year=2021), item("Folder 1/Thumbs.db", year=2015)]
    items += [item(f"Folder 2/factura {i}.pdf", year=2019 + i % 3) for i in range(6)]
    items += [item("Folder 3/a.exe"), item("Folder 3/b.jpg"), item("Folder 3/c.mp3", year=2001)]
    out = {s.folder[0]: s for s in suggest(items, [("Folder 1",), ("Folder 2",), ("Folder 3",)])}
    assert out["Folder 1"].name == "Photos 2021"
    assert out["Folder 2"].name == "Documents factura 2019-2021"
    assert out["Folder 3"].name == "Various"


def test_the_window_can_word_it_in_its_own_language():
    words = {"photos": "Fotos"}
    items = [item("Folder 1/a.jpg"), item("Folder 1/b.jpg")]
    [s] = suggest(items, [("Folder 1",)],
                  label=lambda kind, years, theme: naming.compose(words[kind], years, theme))
    assert s.name == "Fotos 2023"


def test_folders_under_the_lost_parents_folder_get_names_too():
    items = [item("_LOST/Folder 8/a.jpg"), item("Folder 2/a.jpg"), item("Bien/x.txt")]
    assert naming.unnamed_folders(items, ev.Names(unnamed_folder="Folder {}", lost_parent="_LOST")) \
        == [("Folder 2",), ("_LOST", "Folder 8")]


# ---------------------------------------------------------------- renaming

def test_renaming_keeps_a_log_and_can_be_undone(tmp_path):
    for p in ("Folder 1/a.txt", "Folder 2/sub/b.txt", "Otra/c.txt"):
        os.makedirs(tmp_path / os.path.dirname(p), exist_ok=True)
        (tmp_path / p).write_text("x")
    report = tmp_path / "_report.csv"
    report.write_text("ruta,tamano\nFolder 1/a.txt,1\nFolder 2/sub/b.txt,1\nOtra/c.txt,1\n")
    log = str(tmp_path / "_names.json")

    done = naming.rename(str(tmp_path), [(("Folder 1",), "Trabajo"), (("Folder 2",), "Fotos")],
                         log, str(report))
    assert done == [("Folder 1", "Trabajo"), ("Folder 2", "Fotos")]
    assert (tmp_path / "Fotos/sub/b.txt").exists() and not (tmp_path / "Folder 2").exists()
    assert "Trabajo/a.txt" in report.read_text() and "Folder 1" not in report.read_text()
    assert [s["to"] for s in json.load(open(log))] == ["Trabajo", "Fotos"]

    assert naming.undo(str(tmp_path), log, str(report)) == 2
    assert (tmp_path / "Folder 1/a.txt").exists() and (tmp_path / "Folder 2/sub/b.txt").exists()
    assert "Folder 1/a.txt" in report.read_text()
    assert not os.path.exists(log)


def test_renaming_never_overwrites_a_folder(tmp_path):
    for p in ("Folder 1/a.txt", "Trabajo/b.txt"):
        os.makedirs(tmp_path / os.path.dirname(p), exist_ok=True)
        (tmp_path / p).write_text("x")
    try:
        naming.rename(str(tmp_path), [(("Folder 1",), "Trabajo")], str(tmp_path / "log.json"))
        raise AssertionError("it should have refused")
    except naming.RenameError:
        pass
    assert (tmp_path / "Folder 1/a.txt").exists() and (tmp_path / "Trabajo/b.txt").exists()


# -------------------------------------------------------- the whole journey

def test_after_a_format_the_lost_name_is_found_and_put_back(tmp_path):
    path = tmp_path / "pendrive.img"
    X.mkfs(path)
    img = X.ExfatImage(path)
    img.add("Trabajo/Informes/ventas 2024.xlsx", workbook("E:\\Trabajo\\Informes\\"))
    img.add("Trabajo/Informes/gastos 2024.xlsx", workbook("E:\\Trabajo\\Informes\\"))
    img.add("Trabajo/Informes/resumen.txt", b"resumen\n" * 50)
    for i in range(5):
        img.add(f"Vacaciones/Playa/IMG_{i:04d}.jpg", blob(i, 6000))
    img.flush()
    img.windows_quick_format()
    img.close()

    dest = tmp_path / "out"
    names = ev.Names(unnamed_folder="Folder {}")
    result, _, _ = run(path, dest, names=names, find_orphans=False)
    items = naming.items_from_folder(str(dest), skip={"_names.json"})
    folders = naming.unnamed_folders(items, names)
    assert len(folders) == 2
    out = suggest(items, folders)
    by_source = {s.source: s for s in out}
    assert by_source["original"].name == "Trabajo"
    assert by_source["content"].name.startswith("Photos")

    naming.rename(str(dest), [(s.folder, s.name) for s in out], str(dest / "_names.json"))
    assert (dest / "Trabajo/Informes/resumen.txt").exists()
    assert any(p.startswith("Photos") for p in os.listdir(dest))


def test_text_with_nothing_to_name_it_goes_aside(tmp_path):
    from usbrescue.core.orphans import Orphan, save_orphan
    from usbrescue.core.model import Geometry

    class Disk:
        def __init__(self, data):
            self.data = data

        def read(self, off, n):
            return self.data[off:off + n]

    cs = 4096
    pieces = b"\x00" * (2 * cs)
    pieces += (b"'1234','5678','abc','def'),(" * 200)[:cs]          # a piece of a dump
    pieces += b"Lista de compras\npan\nleche\n".ljust(cs, b"\x00")  # a note
    g = Geometry(cs, 0)
    names = ev.Names(text_pieces="pieces")
    a = save_orphan(Disk(pieces), g, Orphan(4, "txt", [(4, 1)], False), str(tmp_path), names)
    b = save_orphan(Disk(pieces), g, Orphan(5, "txt", [(5, 1)], False), str(tmp_path), names)
    assert os.path.dirname(a[0]) == str(tmp_path / "pieces")
    assert os.path.dirname(b[0]) == str(tmp_path) and "Lista de compras" in b[0]
