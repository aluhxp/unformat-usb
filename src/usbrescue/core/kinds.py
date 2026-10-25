"""What sort of file a name is, by its extension."""

KINDS = {
    "photos": ("jpg", "jpeg", "png", "heic", "heif", "gif", "bmp", "webp", "tif", "tiff", "raw",
               "cr2", "cr3", "nef", "arw", "dng", "orf", "rw2"),
    "videos": ("mp4", "mkv", "avi", "mov", "wmv", "3gp", "mpg", "mpeg", "m4v", "webm", "flv", "vob",
               "mts", "m2ts"),
    "music": ("mp3", "wav", "flac", "m4a", "ogg", "wma", "aac", "opus", "mid", "midi", "amr"),
    "documents": ("doc", "docx", "odt", "pdf", "rtf", "txt", "md", "pages"),
    "spreadsheets": ("xls", "xlsx", "xlsm", "ods", "csv", "numbers"),
    "presentations": ("ppt", "pptx", "pps", "ppsx", "odp", "key"),
    "programs": ("exe", "msi", "apk", "deb", "rpm", "dmg", "pkg", "appimage", "jar"),
    "disk_images": ("iso", "img", "vhd", "vhdx", "vmdk", "wim", "esd"),
    "archives": ("zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz"),
    "code": ("py", "java", "js", "ts", "c", "h", "cpp", "cs", "php", "html", "htm", "css", "sql",
             "kt", "go", "rb", "sh", "ipynb", "json", "xml"),
    "books": ("epub", "mobi", "azw", "azw3", "djvu", "cbr", "cbz"),
    "fonts": ("ttf", "otf", "woff", "woff2"),
}

# what "only photos and videos" keeps
MEDIA = frozenset(KINDS["photos"] + KINDS["videos"])


def is_media(name):
    return name.lower().rpartition(".")[2] in MEDIA
