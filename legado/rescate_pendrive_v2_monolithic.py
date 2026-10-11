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
  --sin-huerfanos no busca archivos sin carpeta (los de la raiz)
  --solo-huerfanos  extrae solo los archivos sin carpeta, sin copiar el resto

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
  4. Copia cada archivo. En exFAT el formateo rapido suele dejar intacta la
     tabla FAT antigua: si es asi, los archivos fragmentados se reconstruyen
     siguiendo su cadena de clusters. Si no, se asumen clusters contiguos (lo
     normal en pendrives) y el informe CSV marca los dudosos.
  5. (exFAT) Busca archivos "huerfanos": datos que ningun archivo conocido
     reclama. Ahi estan los archivos que estaban sueltos en la raiz. Salen sin
     nombre en la carpeta _RAIZ_Y_HUERFANOS, con la extension deducida de su
     contenido. Tambien pueden aparecer archivos borrados antes del formateo.
Limitacion: los nombres de las carpetas de PRIMER nivel estaban en la raiz,
que el formateo sobrescribe. Esas carpetas salen como CARPETA_SIN_NOMBRE_<n>,
pero todo lo de adentro conserva sus nombres.
"""

import argparse
import collections
import csv
import datetime
import mmap
import os
import re
import struct
import sys
import time
import urllib.parse
import zipfile

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
                    "root": u32(b, 96), "fat_off": off + u32(b, 80) * bps,
                    "fat_len": u32(b, 84) * bps, "nclus": u32(b, 92)}
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
        self.fat = None   # tabla FAT antigua, si sobrevivio (solo exFAT)

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
    g.fat = load_old_fat(disk, boot, g)
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
        clusters = range(c, c + nclus)
        if g.fat and length and not contiguous:
            # carpeta fragmentada: seguir su cadena en la FAT antigua
            clusters = g.fat.chain(c, max(1, (length + cs - 1) // cs)) or clusters
        for k, cc in enumerate(clusters):
            raw = disk.read(g.coff(cc), cs)
            if not raw:
                break
            if k and length is None and g.coff(cc) not in sset and raw[0] not in (0x85, 0x05, 0x81, 0x82, 0x83, 0xC0, 0xC1, 0x40, 0x41):
                break
            got, ended, junk = ex_parse(raw, want_deleted)
            ents += got
            used.append(cc)
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
# Tabla FAT antigua (exFAT)
# ======================================================================
# El formateo rapido de exFAT reescribe solo las primeras entradas de la FAT.
# El resto conserva las cadenas de los archivos fragmentados (los contiguos no
# usan la FAT en exFAT), asi que se pueden reconstruir sin suponer nada.

EOC = 0xFFFFFFFF


class OldFat:
    def __init__(self, raw, nclus):
        self.n = min(len(raw) // 4, nclus + 2)
        self.t = struct.unpack_from(f"<{self.n}I", raw)

    def chain(self, c, need):
        """Clusters de la cadena que empieza en c, o None si no mide
        exactamente `need` clusters y acaba en fin de cadena."""
        out = []
        while len(out) < need:
            if not 2 <= c < self.n:
                return None
            out.append(c)
            c = self.t[c]
        return out if c == EOC else None

    def free_chain(self, c, claimed):
        """Cadena completa desde c que no pisa clusters de archivos conocidos."""
        out, seen = [], set()
        while c != EOC:
            if not 2 <= c < self.n or c >= len(claimed) or claimed[c] or c in seen:
                return None
            out.append(c)
            seen.add(c)
            c = self.t[c]
        return out


def load_old_fat(disk, boot, g):
    """Solo es fiable si el formateo nuevo uso la misma geometria que el
    antiguo: entonces la FAT sigue en el mismo sitio. Quien la use debe
    comprobarla contra los archivos fragmentados conocidos."""
    if not boot or boot["tipo"] != "exfat" or (boot["cs"], boot["start"]) != (g.cs, g.start):
        return None
    raw = disk.read(boot["fat_off"], boot["fat_len"])
    fat = OldFat(raw, boot["nclus"])
    return fat if any(fat.t[2:]) else None


def to_runs(clusters):
    """[5, 6, 7, 20, 21] -> [(5, 3), (20, 2)]"""
    runs = []
    for c in clusters:
        if runs and runs[-1][0] + runs[-1][1] == c:
            runs[-1][1] += 1
        else:
            runs.append([c, 1])
    return [tuple(r) for r in runs]


def copy_runs(disk, g, runs, nbytes, out, tick=None):
    remaining = nbytes
    for first, count in runs:
        pos, left = g.coff(first), min(remaining, count * g.cs)
        while left > 0:
            data = disk.read(pos, min(left, COPY_BLOCK))
            if not data:
                return
            out.write(data)
            pos += len(data)
            left -= len(data)
            remaining -= len(data)
            if tick:
                tick(len(data))
        if remaining <= 0:
            return


# ======================================================================
# Huerfanos: archivos de la raiz y otros datos sin carpeta (exFAT)
# ======================================================================
# La raiz antigua se pierde, pero los datos de sus archivos siguen ahi. Se
# buscan de dos formas en los clusters que ningun archivo conocido reclama:
#   - cadenas completas en la FAT antigua a las que nadie apunta (archivo
#     fragmentado; sus clusters se conocen con exactitud), y
#   - clusters que empiezan con la firma de un tipo de archivo conocido
#     (archivo contiguo; el final se deduce del propio formato), y
#   - tramos de clusters con texto que acaban en relleno de ceros (archivos
#     de texto, que no tienen firma: notas, scripts, autorun.inf...).
# Un autorun.inf o desktop.ini huerfano puede ademas delatar el nombre
# original de una carpeta de primer nivel.

ORPHAN_DIR = "_RAIZ_Y_HUERFANOS"
MAX_RUN = 2 * 1024 ** 3   # tope para tramos sin final conocido
SIGNATURES = [
    (b"%PDF-", "pdf"), (b"PK\x03\x04", "zip"), (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"), (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "doc"),
    (b"Rar!\x1a\x07", "rar"), (b"7z\xbc\xaf\x27\x1c", "7z"), (b"GIF8", "gif"),
    (b"\x1a\x45\xdf\xa3", "mkv"), (b"SQLite format 3\x00", "sqlite"),
    (b"\x1f\x8b\x08", "gz"), (b"ID3", "mp3"), (b"MZ", "exe"),
]


def sniff(head):
    for sig, ext in SIGNATURES:
        if head.startswith(sig):
            if ext == "exe":   # "MZ" es muy corto: exigir la cabecera PE
                pe = u32(head, 60) if len(head) >= 64 else len(head)
                if head[pe:pe + 4] != b"PE\x00\x00":
                    continue
            return ext
    if head[4:8] == b"ftyp":
        return "mp4"
    return None


TEXT_BYTES = bytes(range(32, 127)) + b"\t\n\r"


def looks_text(data):
    """Casi todo ASCII imprimible (admite acentos en UTF-8 o Latin-1)."""
    data = data.rstrip(b"\x00")
    if not data or b"\x00" in data:
        return False
    plain = len(data) - len(data.translate(None, TEXT_BYTES))
    odd = sum(1 for b in data.translate(None, TEXT_BYTES) if b < 128)
    return plain * 100 >= len(data) * 80 and odd * 100 < len(data)


def text_part(data):
    """Texto con el que empieza un cluster, hasta el primer byte nulo (un
    archivo de texto no los lleva: lo que siga es relleno o restos viejos).
    Devuelve b"" si el cluster no empieza con texto creible."""
    part = data.split(b"\x00", 1)[0]
    if not looks_text(part):
        return b""
    if len(part) < len(data) and any(data[len(part):]) and len(part) < 32 and part[-1:] != b"\n":
        return b""   # unas pocas letras al inicio de un binario
    return part


def text_ext(head):
    """Extension probable de un archivo de texto segun como empieza."""
    low = head.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if low.startswith(b"[autorun]"):
        return "autorun.inf"
    if low.startswith(b"[.shellclassinfo]"):
        return "desktop.ini"
    if low.startswith(b"[trash info]"):
        return "trashinfo"
    if low.startswith(b"#!"):
        return "sh"
    if low.startswith((b"<!doctype html", b"<html")):
        return "html"
    if low.startswith(b"<"):
        return "xml"
    if low.startswith((b"{", b"[{")):
        return "json"
    if any(k in low[:4096] for k in (b"create table", b"insert into", b"-- postgresql", b"-- mysql")):
        return "sql"
    if low.startswith(b"["):
        return "ini"
    return "txt"


class Orphan:
    def __init__(self, cluster, ext, runs, exact, estado=None, size=None):
        self.cluster, self.ext, self.runs, self.exact = cluster, ext, runs, exact
        self.estado = estado   # estado fijado al hallarlo, si no hay nada que verificar
        self.size = size       # tamano exacto en bytes, si se conoce
        self.nclus = sum(n for _, n in runs)


def find_orphans(disk, g, claimed):
    n = len(claimed)
    kinds = {}
    for c in range(2, n):
        if not claimed[c]:
            k = sniff(disk.read(g.coff(c), 1024))
            if k:
                kinds[c] = k
    used = bytearray(claimed)
    found = []
    fat = g.fat
    if fat:
        lim = min(n, fat.n)
        pointed = bytearray(n)
        for c in range(2, lim):
            if 2 <= fat.t[c] < n:
                pointed[fat.t[c]] = 1
        for c in range(2, lim):
            if claimed[c] or pointed[c] or not fat.t[c]:
                continue
            ch = fat.free_chain(c, claimed)
            if ch and not any(used[x] for x in ch):
                if c not in kinds:
                    first = disk.read(g.coff(c), g.cs)
                    if not first.rstrip(b"\x00") or (len(ch) > 1 and (
                            first[-1] == 0 or 0 < len(text_part(first)) < len(first))):
                        # el archivo acaba en su primer cluster: el resto de
                        # la cadena es de otro mas antiguo. Si es texto, lo
                        # recoge la busqueda de texto de mas abajo.
                        continue
                for x in ch:
                    used[x] = 1
                found.append(Orphan(c, kinds.get(c, "bin"), to_runs(ch), True))
    for c in sorted(kinds):
        if used[c]:
            continue
        e = c + 1
        while e < n and not used[e] and e not in kinds and (e - c) * g.cs < MAX_RUN:
            e += 1
        used[c:e] = b"\x01" * (e - c)
        found.append(Orphan(c, kinds[c], [(c, e - c)], False))
    # texto: clusters libres seguidos que son texto, hasta el que se acaba
    # antes de llenar el cluster. Se permite pisar la cola de un tramo hallado
    # por firma, porque ese tramo suele ser mas largo que su archivo.
    taken = bytearray(claimed)
    for o in found:
        if o.exact:
            for first, count in o.runs:
                taken[first:first + count] = b"\x01" * count
        else:
            taken[o.cluster] = 1
    c = 2
    while c < n:
        first, size, closed, head = c, 0, False, b""
        while c < n and not taken[c] and size < MAX_RUN and not closed:
            data = disk.read(g.coff(c), g.cs)
            part = text_part(data)
            if not part:
                break
            head = head or part[:8192]
            size += len(part)
            closed = len(part) < len(data)
            c += 1
        if c == first:
            c += 1
            continue
        if size < 16 and not head.strip():
            continue   # solo saltos de linea
        found.append(Orphan(first, text_ext(head), [(first, c - first)], False,
                            "texto sin carpeta: revisar" if closed
                            else "texto cortado: revisar", size))
    found.sort(key=lambda o: o.cluster)
    return found


def zip_end(m, exact):
    """Posicion donde acaba el zip que empieza en el byte 0, o None."""
    pos = m.rfind(b"PK\x05\x06") if exact else m.find(b"PK\x05\x06")
    while pos != -1:
        if pos + 22 <= len(m):
            cd_size, cd_off, clen = struct.unpack_from("<IIH", m, pos + 12)
            if cd_off + cd_size == pos and pos + 22 + clen <= len(m):
                return pos + 22 + clen
        pos = m.rfind(b"PK\x05\x06", 0, pos) if exact else m.find(b"PK\x05\x06", pos + 1)
    return None


def pdf_end(m):
    """Ultimo %%EOF cuyo startxref apunta a una tabla o a un objeto."""
    pos = m.rfind(b"%%EOF")
    while pos != -1:
        tail = m[max(0, pos - 64):pos]
        mt = re.search(rb"startxref\s+(\d+)\s*$", tail)
        if mt:
            x = int(mt.group(1))
            if x < pos and (m[x:x + 4] == b"xref" or re.match(rb"\d+ \d+ obj", m[x:x + 24])):
                end = pos + 5
                while end < len(m) and m[end] in (10, 13):
                    end += 1
                return end
        pos = m.rfind(b"%%EOF", 0, pos)
    return None


def zip_identify(path):
    """(extension, titulo, fecha, integro) de un zip u Office."""
    ext, title, when = "zip", "", None
    with zipfile.ZipFile(path) as z:
        ok = z.testzip() is None
        names = set(z.namelist())
        for marker, e in (("word/document.xml", "docx"), ("xl/workbook.xml", "xlsx"),
                          ("ppt/presentation.xml", "pptx"), ("AndroidManifest.xml", "apk"),
                          ("META-INF/MANIFEST.MF", "jar")):
            if marker in names:
                ext = e
                break
        else:
            if "mimetype" in names:
                mime = z.read("mimetype")
                ext = {b"application/vnd.oasis.opendocument.text": "odt",
                       b"application/vnd.oasis.opendocument.spreadsheet": "ods",
                       b"application/vnd.oasis.opendocument.presentation": "odp",
                       b"application/epub+zip": "epub"}.get(mime.strip(), "zip")
        if ok and "docProps/core.xml" in names:
            core = z.read("docProps/core.xml").decode("utf-8", "replace")
            mt = re.search(r"<dc:title>([^<]*)</dc:title>", core)
            title = mt.group(1).strip() if mt else ""
            mt = re.search(r"<dcterms:modified[^>]*>([^<]*)<", core)
            try:
                when = datetime.datetime.strptime(mt.group(1)[:19], "%Y-%m-%dT%H:%M:%S") if mt else None
            except ValueError:
                when = None
    return ext, title, when, ok


def save_orphan(disk, g, o, folder):
    """Escribe el huerfano y devuelve (ruta, tamano, fecha, estado), o None
    si resulto no ser un archivo aprovechable."""
    tmp = os.path.join(folder, f"huerfano_{o.cluster}.parte")
    with open(tmp, "wb") as out:
        copy_runs(disk, g, o.runs, o.nclus * g.cs, out)
    size = os.path.getsize(tmp)
    ext, title, when, end, estado = o.ext, "", None, None, None
    if o.size is not None:
        end = min(o.size, size)
    elif size:
        with open(tmp, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as m:
            if ext == "zip":
                end = zip_end(m, o.exact)
            elif ext == "pdf":
                end = pdf_end(m)
                estado = "ok (estructura PDF valida)" if end else None
            elif ext == "png":
                p = m.find(b"IEND")
                end = p + 8 if p != -1 else None
                estado = "ok (PNG completo)" if end else None
            if end is None:
                # sin final reconocible: quitar el relleno de ceros del final
                lo = size - g.cs if o.exact else 0
                end = size
                while end > lo and m[end - 1] == 0:
                    end -= 1
    else:
        end = 0
    os.truncate(tmp, end)
    if ext == "zip":
        try:
            ext, title, when, ok = zip_identify(tmp)
            estado = "ok (verificado)" if ok else "danado"
        except (zipfile.BadZipFile, OSError, ValueError, KeyError, NotImplementedError):
            estado = "danado"
    if not o.exact and (estado is None or estado == "danado") and ext in ("zip", "pdf", "png"):
        os.remove(tmp)   # una firma suelta sin archivo valido detras
        return None
    if estado is None:
        estado = o.estado or ("cadena FAT completa: sin verificar" if o.exact
                              else "tamano aproximado: sin verificar")
    name = f"huerfano_{o.cluster}"
    if title:
        name += " - " + sanitize(title)[:80]
    dest = os.path.join(folder, f"{name}.{ext}")
    os.replace(tmp, dest)
    if when:
        try:
            os.utime(dest, (when.timestamp(), when.timestamp()))
        except (OverflowError, OSError, ValueError):
            pass
    return dest, end, when, estado


def name_clues(disk, g, orphans, contents, paths):
    """Nombres originales de carpetas de primer nivel delatados por restos de
    la raiz:
      - autorun.inf:  'icon=favicon\\usb.ico' dice que la carpeta sin nombre
        que contiene usb.ico se llamaba 'favicon';
      - papelera de Linux (.Trash-*/info): 'Path=Fotos/2020/a.jpg' dice que
        la que contiene '2020' se llamaba 'Fotos'."""
    tops = {c: p for c, p in paths.items() if p.startswith("CARPETA_SIN_NOMBRE_") and os.sep not in p}
    pairs = []   # (carpeta de primer nivel, algo que habia dentro)
    for o in orphans:
        if o.ext not in ("autorun.inf", "trashinfo"):
            continue
        text = text_part(disk.read(g.coff(o.cluster), 8192)).decode("utf-8", "replace")
        if o.ext == "autorun.inf":
            values = [v.split(",")[0].strip('"') for _, v in
                      re.findall(r"(?im)^\s*(icon|open|shellexecute)\s*=\s*(.+?)\s*$", text)]
        else:
            values = [urllib.parse.unquote(v) for v in re.findall(r"(?m)^Path=(.+?)\s*$", text)]
        for value in values:
            parts = [x for x in re.split(r"[\\/]", value) if x and x != "."]
            if len(parts) >= 2 and not re.match(r"^[A-Za-z]:$", parts[0]):
                pairs.append((parts[0], parts[1]))
    found = {}
    for folder, child in pairs:
        match = [c for c in tops if any(en.name.lower() == child.lower() for en in contents[c])]
        if len(match) == 1 and tops[match[0]] not in found and sanitize(folder) not in found.values():
            found[tops[match[0]]] = sanitize(folder)
    return found


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
    ap.add_argument("--sin-huerfanos", action="store_true",
                    help="no buscar archivos sin carpeta (los que estaban sueltos en la raiz)")
    ap.add_argument("--solo-huerfanos", action="store_true",
                    help="extraer solo los archivos sin carpeta, sin copiar el resto")
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

    # Plan de copia: de que clusters sale cada archivo. De paso se anota que
    # clusters tienen dueno, para buscar despues los huerfanos.
    nclus = max(0, (disk.size - g.start) // g.cs)

    def make_plans(fat):
        plans, claimed, frag, chained = [], bytearray(nclus + 2), 0, 0
        for c in dir_cls:
            if 0 <= c < len(claimed):
                claimed[c] = 1
        if boot and boot["tipo"] == "exfat" and (boot["cs"], boot["start"]) == (g.cs, g.start):
            for c in range(2, min(boot["root"] + 1, len(claimed))):
                claimed[c] = 1   # mapa de bits, mayusculas y raiz del formateo nuevo
        for rel, en in tasks:
            ncl = (en.size + g.cs - 1) // g.cs
            runs, metodo = [(en.cluster, ncl)], "contiguo"
            if en.size and en.cluster >= 2 and not en.contiguous:
                frag += 1
                ch = fat.chain(en.cluster, ncl) if fat else None
                if ch:
                    runs, metodo = to_runs(ch), "cadena FAT"
                    chained += 1
            if en.size and en.cluster >= 2:
                for first, count in runs:
                    a, b = max(first, 0), min(first + count, len(claimed))
                    if b > a:
                        claimed[a:b] = b"\x01" * (b - a)
            plans.append((rel, en, runs, metodo))
        return plans, claimed, frag, chained

    plans, claimed, frag, chained = make_plans(g.fat)
    if g.fat and frag and chained * 2 < frag:
        print(f"La tabla FAT no es fiable (solo {chained} de {frag} cadenas cuadran): no se usa.")
        g.fat = None
        plans, claimed, frag, chained = make_plans(None)
    elif g.fat:
        print(f"Tabla FAT antigua conservada: {chained} de {frag} archivos fragmentados "
              "tienen su cadena completa.")
    elif frag:
        print(f"Sin tabla FAT antigua: {frag} archivos fragmentados se copiaran como contiguos.")

    orphans = []
    if tipo == "exfat" and not args.sin_huerfanos:
        orphans = find_orphans(disk, g, claimed)
        print(f"Huerfanos (raiz y sin carpeta): {len(orphans)} candidatos, "
              f"{fmt_size(sum(o.nclus for o in orphans) * g.cs)} como maximo")
        clues = name_clues(disk, g, orphans, contents, paths)
        for old, new in clues.items():
            print(f"Nombre original recuperado: {old} -> {new}")

        def renamed(rel):
            top, sep, rest = rel.partition(os.sep)
            return clues[top] + sep + rest if top in clues else rel

        plans = [(renamed(rel), en, runs, metodo) for rel, en, runs, metodo in plans]
        tasks = [(renamed(rel), en) for rel, en in tasks]
        sin_nombre -= len(clues)

    if args.solo_listar:
        for rel, en in sorted(tasks, key=lambda t: (t[0].lower(), t[1].name.lower())):
            print(f"  {os.path.join(rel, en.name)}   ({fmt_size(en.size)})")
        for o in orphans:
            print(f"  {ORPHAN_DIR}/huerfano_{o.cluster}.{o.ext}   (hasta {fmt_size(o.nclus * g.cs)}, "
                  f"{'cadena FAT' if o.exact else 'por firma'})")
        return 0

    os.makedirs(args.destino, exist_ok=True)
    if args.solo_huerfanos:
        plans = []
    report_path = os.path.join(args.destino, "_informe_huerfanos.csv" if args.solo_huerfanos
                               else "_informe_recuperacion.csv")
    rep = open(report_path, "w", newline="", encoding="utf-8")
    w = csv.writer(rep)
    w.writerow(["ruta", "tamano_bytes", "fecha", "estado", "metodo"])
    done, ok, warn, t0 = 0, 0, 0, time.time()
    taken = set()
    def tick(n):
        nonlocal done
        done += n
        progress("Copiando", done, total, t0)

    for rel, en, runs, metodo in plans:
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
        elif en.size and metodo == "contiguo":
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
            if en.cluster >= 2:
                copy_runs(disk, g, runs, valid, out, tick)
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
                    en.mtime.isoformat() if en.mtime else "", estado, metodo])
    sys.stderr.write("\n")

    saved = 0
    if orphans:
        folder = os.path.join(args.destino, ORPHAN_DIR)
        os.makedirs(folder, exist_ok=True)
        for i, o in enumerate(orphans, 1):
            sys.stderr.write(f"\rHuerfanos: {i}/{len(orphans)}   ")
            sys.stderr.flush()
            res = save_orphan(disk, g, o, folder)
            if res:
                dest, size, when, estado = res
                saved += 1
                w.writerow([os.path.relpath(dest, args.destino), size,
                            when.isoformat() if when else "", estado,
                            "cadena FAT huerfana" if o.exact else "firma en cluster libre"])
        sys.stderr.write("\n")
    rep.close()
    print(f"\nListo: {ok} archivos ok, {warn} con avisos.  Informe: {report_path}")
    if orphans:
        print(f"Huerfanos guardados en {ORPHAN_DIR}: {saved} (de {len(orphans)} candidatos). "
              "Entre ellos estan los archivos de la raiz, sin su nombre original.")
    if sin_nombre:
        print(f"{sin_nombre} carpeta(s) de primer nivel no conservaron su nombre "
              "(CARPETA_SIN_NOMBRE_<n>); su contenido si.")
    if disk.bad_sectors:
        print(f"Atencion: {disk.bad_sectors} sectores ilegibles (rellenados con ceros).")
    if not orphans:
        print("Archivos que estaban sueltos en la raiz: rescatalos con PhotoRec si faltan.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nCancelado.")
        sys.exit(130)
