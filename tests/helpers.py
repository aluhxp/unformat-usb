import hashlib
import io
import os
import random
import zipfile

from usbrescue.core.session import Session


def blob(seed, n):
    return random.Random(seed).randbytes(n)


def make_zip(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


def md5_of(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def run(image, dest=None, **options):
    """Scan (and recover, if dest is given). Returns (result, scan events, recover events)."""
    session = Session(str(image), **options)
    scanned = list(session.scan())
    recovered = list(session.recover(str(dest))) if dest and session.result else []
    session.close()
    return session.result, scanned, recovered


def files_under(dest):
    out = {}
    for base, _, names in os.walk(dest):
        for n in names:
            full = os.path.join(base, n)
            with open(full, "rb") as f:
                out[os.path.relpath(full, dest).replace(os.sep, "/")] = f.read()
    return out


def below_top(path):
    return path.split("/", 1)[1]


def standard_tree():
    """Folders and files every scenario starts from: {path: bytes}."""
    tree = {}
    for i in range(12):
        tree[f"Fotos/viaje_{i:02d}/foto_{i}.jpg"] = blob(i, 5000 + i * 700)
        tree[f"Fotos/viaje_{i:02d}/notas.txt"] = f"viaje numero {i}\n".encode() * 40
    tree["Documentos/Año 2020 ñandú 🎉/informe final con un nombre bastante largo.txt"] = \
        "línea con tildes y eñes\n".encode() * 500
    tree["Documentos/vacio.txt"] = b""
    tree["Documentos/tesis.bin"] = blob(100, 70000)
    tree["iconos/usb.ico"] = blob(101, 3000)
    return tree
