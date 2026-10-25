"""Command line, in English or Spanish (--lang, or the system's language).

Messages are written in English; ES holds their Spanish. The words written
to disk (folder names, the report) come from usbrescue.texts, like the window's.
"""

import argparse
import csv
import os
import sys
import time

from .. import texts
from ..core import model as ev
from ..core import imaging
from ..core import naming
from ..core.diagnose import diagnose
from ..core.reader import Source
from ..core.session import Session, UnsafeDestination
from ..core.util import fmt_size

LANGS = ("en", "es")

ES = {
    # names
    "original name, it appears in the path {}": "nombre original, aparece en la ruta {}",
    "suggested from its content": "sugerido por su contenido",
    "  {:3}. {}  ->  {}   ({} files; {})": "  {:3}. {}  ->  {}   ({} archivos; {})",
    "There are no unnamed folders in {}": "No hay carpetas sin nombre en {}",
    "Proposed names for {} folder(s):": "Nombres propuestos para {} carpeta(s):",
    "\nWhich ones should I rename? (a = all, 1,3,5 = those, Enter = none): ":
        "\n¿Cuáles renombro? (t = todas, 1,3,5 = esas, Enter = ninguna): ",
    "Nothing was changed.": "No se cambió nada.",
    "Could not rename: {} already exists or is missing. What came before is done.":
        "No se pudo renombrar: ya existe o falta {}. Lo anterior quedó hecho.",
    "Renamed {}. To undo it: unformat-usb-cli --undo-names {}":
        "Renombradas {}. Para deshacerlo: unformat-usb-cli --undo-names {}",
    "Undid {} name change(s).": "Deshechos {} cambio(s) de nombre.",
    "There were no name changes to undo.": "No había cambios de nombre que deshacer.",
    # diagnosis
    "This drive looks fine: its files are in plain sight and there is no sign of a recent "
    "format. If you are looking for something deleted or from before a format, the full scan "
    "may find it.":
        "Este pendrive parece estar bien: sus archivos están a la vista y no hay señales de un "
        "formateo reciente. Si buscas algo borrado o anterior a un formateo, el escaneo completo "
        "puede encontrarlo.",
    "Good news: the old root folder is still there. The folders can be recovered with their names.":
        "Buenas noticias: la carpeta raíz antigua sigue ahí. Se pueden recuperar las carpetas "
        "con sus nombres.",
    "The old FAT survived: the folder tree and fragmented files can be rebuilt. The names of "
    "the top folders were lost.":
        "La tabla FAT antigua sobrevivió: se puede reconstruir el árbol de carpetas y los archivos "
        "fragmentados. Los nombres de las carpetas de primer nivel se perdieron.",
    "The format erased the root and the FAT. A full scan is needed to know what can be recovered.":
        "El formateo borró la raíz y la tabla FAT. Hace falta el escaneo completo para saber qué "
        "se puede recuperar.",
    "Everything sampled is blank. Either the drive held no data, or the format erased it (full "
    "format, or TRIM on an SSD). The full scan will confirm it.":
        "Todo lo que se miró está vacío. O el disco no tenía datos, o se borraron al formatear "
        "(formateo completo, o TRIM en un SSD). El escaneo completo lo confirma.",
    "Current format: {}": "Formato actual: {}",
    "not recognised": "no reconocido",
    "In sight now: {} folders and {} files in the root": "A la vista ahora: {} carpetas y {} archivos en la raíz",
    "Old FAT: {}": "Tabla FAT antigua: {}",
    "yes, {} links": "sí, {} enlaces",
    "no": "no",
    "Old root: yes, {} folders and {} files": "Raíz antigua: sí, {} carpetas y {} archivos",
    "Old root: no": "Raíz antigua: no",
    "Blank blocks in the sample: {:.0%}": "Bloques vacíos en la muestra: {:.0%}",
    # progress and image
    "{}: {:5.1f}%  {:6.1f} MB/s  ~{} min left   ": "{}: {:5.1f}%  {:6.1f} MB/s  faltan ~{} min   ",
    "Not enough space for the copy: it needs {} and {} is free.":
        "No hay espacio para la copia: hacen falta {} y hay {} libres.",
    "Copying {} ({}) to {}": "Copiando {} ({}) a {}",
    "Retrying": "Reintentando",
    "Copying": "Copiando",
    "Scanning": "Escaneando",
    "{}: {:5.1f}%  {:6.1f} MB/s  unreadable: {}   ": "{}: {:5.1f}%  {:6.1f} MB/s  ilegible: {}   ",
    "Copy finished. Unreadable: {}. You can unplug the source now.":
        "Copia terminada. Ilegible: {}. Ya puedes desconectar el origen.",
    # arguments
    "Recovers the folders and files of a formatted FAT32/exFAT/NTFS USB drive. It only reads the source.":
        "Recupera carpetas y archivos de un pendrive FAT32/exFAT/NTFS formateado. Solo lee el origen.",
    "drive image (.img) or device (/dev/sdX, \\\\.\\PhysicalDriveN)":
        "imagen del pendrive (.img) o dispositivo (/dev/sdX, \\\\.\\PhysicalDriveN)",
    "folder to save what is recovered (on ANOTHER disk)": "carpeta donde guardar lo recuperado (en OTRO disco)",
    "force the file system type": "forzar el tipo de sistema de archivos",
    "include files that were already deleted before the format":
        "incluir archivos que ya estaban borrados antes del formateo",
    "show what was found without copying": "mostrar lo encontrado sin copiar",
    "on a drive that was not formatted: bring back only the deleted files":
        "en un pendrive que no se formateó: recuperar solo los archivos borrados",
    "don't look for files without a folder (the loose ones in the root)":
        "no buscar archivos sin carpeta (los que estaban sueltos en la raíz)",
    "extract only the files without a folder, without copying the rest":
        "extraer solo los archivos sin carpeta, sin copiar el resto",
    "rescue only photos and videos, each in its folder": "rescatar solo fotos y videos, cada uno en su carpeta",
    "first copy the source to this file and recover from the copy (copes with bad sectors; "
    "resumes if interrupted)":
        "copiar primero el origen a este archivo y recuperar desde la copia (tolera sectores "
        "dañados; si se interrumpe, se reanuda)",
    "check in seconds what the format left, without scanning":
        "revisar en segundos qué dejó el formateo, sin escanear",
    "suggest names for the recovered unnamed folders and rename the ones you choose":
        "proponer nombres para las carpetas recuperadas sin nombre y renombrar las que elijas",
    "put back the names from before --names": "volver a poner los nombres anteriores a --names",
    "language of the messages and of the folder names": "idioma de los mensajes y de los nombres de carpeta",
    "the source and the destination are missing": "faltan el origen y el destino",
    "No permission to read the source. Run it with sudo (or as administrator on Windows).":
        "Sin permiso para leer el origen. Ejecútalo con sudo (o como administrador en Windows).",
    "The copy cannot be saved on the same device as the source.":
        "La copia no puede guardarse en el mismo dispositivo que el origen.",
    # scan
    "Source: {} ({})  -- read-only": "Origen: {} ({})  -- solo lectura",
    "Current format (after the format): {}": "Formato actual (después del formateo): {}",
    "No FAT32, exFAT or NTFS folders were found. It may have been a full format (it "
    "overwrites everything). To rescue loose files, use PhotoRec.":
        "No se encontraron carpetas FAT32, exFAT ni NTFS. Puede que haya sido un formateo "
        "completo (sobrescribe todo). Para rescatar archivos sueltos usa PhotoRec.",
    "Format: NTFS  |  cluster {}  |  file records found {} ({}/{} checks match)":
        "Formato: NTFS  |  cluster {}  |  fichas de archivo halladas {} ({}/{} comprobaciones coinciden)",
    "Format: FAT32  |  cluster {}  |  folders found {} ({} match the geometry)":
        "Formato: FAT32  |  cluster {}  |  carpetas halladas {} ({} coinciden con la geometría)",
    "Format: exFAT  |  cluster {}  |  folder blocks found {} ({}/{} references match)":
        "Formato: exFAT  |  cluster {}  |  bloques de carpeta hallados {} ({}/{} referencias coinciden)",
    "Folders: {}  |  files: {}  |  total: {}": "Carpetas: {}  |  archivos: {}  |  total: {}",
    "The old FAT is not reliable: it is not used.": "La tabla FAT antigua no es fiable: no se usa.",
    "Old FAT kept: {} of {} fragmented files have their full chain.":
        "Tabla FAT antigua conservada: {} de {} archivos fragmentados tienen su cadena completa.",
    "No old FAT: {} fragmented files will be copied as contiguous.":
        "Sin tabla FAT antigua: {} archivos fragmentados se copiarán como contiguos.",
    "Files without a folder (root and loose): {} candidates, {} at most":
        "Huérfanos (raíz y sin carpeta): {} candidatos, {} como máximo",
    "Old root recovered: the top folders keep their names.":
        "Raíz antigua recuperada: las carpetas de primer nivel conservan su nombre.",
    "Original name recovered: {} -> {}": "Nombre original recuperado: {} -> {}",
    "  {}/{}.{}   (up to {}, {})": "  {}/{}.{}   (hasta {}, {})",
    # recovery
    "The destination is on the same device as the source. Choose a folder on another disk.":
        "El destino está en el mismo dispositivo que el origen. Elige una carpeta en otro disco.",
    "\nDone: {} files ok, {} with warnings.  Report: {}":
        "\nListo: {} archivos ok, {} con avisos.  Informe: {}",
    "Files without a folder saved in {}: {} (of {} candidates). The root's files are among "
    "them, without their original names.":
        "Huérfanos guardados en {}: {} (de {} candidatos). Entre ellos están los archivos de la "
        "raíz, sin su nombre original.",
    "{} file(s) without a folder were a copy of a file already recovered and are not repeated.":
        "{} huérfano(s) eran copia de un archivo ya recuperado y no se repiten.",
    "{} top folder(s) did not keep their name; their content did. Proposed names:":
        "{} carpeta(s) de primer nivel no conservaron su nombre; su contenido sí. Nombres propuestos:",
    "Nothing has been renamed. To choose which to apply: unformat-usb-cli --names {}":
        "Nada se ha renombrado. Para elegir cuáles aplicar: unformat-usb-cli --names {}",
    "Warning: {} unreadable sectors (filled with zeros).":
        "Atención: {} sectores ilegibles (rellenados con ceros).",
    "Files that were loose in the root: rescue them with PhotoRec if any are missing.":
        "Archivos que estaban sueltos en la raíz: rescátalos con PhotoRec si faltan.",
    "\nCancelled.": "\nCancelado.",
}
ORPHAN_REPORT = {"en": "_orphans_report.csv", "es": "_informe_huerfanos.csv"}

_lang = "en"


def _(text):
    return ES.get(text, text) if _lang == "es" else text


def system_language():
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        value = os.environ.get(var, "")
        if value:
            return "es" if value.lower().startswith("es") else "en"
    if sys.platform == "win32":
        import locale
        code = (locale.getlocale()[0] or "").lower()
        return "es" if code.startswith(("es", "spanish")) else "en"
    return "en"


def set_language(lang):
    global _lang
    _lang = lang if lang in LANGS else "en"
    return texts.texts(_lang)


W = texts.texts("en")


def label(kind, years, theme):
    return naming.compose(W["kinds"][kind], years, theme)


def name_suggestions(dest):
    skip = {W["report"], W["names_log"], ORPHAN_REPORT[_lang]}
    items = naming.items_from_folder(dest, skip=skip)
    return naming.suggest(items, naming.unnamed_folders(items, W["names"]), label)


def print_suggestions(found):
    for i, s in enumerate(found, 1):
        how = (_("original name, it appears in the path {}").format(s.example)
               if s.source == "original" else _("suggested from its content"))
        print(_("  {:3}. {}  ->  {}   ({} files; {})").format(i, os.sep.join(s.folder), s.name, s.files, how))


def review_names(dest):
    """Shows the proposed names and renames only what the person accepts."""
    found = name_suggestions(dest)
    if not found:
        print(_("There are no unnamed folders in {}").format(dest))
        return 0
    print(_("Proposed names for {} folder(s):").format(len(found)))
    print_suggestions(found)
    answer = input(_("\nWhich ones should I rename? (a = all, 1,3,5 = those, Enter = none): ")).strip().lower()
    if answer in ("a", "all", "t", "todas"):
        chosen = found
    else:
        picks = {int(x) for x in answer.replace(" ", "").split(",") if x.isdigit()}
        chosen = [s for i, s in enumerate(found, 1) if i in picks]
    if not chosen:
        print(_("Nothing was changed."))
        return 0
    try:
        done = naming.rename(dest, [(s.folder, s.name) for s in chosen],
                             os.path.join(dest, W["names_log"]), os.path.join(dest, W["report"]))
    except naming.RenameError as e:
        print(_("Could not rename: {} already exists or is missing. What came before is done.").format(e))
        return 1
    print(_("Renamed {}. To undo it: unformat-usb-cli --undo-names {}").format(len(done), dest))
    return 0


def undo_names(dest):
    n = naming.undo(dest, os.path.join(dest, W["names_log"]), os.path.join(dest, W["report"]))
    print(_("Undid {} name change(s).").format(n) if n else _("There were no name changes to undo."))
    return 0


VERDICTS = {
    "in_use": "This drive looks fine: its files are in plain sight and there is no sign of a recent "
              "format. If you are looking for something deleted or from before a format, the full scan "
              "may find it.",
    "names_and_structure": "Good news: the old root folder is still there. The folders can be "
                           "recovered with their names.",
    "structure": "The old FAT survived: the folder tree and fragmented files can be rebuilt. The "
                 "names of the top folders were lost.",
    "scan_needed": "The format erased the root and the FAT. A full scan is needed to know what can "
                   "be recovered.",
    "looks_empty": "Everything sampled is blank. Either the drive held no data, or the format erased "
                   "it (full format, or TRIM on an SSD). The full scan will confirm it.",
}


def print_diagnosis(d):
    print(_("Current format: {}").format(d.current_fs or _("not recognised")))
    print(_("In sight now: {} folders and {} files in the root").format(len(d.current_folders), d.current_files))
    print(_("Old FAT: {}").format(_("yes, {} links").format(d.fat_links) if d.old_fat else _("no")))
    if d.old_root:
        print(_("Old root: yes, {} folders and {} files").format(len(d.root_folders), d.root_files))
        for name in d.root_folders[:30]:
            print(f"    {name}/")
    else:
        print(_("Old root: no"))
    print(_("Blank blocks in the sample: {:.0%}").format(d.blank_fraction))
    print()
    print(_(VERDICTS[d.verdict]))


def progress(label_, done, total, t0):
    pct = 100.0 * done / total if total else 100.0
    el = time.time() - t0
    speed = done / el / 1e6 if el > 0 else 0
    eta = (total - done) / (done / el) if done and el > 0 else 0
    sys.stderr.write("\r" + _("{}: {:5.1f}%  {:6.1f} MB/s  ~{} min left   ").format(
        label_, pct, speed, int(eta // 60)))
    sys.stderr.flush()


def make_image(source, image):
    disk = Source(source)
    free, fits, _x = imaging.space_check(disk.size, os.path.dirname(os.path.abspath(image)))
    if not fits and not os.path.exists(image):
        print(_("Not enough space for the copy: it needs {} and {} is free.").format(
            fmt_size(disk.size), fmt_size(free)))
        return 1
    print(_("Copying {} ({}) to {}").format(source, fmt_size(disk.size), image))
    t0, start, finished = time.time(), None, None
    for e in imaging.make_image(disk, source, image):
        if isinstance(e, imaging.ImageFinished):
            finished = e
        else:
            start = e.done if start is None else start      # a resumed copy starts part-way
            el = time.time() - t0
            speed = (e.done - start) / el / 1e6 if el > 0 else 0
            sys.stderr.write("\r" + _("{}: {:5.1f}%  {:6.1f} MB/s  unreadable: {}   ").format(
                _("Retrying") if e.retrying else _("Copying"), 100.0 * e.done / e.total, speed,
                fmt_size(e.bad_bytes)))
            sys.stderr.flush()
    sys.stderr.write("\n")
    disk.close()
    print(_("Copy finished. Unreadable: {}. You can unplug the source now.").format(fmt_size(finished.bad_bytes)))
    return 0


def parser():
    ap = argparse.ArgumentParser(prog="unformat-usb-cli", description=_(
        "Recovers the folders and files of a formatted FAT32/exFAT/NTFS USB drive. It only reads the source."))
    ap.add_argument("source", nargs="?", help=_("drive image (.img) or device (/dev/sdX, \\\\.\\PhysicalDriveN)"))
    ap.add_argument("dest", nargs="?", help=_("folder to save what is recovered (on ANOTHER disk)"))
    # the Spanish spellings of the first versions still work
    ap.add_argument("--type", "--tipo", dest="fs_type", choices=["fat32", "exfat", "ntfs"],
                    help=_("force the file system type"))
    ap.add_argument("--deleted", "--borrados", dest="deleted", action="store_true",
                    help=_("include files that were already deleted before the format"))
    ap.add_argument("--only-deleted", "--solo-borrados", dest="only_deleted", action="store_true",
                    help=_("on a drive that was not formatted: bring back only the deleted files"))
    ap.add_argument("--list-only", "--solo-listar", dest="list_only", action="store_true",
                    help=_("show what was found without copying"))
    ap.add_argument("--no-orphans", "--sin-huerfanos", dest="no_orphans", action="store_true",
                    help=_("don't look for files without a folder (the loose ones in the root)"))
    ap.add_argument("--only-orphans", "--solo-huerfanos", dest="only_orphans", action="store_true",
                    help=_("extract only the files without a folder, without copying the rest"))
    ap.add_argument("--only-photos", "--solo-fotos", dest="only_photos", action="store_true",
                    help=_("rescue only photos and videos, each in its folder"))
    ap.add_argument("--image", "--imagen", dest="image", metavar="FILE",
                    help=_("first copy the source to this file and recover from the copy (copes with "
                           "bad sectors; resumes if interrupted)"))
    ap.add_argument("--diagnose", "--diagnostico", dest="diagnose", action="store_true",
                    help=_("check in seconds what the format left, without scanning"))
    ap.add_argument("--names", "--nombres", dest="names", metavar="FOLDER",
                    help=_("suggest names for the recovered unnamed folders and rename the ones you choose"))
    ap.add_argument("--undo-names", "--deshacer-nombres", dest="undo_names", metavar="FOLDER",
                    help=_("put back the names from before --names"))
    ap.add_argument("--lang", choices=LANGS, help=_("language of the messages and of the folder names"))
    return ap


def main(argv=None):
    global W
    argv = sys.argv[1:] if argv is None else argv
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--lang", choices=LANGS)
    early, _rest = pre.parse_known_args(argv)
    W = set_language(early.lang or system_language())
    ap = parser()
    args = ap.parse_args(argv)
    names = W["names"]

    if args.names:
        return review_names(args.names)
    if args.undo_names:
        return undo_names(args.undo_names)
    if not args.source or not args.dest:
        ap.error(_("the source and the destination are missing"))

    if args.image:
        try:
            status = make_image(args.source, args.image)
        except PermissionError:
            print(_("No permission to read the source. Run it with sudo (or as administrator on Windows)."))
            return 1
        except UnsafeDestination:
            print(_("The copy cannot be saved on the same device as the source."))
            return 1
        if status:
            return status
        args.source = args.image

    try:
        deleted = "only" if args.only_deleted else args.deleted
        session = Session(args.source, include_deleted=deleted, fs_type=args.fs_type,
                          find_orphans=not args.no_orphans, names=names)
    except PermissionError:
        print(_("No permission to read the source. Run it with sudo (or as administrator on Windows)."))
        return 1

    if args.diagnose:
        print_diagnosis(diagnose(session.disk))
        return 0

    t0 = time.time()
    result = None
    for e in session.scan():
        if isinstance(e, ev.SourceOpened):
            print(_("Source: {} ({})  -- read-only").format(args.source, fmt_size(e.size)))
            if e.current_fs:
                print(_("Current format (after the format): {}").format(e.current_fs))
        elif isinstance(e, ev.ScanProgress):
            progress(_("Scanning"), e.done, e.total, t0)
        elif isinstance(e, ev.NothingFound):
            sys.stderr.write("\n")
            print(_("No FAT32, exFAT or NTFS folders were found. It may have been a full format (it "
                    "overwrites everything). To rescue loose files, use PhotoRec."))
            return 1
        elif isinstance(e, ev.ScanFinished):
            result = e.result
    sys.stderr.write("\n")

    r, g = result, result.geometry
    hits, checked = r.calibration
    if r.fs == "ntfs":
        print(_("Format: NTFS  |  cluster {}  |  file records found {} ({}/{} checks match)").format(
            fmt_size(g.cs), r.folder_blocks, hits, checked))
    elif r.fs == "fat32":
        print(_("Format: FAT32  |  cluster {}  |  folders found {} ({} match the geometry)").format(
            fmt_size(g.cs), checked, hits))
    else:
        print(_("Format: exFAT  |  cluster {}  |  folder blocks found {} ({}/{} references match)").format(
            fmt_size(g.cs), r.folder_blocks, hits, checked))
    print(_("Folders: {}  |  files: {}  |  total: {}").format(len(r.contents), len(r.plans), fmt_size(r.total_bytes)))
    if r.fat_state == "unreliable":
        print(_("The old FAT is not reliable: it is not used."))
    elif r.fat_state == "kept":
        print(_("Old FAT kept: {} of {} fragmented files have their full chain.").format(r.chained, r.fragmented))
    elif r.fragmented:
        print(_("No old FAT: {} fragmented files will be copied as contiguous.").format(r.fragmented))
    if r.orphans:
        print(_("Files without a folder (root and loose): {} candidates, {} at most").format(
            len(r.orphans), fmt_size(sum(o.nclus for o in r.orphans) * g.cs)))
    if r.root_recovered:
        print(_("Old root recovered: the top folders keep their names."))
    for old, new in r.renamed.items():
        print(_("Original name recovered: {} -> {}").format(old, new))

    if args.list_only:
        for rel, en, _a, _b in sorted(r.plans, key=lambda t: (t[0].lower(), t[1].name.lower())):
            print(f"  {os.path.join(rel, en.name)}   ({fmt_size(en.size)})")
        for o in r.orphans:
            print(_("  {}/{}.{}   (up to {}, {})").format(
                names.orphan_dir, names.orphan_file.format(o.cluster), o.ext,
                fmt_size(o.nclus * g.cs), W["methods"][o.method]))
        return 0

    os.makedirs(args.dest, exist_ok=True)
    report_path = os.path.join(args.dest, ORPHAN_REPORT[_lang] if args.only_orphans else W["report"])
    t0 = time.time()
    finished = None
    try:
        with open(report_path, "w", newline="", encoding="utf-8") as rep:
            w = csv.writer(rep)
            w.writerow(W["columns"])
            for e in session.recover(args.dest, only_orphans=args.only_orphans,
                                     only_media=args.only_photos):
                if isinstance(e, ev.CopyProgress):
                    progress(_("Copying"), e.done, e.total, t0)
                elif isinstance(e, ev.FileRecovered):
                    state = "; ".join(W["warnings"][x] for x in e.warnings) or W["ok"]
                    w.writerow([e.path, e.size, e.mtime.isoformat() if e.mtime else "",
                                state, W["methods"][e.method]])
                elif isinstance(e, ev.OrphanRecovered):
                    w.writerow([e.path, e.size, e.mtime.isoformat() if e.mtime else "",
                                W["orphan_status"][e.status], W["methods"][e.method]])
                elif isinstance(e, ev.RecoverFinished):
                    finished = e
    except UnsafeDestination:
        print(_("The destination is on the same device as the source. Choose a folder on another disk."))
        return 1
    sys.stderr.write("\n")

    f = finished
    print(_("\nDone: {} files ok, {} with warnings.  Report: {}").format(f.ok, f.warned, report_path))
    if f.orphans_found:
        print(_("Files without a folder saved in {}: {} (of {} candidates). The root's files are among "
                "them, without their original names.").format(names.orphan_dir, f.orphans_saved, f.orphans_found))
    if f.orphans_duplicate:
        print(_("{} file(s) without a folder were a copy of a file already recovered and are not "
                "repeated.").format(f.orphans_duplicate))
    if r.unnamed_tops and not args.only_orphans:
        print(_("{} top folder(s) did not keep their name; their content did. Proposed names:").format(r.unnamed_tops))
        print_suggestions(name_suggestions(args.dest))
        print(_("Nothing has been renamed. To choose which to apply: unformat-usb-cli --names {}").format(args.dest))
    if f.bad_sectors:
        print(_("Warning: {} unreadable sectors (filled with zeros).").format(f.bad_sectors))
    if not f.orphans_found and not r.root_recovered:
        print(_("Files that were loose in the root: rescue them with PhotoRec if any are missing."))
    return 0


def run():
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(_("\nCancelled."))
        sys.exit(130)


if __name__ == "__main__":
    run()
