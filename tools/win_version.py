"""Writes the Windows version information (product name and version) that
PyInstaller puts into UnformatUSB.exe. Usage: python tools/win_version.py OUT"""

import sys

sys.path.insert(0, "src")
from usbrescue.brand import APP_NAME, VERSION  # noqa: E402

nums = tuple(int(n) for n in (VERSION.split(".") + ["0"] * 4)[:4])
text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('ProductName', '{APP_NAME}'),
      StringStruct('ProductVersion', '{VERSION}'),
      StringStruct('FileDescription', '{APP_NAME}'),
      StringStruct('FileVersion', '{VERSION}'),
      StringStruct('InternalName', 'UnformatUSB'),
      StringStruct('OriginalFilename', 'UnformatUSB.exe'),
      StringStruct('CompanyName', '{APP_NAME} project'),
      StringStruct('LegalCopyright', 'GPL-3.0-or-later')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    fh.write(text)
