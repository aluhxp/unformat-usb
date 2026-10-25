"""Words the program writes to disk (folder names, the report), per language.
The window and the command line share them; the screens themselves are
translated with Qt (see tools/i18n.py)."""

from .core.model import Names

LANGUAGES = ("en", "es", "pt")
# each language in its own words, for the menu
LANGUAGE_NAMES = {"en": "English", "es": "Español", "pt": "Português"}
DEFAULT = "en"

TEXTS = {
    "en": dict(
        names=Names(unnamed_folder="Unnamed folder {}", lost_parent="Loose folders",
                    orphan_dir="Files without a folder", orphan_file="file_{}",
                    photo_label="photo {}", link_label="link {}", text_pieces="Pieces of text"),
        kinds={"photos": "Photos", "videos": "Videos", "music": "Music", "documents": "Documents",
               "spreadsheets": "Spreadsheets", "presentations": "Presentations",
               "programs": "Programs", "disk_images": "Disk images", "archives": "Archives",
               "code": "Code", "books": "Books", "fonts": "Fonts", "mixed": "Various"},
        report="_recovery_report.csv",
        names_log="_name_changes.json",
        copy="Copy of {}.img",
        columns=["path", "size_bytes", "date", "state", "method"],
        ok="ok",
        warnings={"no_data": "no data", "fragmented": "fragmented: may be damaged",
                  "maybe_fragmented": "maybe fragmented: check it", "incomplete": "incomplete",
                  "was_deleted": "had been deleted", "bad_sectors": "unreadable sectors",
                  "overwritten": "a newer file used its space: probably damaged"},
        methods={"contiguous": "contiguous", "fat_chain": "FAT chain",
                 "orphan_chain": "orphan FAT chain", "signature": "signature in a free cluster"},
        orphan_status={"verified": "ok (verified)", "pdf_valid": "ok (valid PDF structure)",
                       "png_complete": "ok (complete PNG)", "damaged": "damaged",
                       "chain_unverified": "full FAT chain: not verified",
                       "size_approx": "approximate size: not verified",
                       "text": "text without a folder: check it", "text_cut": "cut text: check it"},
        decimal=".",
        date="%Y-%m-%d",
        locale="en_US",
    ),
    "es": dict(
        names=Names(unnamed_folder="Carpeta sin nombre {}", lost_parent="Carpetas sueltas",
                    orphan_dir="Archivos sin carpeta", orphan_file="archivo_{}",
                    photo_label="foto {}", link_label="enlace {}", text_pieces="Trozos de texto"),
        kinds={"photos": "Fotos", "videos": "Videos", "music": "Música", "documents": "Documentos",
               "spreadsheets": "Hojas de cálculo", "presentations": "Presentaciones",
               "programs": "Programas", "disk_images": "Imágenes de disco", "archives": "Comprimidos",
               "code": "Código", "books": "Libros", "fonts": "Fuentes", "mixed": "Varios"},
        report="_informe_recuperacion.csv",
        names_log="_cambios_de_nombre.json",
        copy="Copia de {}.img",
        columns=["ruta", "tamano_bytes", "fecha", "estado", "metodo"],
        ok="ok",
        warnings={"no_data": "sin datos", "fragmented": "fragmentado: puede estar dañado",
                  "maybe_fragmented": "posible fragmentado: revisar", "incomplete": "incompleto",
                  "was_deleted": "estaba borrado", "bad_sectors": "sectores ilegibles",
                  "overwritten": "un archivo nuevo usó su espacio: probablemente dañado"},
        methods={"contiguous": "contiguo", "fat_chain": "cadena FAT",
                 "orphan_chain": "cadena FAT huérfana", "signature": "firma en clúster libre"},
        orphan_status={"verified": "ok (verificado)", "pdf_valid": "ok (estructura PDF válida)",
                       "png_complete": "ok (PNG completo)", "damaged": "dañado",
                       "chain_unverified": "cadena FAT completa: sin verificar",
                       "size_approx": "tamaño aproximado: sin verificar",
                       "text": "texto sin carpeta: revisar", "text_cut": "texto cortado: revisar"},
        decimal=",",
        date="%d/%m/%Y",
        locale="es_ES",
    ),
    "pt": dict(
        names=Names(unnamed_folder="Pasta sem nome {}", lost_parent="Pastas soltas",
                    orphan_dir="Arquivos sem pasta", orphan_file="arquivo_{}",
                    photo_label="foto {}", link_label="link {}", text_pieces="Pedaços de texto"),
        kinds={"photos": "Fotos", "videos": "Vídeos", "music": "Música", "documents": "Documentos",
               "spreadsheets": "Planilhas", "presentations": "Apresentações",
               "programs": "Programas", "disk_images": "Imagens de disco", "archives": "Compactados",
               "code": "Código", "books": "Livros", "fonts": "Fontes", "mixed": "Diversos"},
        report="_relatorio_recuperacao.csv",
        names_log="_mudancas_de_nome.json",
        copy="Cópia de {}.img",
        columns=["caminho", "tamanho_bytes", "data", "estado", "metodo"],
        ok="ok",
        warnings={"no_data": "sem dados", "fragmented": "fragmentado: pode estar danificado",
                  "maybe_fragmented": "talvez fragmentado: conferir", "incomplete": "incompleto",
                  "was_deleted": "estava apagado", "bad_sectors": "setores ilegíveis",
                  "overwritten": "um arquivo novo usou o espaço: provavelmente danificado"},
        methods={"contiguous": "contíguo", "fat_chain": "cadeia FAT",
                 "orphan_chain": "cadeia FAT órfã", "signature": "assinatura em cluster livre"},
        orphan_status={"verified": "ok (verificado)", "pdf_valid": "ok (estrutura PDF válida)",
                       "png_complete": "ok (PNG completo)", "damaged": "danificado",
                       "chain_unverified": "cadeia FAT completa: não verificado",
                       "size_approx": "tamanho aproximado: não verificado",
                       "text": "texto sem pasta: conferir", "text_cut": "texto cortado: conferir"},
        decimal=",",
        date="%d/%m/%Y",
        locale="pt_BR",
    ),
}


def texts(lang):
    return TEXTS.get(lang, TEXTS[DEFAULT])
