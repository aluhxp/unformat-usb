"""Names and dates read from inside files, and copies left out."""

import datetime
import os

import samples
from factory import exfat_image as X
from helpers import files_under, run, standard_tree
from usbrescue.core import metadata, model as ev


def write(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def test_a_document_is_named_by_its_title(tmp_path):
    path = write(tmp_path, "a.docx", samples.docx("Texto cualquiera", title="Acta de entrega"))
    assert metadata.describe(path, "docx", "Acta de entrega")[0] == "Acta de entrega"


def test_a_document_without_title_is_named_by_how_it_begins(tmp_path):
    path = write(tmp_path, "a.docx", samples.docx("Guayaquil, 5 de enero 2024 ACTA DE ENTREGA DE PUESTO y sigue un buen rato más"))
    label, _ = metadata.describe(path, "docx")
    assert label.startswith("Guayaquil, 5 de enero 2024 ACTA DE ENTREGA") and len(label) <= 60


def test_a_pdf_gives_its_title_and_date(tmp_path):
    path = write(tmp_path, "a.pdf", samples.pdf("Informe anual 2023"))
    assert metadata.describe(path, "pdf") == ("Informe anual 2023", datetime.datetime(2023, 5, 12, 18, 12, 3))


def test_a_title_that_is_only_the_program_and_file_name_is_cleaned(tmp_path):
    path = write(tmp_path, "a.pdf", samples.pdf("Microsoft Word - renuncia.docx"))
    assert metadata.describe(path, "pdf")[0] == "renuncia"


def test_a_photo_is_named_by_the_moment_it_was_taken(tmp_path):
    path = write(tmp_path, "a.jpg", samples.jpeg("2019:07:30 18:04:48"))
    assert metadata.describe(path, "jpg") == ("photo 2019-07-30 18.04.48", datetime.datetime(2019, 7, 30, 18, 4, 48))


def test_a_song_is_named_by_artist_and_title(tmp_path):
    path = write(tmp_path, "a.mp3", samples.mp3("Los Panchos", "Sabor a mí"))
    assert metadata.describe(path, "mp3")[0] == "Los Panchos - Sabor a mí"


def test_a_note_is_named_by_its_first_line(tmp_path):
    path = write(tmp_path, "a.txt", b"\n\nlista de la compra\nhuevos\nleche\n")
    assert metadata.describe(path, "txt")[0] == "lista de la compra"


def test_a_title_holding_the_program_name_is_cleaned_in_documents_too(tmp_path):
    path = write(tmp_path, "a.docx", samples.docx("texto", title="Microsoft Word - renuncia"))
    assert metadata.describe(path, "docx", "Microsoft Word - renuncia")[0] == "renuncia"


def test_a_note_that_is_a_web_address_is_named_by_the_site(tmp_path):
    path = write(tmp_path, "a.txt", b"https://www.example.org/blog/upgrade-11-to-14/\n")
    assert metadata.describe(path, "txt")[0] == "link example.org"


def test_database_rows_and_encoded_data_are_not_used_as_names(tmp_path):
    rows = b"401\t.\t2024-07-29 23:00:01.588327\t\\N\t7\tDesembolsos\n"
    assert metadata.describe(write(tmp_path, "a.txt", rows), "txt")[0] is None
    sql = b"n_contrato bigint NOT NULL, insertby character varying(50) DEFAULT \"current_user\"(),\n"
    assert metadata.describe(write(tmp_path, "b.txt", sql), "txt")[0] is None
    blob = b"Zhwf3+QZcYZECc4Qaed5na91tkJaOe9ynXUPjRbIteRWJ4pI7SQNEDiJPwmJGaRmCiPteZ7S\n"
    assert metadata.describe(write(tmp_path, "c.txt", blob), "txt")[0] is None
    numbers = b"80 895.000000 30.00 5 3 5 5 0.00 14.00 5 2 2 0.500000 10 50\n"
    assert metadata.describe(write(tmp_path, "d.txt", numbers), "txt")[0] is None


def test_noise_is_not_used_as_a_name(tmp_path):
    path = write(tmp_path, "a.txt", b"',0,0),(41863,'--> <-- || :: ;;\n")
    assert metadata.describe(path, "txt")[0] is None
    assert metadata.describe(write(tmp_path, "b.jpg", b"\xff\xd8\xff\xd9"), "jpg") == (None, None)


# ----------------------------------------------------------- on a real rescue

REPORT = samples.pdf("Informe anual 2023", body=b"x" * 5000)
PHOTO = samples.jpeg("2019:07:30 18:04:48")
LETTER = samples.docx("Carta de renuncia presentada el lunes")
NOTE = b"comandos utiles del servidor\npm2 save\n"


def formatted(tmp_path, root_files, extra=None):
    path = tmp_path / "pendrive.img"
    X.mkfs(path)
    img = X.ExfatImage(path)
    for name, data in {**standard_tree(), **(extra or {})}.items():
        img.add(name, data)
    for name, data in root_files.items():
        img.add(name, data)
    img.flush()
    img.windows_quick_format()
    img.close()
    return path


def loose(out):
    return {p.split("/", 1)[1]: d for p, d in files_under(out).items() if p.startswith("_ROOT_AND_ORPHANS/")}


def test_files_without_a_folder_come_back_with_names_from_their_content(tmp_path):
    path = formatted(tmp_path, {"a.pdf": REPORT, "b.jpg": PHOTO, "c.docx": LETTER, "d.txt": NOTE})
    run(path, tmp_path / "out")
    got = loose(tmp_path / "out")
    by_label = {name.split(" - ", 1)[1]: data for name, data in got.items() if " - " in name}
    assert by_label["Informe anual 2023.pdf"] == REPORT
    assert by_label["Carta de renuncia presentada el lunes.docx"] == LETTER
    assert by_label["comandos utiles del servidor.txt"] == NOTE
    assert "photo 2019-07-30 18.04.48.jpg" in by_label


def test_a_photo_gets_back_the_date_it_was_taken(tmp_path):
    path = formatted(tmp_path, {"b.jpg": PHOTO})
    run(path, tmp_path / "out")
    photo = next(p for p in os.listdir(tmp_path / "out" / "_ROOT_AND_ORPHANS") if p.endswith(".jpg"))
    taken = os.path.getmtime(tmp_path / "out" / "_ROOT_AND_ORPHANS" / photo)
    assert datetime.datetime.fromtimestamp(taken) == datetime.datetime(2019, 7, 30, 18, 4, 48)


def test_a_loose_copy_of_a_file_that_is_in_a_folder_is_not_rescued_twice(tmp_path):
    path = formatted(tmp_path, {"copia.pdf": REPORT}, extra={"Trabajo/informe.pdf": REPORT})
    _, _, recovered = run(path, tmp_path / "out")
    assert REPORT not in loose(tmp_path / "out").values()
    assert list(files_under(tmp_path / "out").values()).count(REPORT) == 1
    assert recovered[-1].orphans_duplicate == 1


def test_two_identical_loose_files_are_kept_once(tmp_path):
    path = formatted(tmp_path, {"uno.pdf": REPORT, "dos.pdf": REPORT, "otro.pdf": samples.pdf("Otro", body=b"y" * 5000)})
    _, _, recovered = run(path, tmp_path / "out")
    pdfs = [d for name, d in loose(tmp_path / "out").items() if name.endswith(".pdf")]
    assert len(pdfs) == 2 and pdfs.count(REPORT) == 1
    assert isinstance(recovered[-1], ev.RecoverFinished) and recovered[-1].orphans_duplicate == 1


def test_files_of_the_same_size_but_different_content_are_both_kept(tmp_path):
    a, b = samples.pdf("Uno", body=b"a" * 5000), samples.pdf("Dos", body=b"b" * 5000)
    assert len(a) == len(b)
    path = formatted(tmp_path, {"a.pdf": a, "b.pdf": b})
    run(path, tmp_path / "out")
    assert sorted(d for d in loose(tmp_path / "out").values() if d[:4] == b"%PDF") == sorted([a, b])
