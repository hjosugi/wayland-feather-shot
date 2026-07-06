"""Pure image-format helpers (no GTK), shared by save.py and the tests."""

from __future__ import annotations

import os

# File extension -> GdkPixbuf format name (when they differ).
_EXT_TO_FORMAT = {"jpg": "jpeg", "jpeg": "jpeg", "tif": "tiff"}
# Formats we offer beyond PNG when the GdkPixbuf build can write them.
_OPTIONAL_FORMATS = {"jpeg", "webp", "avif", "tiff", "bmp"}


def format_for_path(path: str, writable):
    """Decide the encoder for *path* from its extension.

    Pure and side-effect free (pass the set of writable GdkPixbuf format
    names).  Returns ``(format_name, final_path, options)`` where *options* is
    a list of ``(key, value)`` encoder settings.  Unknown or unwritable
    extensions fall back to PNG (with the extension appended when needed).
    """
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    name = _EXT_TO_FORMAT.get(ext, ext)
    if name == "jpeg" and "jpeg" in writable:
        return ("jpeg", path, [("quality", "92")])
    if name in _OPTIONAL_FORMATS and name in writable:
        opts = [("quality", "92")] if name in ("webp", "avif") else []
        return (name, path, opts)
    if ext != "png":
        path = path + ".png"
    return ("png", path, [])


def writable_image_extensions(writable):
    """Save-dialog extensions available given the *writable* format names."""
    exts = ["png"]
    for name in ("jpeg", "webp", "avif", "tiff", "bmp"):
        if name in writable:
            exts.append("jpg" if name == "jpeg" else name)
    return exts
