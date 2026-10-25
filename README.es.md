# Unformat USB

**Recupera las carpetas y archivos de un pendrive formateado por error. Gratis, sin límites, y sin escribir nunca en el pendrive.**

[Read in English](README.md)

## ¿Formateaste tu pendrive por error?

Para todo y no copies nada nuevo en él. Un formateo rápido (el que hacen Windows, macOS y Linux por defecto) borra el índice, pero casi siempre deja los archivos ahí. Unformat USB lee lo que quedó y lo copia a tu computadora:

- **Reconstruye las carpetas** con sus nombres y lo que tenían dentro, también los archivos grandes guardados en trozos.
- **Te muestra lo que encuentra mientras busca**, y puedes rescatar una carpeta sin esperar a que termine.
- **Modo seguro**: primero copia el pendrive entero a tu computadora y trabaja sobre la copia. Si el pendrive está fallando, es lo recomendado.
- **Archivos sueltos**: los que estaban fuera de las carpetas también salen, con un nombre sacado de su contenido (el título de un documento, la fecha de una foto) y sin repetidos.
- **Nombres perdidos**: propone un nombre para las carpetas que lo perdieron y solo las renombra si tú lo apruebas. Se puede deshacer.
- **Solo fotos y videos**, cada uno en su carpeta, si es lo único que te importa.
- **Nunca escribe en el pendrive** ni deja guardar lo rescatado en él.

Funciona con pendrives y tarjetas en **exFAT** y **FAT32**.

## Descargar

- **Windows**: [UnformatUSB.exe](https://github.com/aluhxp/unformat-usb/releases/latest). Windows te pedirá permiso de administrador al abrirlo: sin él no se puede leer un pendrive completo.
- **Linux**: `pip install "unformat-usb[gui] @ git+https://github.com/aluhxp/unformat-usb"` y luego `unformat-usb`. Te pedirá tu contraseña para leer el pendrive.
- **macOS**: en preparación.

## Cuándo no se puede

Hay que decirlo claro: si el pendrive se formateó en **modo completo** (escribe ceros en todo), si se usó mucho después del formateo, o si es un **disco SSD/NVMe** (el sistema borra los bloques libres con TRIM), puede que no quede nada que recuperar. Unformat USB te lo dirá en lugar de prometer lo que no puede.

## Apoyar el proyecto

Unformat USB es gratis y lo va a seguir siendo. Si te ayudó, al terminar un rescate verás la opción de invitar un café. Es voluntario.

---

Para desarrolladores: ver el [README en inglés](README.md#for-developers). Licencia: [GPL-3.0-or-later](LICENSE).
