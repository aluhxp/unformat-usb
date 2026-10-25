**Formatted your USB drive by mistake? Unformat USB gets your folders and files back. Free, no limits, and it never writes to the drive.**

## New in 0.1.3

- **NTFS drives**: a drive that was NTFS before the format now comes back too, with its folders, names and dates (also after formatting it as exFAT or FAT32).
- **Deleted files**: on a drive that was not formatted, "Look for deleted files" brings back what was deleted, each file in its folder, without touching what is on the drive now. It warns you when a newer file has used the space of a deleted one.
- Folders whose first entry was a deleted file are no longer missed.

(0.1.2 fixed the donation button; 0.1.1 brought Portuguese, the Linux AppImage, the icon and font, and the English command line.)

## Download

- **Windows**: `UnformatUSB.exe` below. Open it and accept the administrator request (a whole drive cannot be read without it).
  It is not signed yet, so Windows may say "Windows protected your PC": choose **More info** → **Run anyway**.
- **macOS**: `UnformatUSB-macOS.zip` below. Unzip it, then the first time right-click the app → **Open**. It asks for your password to read the drive.
- **Linux**: `UnformatUSB-x86_64.AppImage` below. Make it executable (`chmod +x`) and open it. It asks for your password to read the drive.

## What it does

- Rebuilds folders with their names after a quick format (exFAT, FAT32 and NTFS).
- Brings back deleted files on a drive that was not formatted.
- Shows what it finds while it searches; rescue a folder without waiting.
- Safe mode: copies the whole drive first and works on the copy.
- Brings back loose files named after their content, without duplicates.
- Suggests names for folders that lost theirs (you approve, and it can be undone).
- Quick option: only photos and videos, each in its folder.
- English, Spanish and Portuguese.

Windows releases are going to be signed through SignPath Foundation's free program: see the [Code signing policy](https://github.com/aluhxp/unformat-usb/blob/main/docs/code-signing.md).

If it helped you, the last screen has a way to buy us a coffee. Thank you!

---

**¿Formateaste tu USB por error?** Unformat USB recupera tus carpetas y archivos, gratis y sin escribir nada en la unidad. Elige "Español" arriba a la derecha en la app. [Leer en español](https://github.com/aluhxp/unformat-usb/blob/main/README.es.md).

**Formatou seu pendrive por engano?** O Unformat USB recupera suas pastas e arquivos, grátis e sem gravar nada no pendrive. Escolha "Português" no menu de idioma, no alto à direita. [Site em português](https://aluhxp.github.io/unformat-usb/pt/).
