"""Command line. Messages are in Spanish for now; translations come with i18n."""

import argparse
import csv
import os
import sys
import time

from ..core import model as ev
from ..core.session import Session, UnsafeDestination
from ..core.util import fmt_size

NAMES = ev.Names(unnamed_folder="CARPETA_SIN_NOMBRE_{}", lost_parent="_HUERFANAS",
                 orphan_dir="_RAIZ_Y_HUERFANOS", orphan_file="huerfano_{}")
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


def progress(label, done, total, t0):
    pct = 100.0 * done / total if total else 100.0
    el = time.time() - t0
    speed = done / el / 1e6 if el > 0 else 0
    eta = (total - done) / (done / el) if done and el > 0 else 0
    sys.stderr.write(f"\r{label}: {pct:5.1f}%  {speed:6.1f} MB/s  faltan ~{int(eta // 60)} min   ")
    sys.stderr.flush()


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Recupera carpetas y archivos de un pendrive FAT32/exFAT formateado.")
    ap.add_argument("origen", help="imagen del pendrive (.img) o dispositivo (/dev/sdX)")
    ap.add_argument("destino", help="carpeta donde guardar lo recuperado (en OTRO disco)")
    ap.add_argument("--tipo", choices=["fat32", "exfat"], help="forzar el tipo de sistema de archivos")
    ap.add_argument("--borrados", action="store_true",
                    help="incluir archivos que ya estaban borrados antes del formateo")
    ap.add_argument("--solo-listar", action="store_true", help="mostrar lo encontrado sin copiar")
    ap.add_argument("--sin-huerfanos", action="store_true",
                    help="no buscar archivos sin carpeta (los que estaban sueltos en la raiz)")
    ap.add_argument("--solo-huerfanos", action="store_true",
                    help="extraer solo los archivos sin carpeta, sin copiar el resto")
    args = ap.parse_args(argv)

    try:
        session = Session(args.origen, include_deleted=args.borrados, fs_type=args.tipo,
                          find_orphans=not args.sin_huerfanos, names=NAMES)
    except PermissionError:
        print("Sin permiso para leer el origen. Ejecutalo con sudo.")
        return 1

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
                               else "_informe_recuperacion.csv")
    t0 = time.time()
    finished = None
    try:
        with open(report_path, "w", newline="", encoding="utf-8") as rep:
            w = csv.writer(rep)
            w.writerow(["ruta", "tamano_bytes", "fecha", "estado", "metodo"])
            for e in session.recover(args.destino, only_orphans=args.solo_huerfanos):
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
    if r.unnamed_tops:
        print(f"{r.unnamed_tops} carpeta(s) de primer nivel no conservaron su nombre "
              "(CARPETA_SIN_NOMBRE_<n>); su contenido si.")
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
