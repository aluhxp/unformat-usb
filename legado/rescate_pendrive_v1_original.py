#!/usr/bin/env python3
"""
rescate_pendrive.py - Recupera carpetas y archivos de un pendrive formateado
(formateo rapido) con sistema de archivos FAT32 o exFAT, conservando la
estructura de subcarpetas y los nombres largos.

    Solo LEE el origen. Nunca escribe en el pendrive.
    No tiene limites de tamano ni pide licencias.
    Solo usa Python 3 (sin instalar nada).

Uso rapido (Linux)
------------------
  1) Identifica el pendrive (NO lo montes, NO escribas nada en el):
       lsblk -o NAME,SIZE,MODEL,FSTYPE
  2) Recomendado: saca una imagen y trabaja sobre ella
       sudo apt install gddrescue
       sudo ddrescue /dev/sdX ~/pendrive.img ~/pendrive.map
  3) Recupera (la carpeta destino debe estar en OTRO disco):
       python3 rescate_pendrive.py ~/pendrive.img ~/recuperado
     O directo desde el pendrive:
       sudo python3 rescate_pendrive.py /dev/sdX ~/recuperado

Opciones
  --solo-listar   muestra lo que encontraria, sin copiar nada
  --tipo fat32|exfat   forzar el tipo (por defecto se detecta solo)
  --borrados      incluye archivos que ya estaban borrados antes del formateo

Como funciona
-------------
El formateo rapido reescribe solo el inicio del disco: sector de arranque,
tabla FAT, (en exFAT) mapa de bits, y la carpeta raiz. Las subcarpetas siguen
en la zona de datos con la lista de sus archivos: nombre, tamano, fecha y
cluster inicial. La herramienta:
  1. Escanea todo el disco buscando esas carpetas.
  2. Deduce la geometria antigua (tamano de cluster e inicio de datos), aunque
     el formateo nuevo haya usado otra.
  3. Reconstruye el arbol de carpetas.
  4. Copia cada archivo asumiendo clusters contiguos (lo normal en pendrives).
     La tabla FAT antigua se perdio, asi que un archivo fragmentado puede salir
     danado: el informe CSV lo marca para revisarlo.
Limitacion: los nombres de las carpetas de PRIMER nivel estaban en la raiz,
que el formateo sobrescribe. Esas carpetas salen como CARPETA_SIN_NOMBRE_<n>,
pero todo lo de adentro conserva sus nombres.
"""

import argparse
import collections
import csv
import datetime
import os
import struct
import sys
import time

SECTOR = 512
ENTRY = 32
CHUNK = 32 * 1024 * 1024
COPY_BLOCK = 8 * 1024 * 1024

# FAT32
DOT = b".          \x10"
DOTDOT = b"..         \x10"
ATTR_LFN, ATTR_DIR, ATTR_VOL = 0x0F, 0x10, 0x08
INVALID_SFN = set(b'"*+,./:;<=>?[\\]|')

# exFAT
EX_FILE, EX_STREAM, EX_NAME = 0x85, 0xC0, 0xC1
EX_KNOWN = {0x81, 0x82, 0x83, 0xA0, 0xA1, 0xA2, 0x85, 0xC0, 0xC1}


# ======================================================================
# Utilidades
# ======================================================================

def fmt_size(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n} B" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


def progress(label, done, total, t0):
    pct = 100.0 * done / total if total else 100.0
    el = time.time() - t0
    speed = done / el / 1e6 if el > 0 else 0
    eta = (total - done) / (done / el) if done and el > 0 else 0
    sys.stderr.write(f"\r{label}: {pct:5.1f}%  {speed:6.1f} MB/s  faltan ~{int(eta // 60)} min   ")
    sys.stderr.flush()


def sanitize(name):
    bad = '<>:"/\\|?*\x00'
    name = "".join("_" if c in bad or ord(c) < 32 else c for c in name)
    name = name.strip().rstrip(".")
    return (name or "_sin_nombre")[:240]


def u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def u64(b, o):
    return struct.unpack_from("<Q", b, o)[0]


# ======================================================================
# Lectura del origen (tolera sectores defectuosos)
# ======================================================================

class Disk:
    def __init__(self, path):
        self.path = path
        self.f = open(path, "rb", buffering=0)
        self.f.seek(0, os.SEEK_END)
        self.size = self.f.tell()
        self.bad_sectors = 0

    def _raw(self, off, n):
        self.f.seek(off)
        out = bytearray()
        while len(out) < n:
            c = self.f.read(n - len(out))
            if not c:
                break
            out += c
        return out

    def read(self, off, n):
        if off < 0 or off >= self.size or n <= 0:
            return b""
        n = min(n, self.size - off)
        try:
            return bytes(self._raw(off, n))
        except OSError:
            # sector a sector; los ilegibles se rellenan con ceros
            out = bytearray()
            pos = off
            while pos < off + n:
                step = min(SECTOR - pos % SECTOR, off + n - pos)
                try:
                    out += self._raw(pos, step)
                except OSError:
                    out += b"\x00" * step
                    self.bad_sectors += 1
                pos += step
            return bytes(out)


def boot_info(disk):
    """Sector de arranque actual (tras el formateo). Puede apuntar a otra
    geometria que la antigua; solo se usa como primera pista."""
    def vbr(off):
        b = disk.read(off, 512)
        if len(b) < 512 or b[510:512] != b"\x55\xaa":
            return None
        if b[3:11] == b"EXFAT   ":
            bps = 1 << b[108]
            cs = bps << b[109]
            return {"tipo": "exfat", "cs": cs, "start": off + u32(b, 88) * bps,
                    "root": u32(b, 96)}
        bps, spc, rsv, nfats = struct.unpack_from("<HBHB", b, 11)
        fatsz = u32(b, 36)
        if bps in (512, 1024, 2048, 4096) and spc and fatsz and u16(b, 22) == 0:
            return {"tipo": "fat32", "cs": bps * spc,
                    "start": off + (rsv + nfats * fatsz) * bps, "root": u32(b, 44)}
        return None

    info = vbr(0)
    if info:
        return info
    mbr = disk.read(0, 512)
    if len(mbr) == 512 and mbr[510:512] == b"\x55\xaa":
        for i in range(4):
            lba = u32(mbr, 446 + 16 * i + 8)
            if lba:
                info = vbr(lba * 512)
                if info:
                    return info
    return None


# ======================================================================
# Escaneo (una sola pasada para FAT32 y exFAT)
# ======================================================================

def plausible_sfn(e):
    first, attr = e[0], e[11]
    if first in (0x00, 0x20) or attr & 0xC0:
        return False
    for i, b in enumerate(e[:11]):
        if b < 0x20 and not (i == 0 and b == 0x05):
            return False
        if b in INVALID_SFN and not (first == 0x2E and b == 0x2E):
            return False
    return True


def exfat_set_ok(buf, i, allow_deleted):
    if i + 96 > len(buf):
        return False
    t0, t1, t2 = buf[i], buf[i + 32], buf[i + 64]
    if allow_deleted:
        t0, t1, t2 = t0 | 0x80, t1 | 0x80, t2 | 0x80
    if (t0, t1, t2) != (EX_FILE, EX_STREAM, EX_NAME):
        return False
    sec, nlen = buf[i + 1], buf[i + 35]
    return nlen > 0 and sec == 1 + (nlen + 14) // 15


def scan(disk, want_deleted):
    fat_dots, fat_refs, ex_starts = [], [], []
    t0 = time.time()
    off = 0
    while off < disk.size:
        buf = disk.read(off, CHUNK + 128)
        if not buf:
            break
        lim = min(CHUNK, len(buf))

        # --- FAT32: carpeta = entrada '.' alineada a sector seguida de '..'
        i = buf.find(DOT)
        while i != -1 and i < lim:
            if (off + i) % SECTOR == 0 and buf[i + 32:i + 44] == DOTDOT:
                own = u16(buf, i + 20) << 16 | u16(buf, i + 26)
                par = u16(buf, i + 52) << 16 | u16(buf, i + 58)
                if own >= 2:
                    fat_dots.append((off + i, own, par))
            i = buf.find(DOT, i + 1)

        # --- FAT32: entradas con atributo carpeta (para hallar nombres en
        #     restos de la raiz antigua)
        attrs = buf[11:lim:ENTRY]
        j = attrs.find(b"\x10")
        while j != -1:
            p = j * ENTRY
            e = buf[p:p + ENTRY]
            if e[0] not in (0x2E, 0xE5) and plausible_sfn(e):
                cl = u16(e, 20) << 16 | u16(e, 26)
                if cl >= 2:
                    fat_refs.append((off + p, cl))
            j = attrs.find(b"\x10", j + 1)

        # --- exFAT: sector que empieza con un conjunto Archivo+Stream+Nombre
        firsts = buf[0:lim:SECTOR]
        for code in ((EX_FILE, 0x05) if want_deleted else (EX_FILE,)):
            k = firsts.find(bytes([code]))
            while k != -1:
                p = k * SECTOR
                if exfat_set_ok(buf, p, want_deleted):
                    ex_starts.append(off + p)
                k = firsts.find(bytes([code]), k + 1)

        off += CHUNK
        progress("Escaneando", min(off, disk.size), disk.size, t0)
    sys.stderr.write("\n")
    ex_starts.sort()
    return fat_dots, fat_refs, ex_starts


CS_CANDIDATES = [512 << k for k in range(0, 17)]  # 512 B .. 32 MB


# ======================================================================
# Modelo comun
# ======================================================================

class Entry:
    __slots__ = ("name", "is_dir", "cluster", "size", "valid", "mtime",
                 "deleted", "contiguous")

    def __init__(self):
        self.valid = None
        self.contiguous = True
        self.deleted = False


class Geometry:
    def __init__(self, cs, start):
        self.cs, self.start = cs, start

    def coff(self, c):
        return self.start + (c - 2) * self.cs

    def cluster_of(self, off):
        return (off - self.start) // self.cs + 2


# ======================================================================
# FAT32
# ======================================================================

def fat_dt(date, tm):
    try:
        return datetime.datetime(1980 + (date >> 9), (date >> 5) & 0xF, date & 0x1F,
                                 tm >> 11, (tm >> 5) & 0x3F, (tm & 0x1F) * 2)
    except ValueError:
        return None


def sfn_checksum(raw11):
    s = 0
    for b in raw11:
        s = (((s & 1) << 7) + (s >> 1) + b) & 0xFF
    return s


def short_name(raw11, nt):
    base = raw11[:8].decode("cp850", "replace").rstrip()
    ext = raw11[8:11].decode("cp850", "replace").rstrip()
    if nt & 0x08:
        base = base.lower()
    if nt & 0x10:
        ext = ext.lower()
    if base.startswith("\x05"):
        base = "\xe5" + base[1:]
    return f"{base}.{ext}" if ext else base


def fat_parse(raw, want_deleted):
    """Devuelve (entradas, fin_encontrado, basura_encontrada)."""
    out, lfn, lfn_sum = [], {}, None
    for p in range(0, len(raw) - ENTRY + 1, ENTRY):
        e = raw[p:p + ENTRY]
        first, attr = e[0], e[11]
        if first == 0x00:
            return out, True, False
        deleted = first == 0xE5
        if attr == ATTR_LFN:
            part = (e[1:11] + e[14:26] + e[28:32]).decode("utf-16-le", "replace")
            part = part.split("\x00")[0].replace("￿", "")
            if deleted:
                lfn[-len(lfn) - 1] = part   # orden aproximado
            else:
                if first & 0x40:
                    lfn = {}
                lfn[first & 0x1F] = part
            lfn_sum = e[13]
            continue
        if not deleted and not plausible_sfn(e):
            return out, False, True
        if attr & ATTR_VOL or e[:11] in (DOT[:11], DOTDOT[:11]) or (deleted and not want_deleted):
            lfn = {}
            continue
        name = None
        if lfn and (deleted or lfn_sum == sfn_checksum(e[:11])):
            keys = sorted(lfn, reverse=deleted) if deleted else sorted(lfn)
            name = "".join(lfn[k] for k in keys)
        if not name:
            name = short_name(e[:11], e[12])
            if deleted:
                name = "_" + name[1:]
        lfn = {}
        en = Entry()
        en.name = name
        en.is_dir = bool(attr & ATTR_DIR)
        en.cluster = u16(e, 20) << 16 | u16(e, 26)
        en.size = u32(e, 28)
        en.mtime = fat_dt(u16(e, 24), u16(e, 22))
        en.deleted = deleted
        out.append(en)
    return out, False, False


def fat_calibrate(dots, boot):
    cands = list(CS_CANDIDATES)
    if boot and boot["tipo"] == "fat32":
        cands.insert(0, boot["cs"])
    best = None
    for cs in dict.fromkeys(cands):
        votes = collections.Counter(o - (c - 2) * cs for o, c, _ in dots)
        start, hits = votes.most_common(1)[0]
        if start >= 0 and (best is None or hits > best[2]):
            best = (cs, start, hits)
    return best


def build_fat(disk, dots, refs, boot, want_deleted):
    cs, start, hits = fat_calibrate(dots, boot)
    g = Geometry(cs, start)
    print(f"Formato: FAT32  |  cluster {fmt_size(cs)}  |  carpetas halladas {len(dots)} "
          f"({hits} coinciden con la geometria)")
    parent_of = {own: par for o, own, par in dots if o == g.coff(own)}
    root_cl = boot["root"] if boot and boot["tipo"] == "fat32" else 2

    contents, dir_cls = {}, {}
    for c in parent_of:
        ents, used = [], []
        for k in range(4096):   # carpeta contigua; para al llegar a algo que no lo es
            raw = disk.read(g.coff(c + k), cs)
            if not raw:
                break
            if k and (raw[:12] == DOT or raw[0] == 0 or not (plausible_sfn(raw[:32]) or raw[11] == ATTR_LFN)):
                break
            got, ended, junk = fat_parse(raw, want_deleted)
            ents += got
            used.append(c + k)
            if ended or junk:
                break
        contents[c] = ents
        for u in used:
            dir_cls[u] = c

    # restos de la raiz antigua que mencionan carpetas de primer nivel
    root_ents, frags = {}, set()
    for off, cl in refs:
        if parent_of.get(cl, -1) in (0, root_cl):
            fr = g.cluster_of(off)
            if fr >= 2 and fr not in dir_cls:
                frags.add(fr)
    for fr in sorted(frags):
        for en in fat_parse(disk.read(g.coff(fr), cs), want_deleted)[0]:
            root_ents[(en.name, en.cluster)] = en
    return g, parent_of, contents, list(root_ents.values()), dir_cls, root_cl


# ======================================================================
# exFAT
# ======================================================================

def ex_dt(ts):
    try:
        return datetime.datetime(1980 + (ts >> 25), (ts >> 21) & 0xF, (ts >> 16) & 0x1F,
                                 (ts >> 11) & 0x1F, (ts >> 5) & 0x3F, (ts & 0x1F) * 2)
    except ValueError:
        return None


def ex_checksum(es):
    chk = 0
    for i, b in enumerate(es):
        if i in (2, 3):
            continue
        chk = ((((chk & 1) << 15) | (chk >> 1)) + b) & 0xFFFF
    return chk


def ex_parse(raw, want_deleted):
    """Devuelve (entradas, fin_encontrado, basura_encontrada)."""
    out, p = [], 0
    n = len(raw)
    while p + ENTRY <= n:
        t = raw[p]
        if t == 0x00:
            return out, True, False
        deleted = not (t & 0x80)
        if (t | 0x80) not in EX_KNOWN:
            return out, False, True
        if (t | 0x80) != EX_FILE:
            p += ENTRY
            continue
        sec = raw[p + 1]
        end = p + ENTRY * (1 + sec)
        if sec < 2 or end > n:
            p += ENTRY
            continue
        es = raw[p:end]
        if (es[32] | 0x80) != EX_STREAM:
            p += ENTRY
            continue
        if deleted and not want_deleted:
            p = end
            continue
        if not deleted and ex_checksum(es) != u16(es, 2):
            p += ENTRY
            continue
        nlen = es[35]
        name = b"".join(es[64 + 32 * k + 2:64 + 32 * k + 32] for k in range(sec - 1))
        name = name.decode("utf-16-le", "replace")[:nlen]
        en = Entry()
        en.name = name if not deleted else "_" + name
        en.is_dir = bool(u16(es, 4) & 0x10)
        en.cluster = u32(es, 52)
        en.size = u64(es, 56)
        en.valid = u64(es, 40)
        en.contiguous = bool(es[33] & 0x02)
        en.mtime = ex_dt(u32(es, 12))
        en.deleted = deleted
        out.append(en)
        p = end
    return out, False, False


def ex_calibrate(disk, starts, boot, want_deleted):
    """Busca (cluster, inicio) para que las carpetas citadas caigan sobre
    sectores donde realmente hay carpetas."""
    sset = set(starts)
    refs = []
    for s in starts[:4000]:
        for en in ex_parse(disk.read(s, 4096), want_deleted)[0]:
            if en.is_dir and en.cluster >= 2:
                refs.append(en.cluster)
    refs = list(dict.fromkeys(refs))
    if not refs:
        if boot and boot["tipo"] == "exfat":
            return boot["cs"], boot["start"], 0, 0
        return None

    def score(cs, st):
        return sum(1 for x in refs if st + (x - 2) * cs in sset)

    if boot and boot["tipo"] == "exfat":
        sc = score(boot["cs"], boot["start"])
        if sc >= 0.6 * len(refs):
            return boot["cs"], boot["start"], sc, len(refs)
    sample = refs[:300]
    best = None
    for cs in CS_CANDIDATES[3:]:   # 4 KB .. 32 MB
        votes = collections.Counter()
        for x in sample:
            base = (x - 2) * cs
            for s in starts:
                st = s - base
                if st >= 0:
                    votes[st] += 1
        if votes:
            st, _ = votes.most_common(1)[0]
            sc = score(cs, st)
            if best is None or sc > best[2]:
                best = (cs, st, sc, len(refs))
    return best


def build_exfat(disk, starts, boot, want_deleted):
    cal = ex_calibrate(disk, starts, boot, want_deleted)
    if not cal:
        return None
    cs, start, sc, nrefs = cal
    g = Geometry(cs, start)
    print(f"Formato: exFAT  |  cluster {fmt_size(cs)}  |  bloques de carpeta hallados {len(starts)} "
          f"({sc}/{nrefs} referencias coinciden)")
    sset = set(starts)

    contents, dir_cls, known_len = {}, {}, {}
    parent_of = {}

    def read_dir(c, length=None, contiguous=True):
        if c in contents:
            return
        ents, used = [], []
        nclus = max(1, (length + cs - 1) // cs) if length and contiguous else 4096
        for k in range(nclus):
            raw = disk.read(g.coff(c + k), cs)
            if not raw:
                break
            if k and length is None and g.coff(c + k) not in sset and raw[0] not in (0x85, 0x05, 0x81, 0x82, 0x83, 0xC0, 0xC1, 0x40, 0x41):
                break
            got, ended, junk = ex_parse(raw, want_deleted)
            ents += got
            used.append(c + k)
            if ended or junk:
                break
        contents[c] = ents
        for u in used:
            dir_cls[u] = c

    # recorrer en orden: primero carpetas sin padre conocido (por offset)
    pending = [g.cluster_of(s) for s in starts if (s - g.start) % cs == 0 and s >= g.start]
    queue = list(pending)
    # dos pasadas: la primera descubre todas las referencias padre->hijo
    for c in queue:
        if c in dir_cls:
            continue
        read_dir(c, known_len.get(c, (None, True))[0], known_len.get(c, (None, True))[1])
        for en in contents[c]:
            if en.is_dir and en.cluster >= 2:
                parent_of.setdefault(en.cluster, c)
                known_len[en.cluster] = (en.size, en.contiguous)
                if en.cluster not in contents:
                    queue.append(en.cluster)
    # re-leer con el tamano exacto las carpetas que tenian tamano conocido
    for c, (ln, cont) in known_len.items():
        if c in contents:
            for u in [u for u, owner in dir_cls.items() if owner == c]:
                del dir_cls[u]
            del contents[c]
            read_dir(c, ln, cont)

    # bloques que no son hijos de nadie: carpetas de primer nivel (su nombre
    # estaba en la raiz, que se perdio). En exFAT la raiz casi nunca ocupa mas
    # de un cluster, asi que no se buscan restos de ella.
    for c in list(contents):
        if c not in parent_of:
            parent_of[c] = 0
    return g, parent_of, contents, [], dir_cls, 0


# ======================================================================
# Arbol y copia
# ======================================================================

def build_paths(parent_of, contents, root_ents, root_cl):
    names = {}
    for en in root_ents:
        if en.is_dir and en.cluster in contents:
            names.setdefault(en.cluster, en.name)
    for par, ents in contents.items():
        for en in ents:
            if en.is_dir and en.cluster in contents and parent_of.get(en.cluster) == par:
                names.setdefault(en.cluster, en.name)
    paths = {}

    def path_of(c, depth=0):
        if c in paths:
            return paths[c]
        par = parent_of.get(c, 0)
        name = sanitize(names.get(c, f"CARPETA_SIN_NOMBRE_{c}"))
        if par in (0, root_cl, c) or depth > 100:
            p = name
        elif par not in contents:
            p = os.path.join("_HUERFANAS", name)
        else:
            p = os.path.join(path_of(par, depth + 1), name)
        paths[c] = p
        return p

    for c in contents:
        path_of(c)
    return paths


def main():
    ap = argparse.ArgumentParser(
        description="Recupera carpetas y archivos de un pendrive FAT32/exFAT formateado.")
    ap.add_argument("origen", help="imagen del pendrive (.img) o dispositivo (/dev/sdX)")
    ap.add_argument("destino", help="carpeta donde guardar lo recuperado (en OTRO disco)")
    ap.add_argument("--tipo", choices=["fat32", "exfat"], help="forzar el tipo de sistema de archivos")
    ap.add_argument("--borrados", action="store_true",
                    help="incluir archivos que ya estaban borrados antes del formateo")
    ap.add_argument("--solo-listar", action="store_true", help="mostrar lo encontrado sin copiar")
    args = ap.parse_args()

    try:
        disk = Disk(args.origen)
    except PermissionError:
        print("Sin permiso para leer el origen. Ejecutalo con sudo.")
        return 1
    print(f"Origen: {args.origen} ({fmt_size(disk.size)})  -- solo lectura")
    boot = boot_info(disk)
    if boot:
        print(f"Formato actual (despues del formateo): {boot['tipo']}")

    dots, refs, ex_starts = scan(disk, args.borrados)
    tipo = args.tipo or ("fat32" if len(dots) >= len(ex_starts) / 4 and dots else "exfat")
    if tipo == "fat32" and dots:
        g, parent_of, contents, root_ents, dir_cls, root_cl = build_fat(disk, dots, refs, boot, args.borrados)
    elif tipo == "exfat" and ex_starts:
        res = build_exfat(disk, ex_starts, boot, args.borrados)
        if not res:
            print("No se pudo deducir la geometria exFAT.")
            return 1
        g, parent_of, contents, root_ents, dir_cls, root_cl = res
    else:
        print("No se encontraron carpetas FAT32/exFAT. Puede que haya sido un formateo "
              "completo (sobrescribe todo) u otro sistema de archivos (NTFS). "
              "Para rescatar archivos sueltos usa PhotoRec.")
        return 1

    paths = build_paths(parent_of, contents, root_ents, root_cl)
    tasks = [(paths[c], en) for c, ents in contents.items() for en in ents if not en.is_dir]
    tasks += [("", en) for en in root_ents if not en.is_dir]
    total = sum(en.size for _, en in tasks)
    sin_nombre = len({p.split(os.sep)[0] for p in paths.values()
                      if p.startswith("CARPETA_SIN_NOMBRE_")})
    print(f"Carpetas: {len(contents)}  |  archivos: {len(tasks)}  |  total: {fmt_size(total)}")

    if args.solo_listar:
        for rel, en in sorted(tasks, key=lambda t: (t[0].lower(), t[1].name.lower())):
            print(f"  {os.path.join(rel, en.name)}   ({fmt_size(en.size)})")
        return 0

    os.makedirs(args.destino, exist_ok=True)
    report_path = os.path.join(args.destino, "_informe_recuperacion.csv")
    rep = open(report_path, "w", newline="", encoding="utf-8")
    w = csv.writer(rep)
    w.writerow(["ruta", "tamano_bytes", "fecha", "estado"])
    done, ok, warn, t0 = 0, 0, 0, time.time()
    taken = set()
    for rel, en in tasks:
        folder = os.path.join(args.destino, rel)
        os.makedirs(folder, exist_ok=True)
        fname = sanitize(en.name)
        dest = os.path.join(folder, fname)
        n = 1
        while dest.lower() in taken or os.path.exists(dest):
            base, ext = os.path.splitext(fname)
            dest = os.path.join(folder, f"{base} ({n}){ext}")
            n += 1
        taken.add(dest.lower())

        avisos = []
        if en.size and en.cluster < 2:
            avisos.append("sin datos")
        elif en.size:
            ncl = (en.size + g.cs - 1) // g.cs
            if any((en.cluster + k) in dir_cls for k in range(min(ncl, 1 << 20))):
                avisos.append("fragmentado: puede estar danado")
            elif not en.contiguous:
                avisos.append("posible fragmentado: revisar")
            if g.coff(en.cluster) + en.size > disk.size:
                avisos.append("incompleto")
        if en.deleted:
            avisos.append("estaba borrado")

        valid = en.size if en.valid is None else min(en.valid, en.size)
        bad_before = disk.bad_sectors
        with open(dest, "wb") as out:
            pos, remaining = g.coff(en.cluster), valid
            while remaining > 0 and en.cluster >= 2:
                data = disk.read(pos, min(remaining, COPY_BLOCK))
                if not data:
                    break
                out.write(data)
                pos += len(data)
                remaining -= len(data)
                done += len(data)
                progress("Copiando", done, total, t0)
            if en.size > valid:
                out.truncate(en.size)
        if disk.bad_sectors > bad_before:
            avisos.append("sectores ilegibles")
        if en.mtime:
            try:
                ts = en.mtime.timestamp()
                os.utime(dest, (ts, ts))
            except (OverflowError, OSError, ValueError):
                pass
        estado = "; ".join(avisos) or "ok"
        ok += not avisos
        warn += bool(avisos)
        w.writerow([os.path.relpath(dest, args.destino), en.size,
                    en.mtime.isoformat() if en.mtime else "", estado])
    rep.close()
    sys.stderr.write("\n")
    print(f"\nListo: {ok} archivos ok, {warn} con avisos.  Informe: {report_path}")
    if sin_nombre:
        print(f"{sin_nombre} carpeta(s) de primer nivel no conservaron su nombre "
              "(CARPETA_SIN_NOMBRE_<n>); su contenido si.")
    if disk.bad_sectors:
        print(f"Atencion: {disk.bad_sectors} sectores ilegibles (rellenados con ceros).")
    print("Archivos que estaban sueltos en la raiz: rescatalos con PhotoRec si faltan.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nCancelado.")
        sys.exit(130)
