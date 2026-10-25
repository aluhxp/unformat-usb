"""Command line. Messages are in Spanish for now; translations come with i18n."""

import argparse
import csv
import os
import sys
import time

from ..core import model as ev
from ..core import imaging
from ..core import naming
from ..core.diagnose import diagnose
from ..core.reader import Source
from ..core.session import Session, UnsafeDestination
from ..core.util import fmt_size

NAMES = ev.Names(unnamed_folder="CARPETA_SIN_NOMBRE_{}", lost_parent="_HUERFANAS",
                 orphan_dir="_RAIZ_Y_HUERFANOS", orphan_file="huerfano_{}",
                 photo_label="foto {}", link_label="enlace {}", text_pieces="_TROZOS_DE_TEXTO")
WARNINGS = {
    "no_data": "sin datos",
    "fragmented": "fragmentado: puede estar danado",
    "maybe_fragmented": "posible fragmentado: revisar",
    "incomplete": "incompleto",
    "was_deleted": "estaba borrado",
    "bad_sectors": "sectores ilegibles",
}
METHODS = {
    "contiguous": "contiguo",
    "fat_chain": "cadena FAT",
    "orphan_chain": "cadena FAT huerfana",
    "signature": "firma en cluster libre",
}
ORPHAN_STATUS = {
    "verified": "ok (verificado)",
    "pdf_valid": "ok (estructura PDF valida)",
    "png_complete": "ok (PNG completo)",
    "damaged": "danado",
    "chain_unverified": "cadena FAT completa: sin verificar",
    "size_approx": "tamano aproximado: sin verificar",
    "text": "texto sin carpeta: revisar",
    "text_cut": "texto cortado: revisar",
}

# names proposed from what a folder holds (these become folder names: accents are fine)
KIND_WORDS = {
    "photos": "Fotos", "videos": "Videos", "music": "Música", "documents": "Documentos",
    "spreadsheets": "Hojas de cálculo", "presentations": "Presentaciones",
    "programs": "Programas", "disk_images": "Imágenes de disco", "archives": "Comprimidos",
    "code": "Código", "books": "Libros", "fonts": "Fuentes", "mixed": "Varios",
}
REPORT = "_informe_recuperacion.csv"
NAMES_LOG = "_cambios_de_nombre.json"


def spanish_label(kind, years, theme):
    return naming.compose(KIND_WORDS[kind], years, theme)


def name_suggestions(dest):
    items = naming.items_from_folder(dest, skip={REPORT, NAMES_LOG, "_informe_huerfanos.csv"})
    return naming.suggest(items, naming.unnamed_folders(items, NAMES), spanish_label)


def print_suggestions(found):
    for i, s in enumerate(found, 1):
        how = (f"nombre original, aparece en la ruta {s.example}"
               if s.source == "original" else "sugerido por su contenido")
        print(f"  {i:3}. {os.sep.join(s.folder)}  ->  {s.name}   ({s.files} archivos; {how})")


def review_names(dest):
    """Shows the proposed names and renames only what the person accepts."""
    found = name_suggestions(dest)
    if not found:
        print("No hay carpetas sin nombre en", dest)
        return 0
    print(f"Nombres propuestos para {len(found)} carpeta(s):")
    print_suggestions(found)
    answer = input("\n¿Cuáles renombro? (t = todas, 1,3,5 = esas, Enter = ninguna): ").strip().lower()
    if answer in ("t", "todas"):
        chosen = found
    else:
        picks = {int(x) for x in answer.replace(" ", "").split(",") if x.isdigit()}
        chosen = [s for i, s in enumerate(found, 1) if i in picks]
    if not chosen:
        print("No se cambió nada.")
        return 0
    try:
        done = naming.rename(dest, [(s.folder, s.name) for s in chosen],
                             os.path.join(dest, NAMES_LOG), os.path.join(dest, REPORT))
    except naming.RenameError as e:
        print(f"No se pudo renombrar: ya existe o falta {e}. Lo anterior quedó hecho.")
        return 1
    print(f"Renombradas {len(done)}. Para deshacerlo: unformat-usb-cli --deshacer-nombres {dest}")
    return 0


def undo_names(dest):
    n = naming.undo(dest, os.path.join(dest, NAMES_LOG), os.path.join(dest, REPORT))
    print(f"Deshechos {n} cambio(s) de nombre." if n else "No había cambios de nombre que deshacer.")
    return 0


VERDICTS = {
    "in_use": "Este pendrive parece estar bien: sus archivos estan a la vista y no hay senales de un "
              "formateo reciente. Si buscas algo borrado o anterior a un formateo, el escaneo "
              "completo puede encontrarlo.",
    "names_and_structure": "Buenas noticias: la carpeta raiz antigua sigue ahi. Se pueden recuperar "
                           "las carpetas con sus nombres.",
    "structure": "La tabla FAT antigua sobrevivio: se puede reconstruir el arbol de carpetas y los "
                 "archivos fragmentados. Los nombres de las carpetas de primer nivel se perdieron.",
    "scan_needed": "El formateo borro la raiz y la tabla FAT. Hace falta el escaneo completo para "
                   "saber que se puede recuperar.",
    "looks_empty": "Todo lo que se miro esta vacio. O el disco no tenia datos, o se borraron al "
                   "formatear (formateo completo, o TRIM en un SSD). El escaneo completo lo confirma.",
}


def print_diagnosis(d):
    print(f"Formato actual: {d.current_fs or 'no reconocido'}")
    print(f"A la vista ahora: {len(d.current_folders)} carpetas y {d.current_files} archivos en la raiz")
    print(f"Tabla FAT antigua: {'si, ' + str(d.fat_links) + ' enlaces' if d.old_fat else 'no'}")
    if d.old_root:
        print(f"Raiz antigua: si, {len(d.root_folders)} carpetas y {d.root_files} archivos")
        for name in d.root_folders[:30]:
            print(f"    {name}/")
    else:
        print("Raiz antigua: no")
    print(f"Bloques vacios en la muestra: {d.blank_fraction:.0%}")
    print()
    print(VERDICTS[d.verdict])


def progress(label, done, total, t0):
    pct = 100.0 * done / total if total else 100.0
    el = time.time() - t0
    speed = done / el / 1e6 if el > 0 else 0
    eta = (total - done) / (done / el) if done and el > 0 else 0
    sys.stderr.write(f"\r{label}: {pct:5.1f}%  {speed:6.1f} MB/s  faltan ~{int(eta // 60)} min   ")
    sys.stderr.flush()


def make_image(source, image):
    disk = Source(source)
    free, fits, _ = imaging.space_check(disk.size, os.path.dirname(os.path.abspath(image)))
    if not fits and not os.path.exists(image):
        print(f"No hay espacio para la copia: hacen falta {fmt_size(disk.size)} y hay {fmt_size(free)} libres.")
        return 1
    print(f"Copiando {source} ({fmt_size(disk.size)}) a {image}")
    t0, start, finished = time.time(), None, None
    for e in imaging.make_image(disk, source, image):
        if isinstance(e, imaging.ImageFinished):
            finished = e
        else:
            start = e.done if start is None else start      # a resumed copy starts part-way
            el = time.time() - t0
            speed = (e.done - start) / el / 1e6 if el > 0 else 0
            sys.stderr.write(f"\r{'Reintentando' if e.retrying else 'Copiando'}: "
                             f"{100.0 * e.done / e.total:5.1f}%  {speed:6.1f} MB/s  "
                             f"ilegible: {fmt_size(e.bad_bytes)}   ")
            sys.stderr.flush()
    sys.stderr.write("\n")
    disk.close()
    print(f"Copia terminada. Ilegible: {fmt_size(finished.bad_bytes)}. Ya puedes desconectar el origen.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Recupera carpetas y archivos de un pendrive FAT32/exFAT formateado.")
    ap.add_argument("origen", nargs="?", help="imagen del pendrive (.img) o dispositivo (/dev/sdX)")
    ap.add_argument("destino", nargs="?", help="carpeta donde guardar lo recuperado (en OTRO disco)")
    ap.add_argument("--tipo", choices=["fat32", "exfat"], help="forzar el tipo de sistema de archivos")
    ap.add_argument("--borrados", action="store_true",
                    help="incluir archivos que ya estaban borrados antes del formateo")
    ap.add_argument("--solo-listar", action="store_true", help="mostrar lo encontrado sin copiar")
    ap.add_argument("--sin-huerfanos", action="store_true",
                    help="no buscar archivos sin carpeta (los que estaban sueltos en la raiz)")
    ap.add_argument("--solo-huerfanos", action="store_true",
                    help="extraer solo los archivos sin carpeta, sin copiar el resto")
    ap.add_argument("--solo-fotos", action="store_true",
                    help="rescatar solo fotos y videos, cada uno en su carpeta")
    ap.add_argument("--imagen", metavar="ARCHIVO",
                    help="copiar primero el origen a este archivo y recuperar desde la copia "
                         "(tolera sectores danados; si se interrumpe, se reanuda)")
    ap.add_argument("--diagnostico", action="store_true",
                    help="revisar en segundos que dejo el formateo, sin escanear")
    ap.add_argument("--nombres", metavar="CARPETA",
                    help="proponer nombres para las carpetas recuperadas sin nombre y "
                         "renombrar las que elijas")
    ap.add_argument("--deshacer-nombres", metavar="CARPETA",
                    help="volver a poner los nombres anteriores a --nombres")
    args = ap.parse_args(argv)

    if args.nombres:
        return review_names(args.nombres)
    if args.deshacer_nombres:
        return undo_names(args.deshacer_nombres)
    if not args.origen or not args.destino:
        ap.error("faltan el origen y el destino")

    if args.imagen:
        try:
            status = make_image(args.origen, args.imagen)
        except PermissionError:
            print("Sin permiso para leer el origen. Ejecutalo con sudo.")
            return 1
        except UnsafeDestination:
            print("La copia no puede guardarse en el mismo dispositivo que el origen.")
            return 1
        if status:
            return status
        args.origen = args.imagen

    try:
        session = Session(args.origen, include_deleted=args.borrados, fs_type=args.tipo,
                          find_orphans=not args.sin_huerfanos, names=NAMES)
    except PermissionError:
        print("Sin permiso para leer el origen. Ejecutalo con sudo.")
        return 1

    if args.diagnostico:
        print_diagnosis(diagnose(session.disk))
        return 0

    t0 = time.time()
    result = None
    for e in session.scan():
        if isinstance(e, ev.SourceOpened):
            print(f"Origen: {args.origen} ({fmt_size(e.size)})  -- solo lectura")
            if e.current_fs:
                print(f"Formato actual (despues del formateo): {e.current_fs}")
        elif isinstance(e, ev.ScanProgress):
            progress("Escaneando", e.done, e.total, t0)
        elif isinstance(e, ev.NothingFound):
            sys.stderr.write("\n")
            print("No se encontraron carpetas FAT32/exFAT. Puede que haya sido un formateo "
                  "completo (sobrescribe todo) u otro sistema de archivos (NTFS). "
                  "Para rescatar archivos sueltos usa PhotoRec.")
            return 1
        elif isinstance(e, ev.ScanFinished):
            result = e.result
    sys.stderr.write("\n")

    r, g = result, result.geometry
    hits, checked = r.calibration
    if r.fs == "fat32":
        print(f"Formato: FAT32  |  cluster {fmt_size(g.cs)}  |  carpetas halladas {checked} "
              f"({hits} coinciden con la geometria)")
    else:
        print(f"Formato: exFAT  |  cluster {fmt_size(g.cs)}  |  bloques de carpeta hallados "
              f"{r.folder_blocks} ({hits}/{checked} referencias coinciden)")
    print(f"Carpetas: {len(r.contents)}  |  archivos: {len(r.plans)}  |  total: {fmt_size(r.total_bytes)}")
    if r.fat_state == "unreliable":
        print("La tabla FAT antigua no es fiable: no se usa.")
    elif r.fat_state == "kept":
        print(f"Tabla FAT antigua conservada: {r.chained} de {r.fragmented} archivos fragmentados "
              "tienen su cadena completa.")
    elif r.fragmented:
        print(f"Sin tabla FAT antigua: {r.fragmented} archivos fragmentados se copiaran como contiguos.")
    if r.orphans:
        print(f"Huerfanos (raiz y sin carpeta): {len(r.orphans)} candidatos, "
              f"{fmt_size(sum(o.nclus for o in r.orphans) * g.cs)} como maximo")
    if r.root_recovered:
        print("Raiz antigua recuperada: las carpetas de primer nivel conservan su nombre.")
    for old, new in r.renamed.items():
        print(f"Nombre original recuperado: {old} -> {new}")

    if args.solo_listar:
        for rel, en, _, _ in sorted(r.plans, key=lambda t: (t[0].lower(), t[1].name.lower())):
            print(f"  {os.path.join(rel, en.name)}   ({fmt_size(en.size)})")
        for o in r.orphans:
            print(f"  {NAMES.orphan_dir}/{NAMES.orphan_file.format(o.cluster)}.{o.ext}   "
                  f"(hasta {fmt_size(o.nclus * g.cs)}, {METHODS[o.method]})")
        return 0

    os.makedirs(args.destino, exist_ok=True)
    report_path = os.path.join(args.destino, "_informe_huerfanos.csv" if args.solo_huerfanos
                               else REPORT)
    t0 = time.time()
    finished = None
    try:
        with open(report_path, "w", newline="", encoding="utf-8") as rep:
            w = csv.writer(rep)
            w.writerow(["ruta", "tamano_bytes", "fecha", "estado", "metodo"])
            for e in session.recover(args.destino, only_orphans=args.solo_huerfanos,
                                             only_media=args.solo_fotos):
                if isinstance(e, ev.CopyProgress):
                    progress("Copiando", e.done, e.total, t0)
                elif isinstance(e, ev.FileRecovered):
                    estado = "; ".join(WARNINGS[x] for x in e.warnings) or "ok"
                    w.writerow([e.path, e.size, e.mtime.isoformat() if e.mtime else "",
                                estado, METHODS[e.method]])
                elif isinstance(e, ev.OrphanRecovered):
                    w.writerow([e.path, e.size, e.mtime.isoformat() if e.mtime else "",
                                ORPHAN_STATUS[e.status], METHODS[e.method]])
                elif isinstance(e, ev.RecoverFinished):
                    finished = e
    except UnsafeDestination:
        print("El destino esta en el mismo dispositivo que el origen. Elige una carpeta en otro disco.")
        return 1
    sys.stderr.write("\n")

    f = finished
    print(f"\nListo: {f.ok} archivos ok, {f.warned} con avisos.  Informe: {report_path}")
    if f.orphans_found:
        print(f"Huerfanos guardados en {NAMES.orphan_dir}: {f.orphans_saved} (de {f.orphans_found} "
              "candidatos). Entre ellos estan los archivos de la raiz, sin su nombre original.")
    if f.orphans_duplicate:
        print(f"{f.orphans_duplicate} huerfano(s) eran copia de un archivo ya recuperado y no se repiten.")
    if r.unnamed_tops and not args.solo_huerfanos:
        print(f"{r.unnamed_tops} carpeta(s) de primer nivel no conservaron su nombre "
              "(CARPETA_SIN_NOMBRE_<n>); su contenido si. Nombres propuestos:")
        print_suggestions(name_suggestions(args.destino))
        print(f"Nada se ha renombrado. Para elegir cuales aplicar: unformat-usb-cli --nombres {args.destino}")
    if f.bad_sectors:
        print(f"Atencion: {f.bad_sectors} sectores ilegibles (rellenados con ceros).")
    if not f.orphans_found:
        print("Archivos que estaban sueltos en la raiz: rescatalos con PhotoRec si faltan.")
    return 0


def run():
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nCancelado.")
        sys.exit(130)


if __name__ == "__main__":
    run()
