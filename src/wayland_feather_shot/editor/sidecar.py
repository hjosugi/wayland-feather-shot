"""The editable sidecar document.

A saved screenshot is flat pixels: once the arrows are drawn into it there is
no way back, so fixing a typo in a callout meant redoing the annotation from
scratch.  This writes the editable state next to the image as
``<image>.wfs.json`` so ``wayland-feather-shot edit x.png`` can pick the
annotations back up exactly where they were left.

The sidecar carries the **pristine base image** as well as the shapes.  The
saved PNG has the annotations burned in, so the untouched pixels have to live
somewhere; keeping them inside the sidecar means there is one extra file rather
than two, and the document cannot get separated from the image it describes.
A sidecar is only written when there is something to re-edit, so unannotated
screenshots stay one file.

Pure Python — no ``gi`` — so the format is unit-testable in CI.  The caller
turns ``base_png`` into a pixbuf.
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import json
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import crop as crop_mod
from . import shapes as S

SIDECAR_VERSION = 1
SIDECAR_SUFFIX = ".wfs.json"


class SidecarError(Exception):
    """The sidecar could not be read as an editable document."""


class UnsupportedVersion(SidecarError):
    """Written by a newer release than this one.

    Callers fall back to opening the flat image, which is always still
    correct — just not re-editable.
    """


@dataclasses.dataclass(frozen=True)
class Document:
    shapes: Tuple[S.Shape, ...]
    base_png: Optional[bytes]
    base_image: str = ""
    version: int = SIDECAR_VERSION
    # The edited region of the stored base, normalized.  Storing the crop as a
    # rect over the pristine image rather than cropped pixels is what lets a
    # reopened screenshot have its crop widened again.
    crop: Tuple[float, float, float, float] = crop_mod.UNIT


# -- paths -------------------------------------------------------------------

def sidecar_path(image_path: str) -> str:
    """The sidecar that belongs to *image_path*."""
    return image_path + SIDECAR_SUFFIX


def remove(image_path: str) -> bool:
    """Delete a stale sidecar.  Returns whether one was there."""
    try:
        os.unlink(sidecar_path(image_path))
        return True
    except OSError:
        return False


# -- shape codec -------------------------------------------------------------

_PROPS_BY_KIND = {
    cls.KIND: cls for cls in (
        S.PenProps, S.ArrowProps, S.GeoProps, S.HighlightProps,
        S.ObscureProps, S.TextProps, S.MarkerProps, S.BubbleProps,
        S.EmojiProps,
    )
}


def _encode_style(style: S.Style) -> Dict[str, Any]:
    return {
        "rgba": list(style.rgba),
        "width": style.width,
        "font_size": style.font_size,
        "font_family": style.font_family,
    }


def _decode_style(data: Any) -> S.Style:
    if not isinstance(data, dict):
        return S.Style()
    rgba = data.get("rgba")
    kwargs: Dict[str, Any] = {}
    if isinstance(rgba, (list, tuple)) and len(rgba) == 4:
        kwargs["rgba"] = tuple(float(c) for c in rgba)
    for key in ("width", "font_size"):
        if isinstance(data.get(key), (int, float)):
            kwargs[key] = float(data[key])
    if isinstance(data.get("font_family"), str):
        kwargs["font_family"] = data["font_family"]
    return S.Style(**kwargs)


def _encode_value(name: str, value: Any) -> Any:
    if name == "style":
        return _encode_style(value)
    if name == "points":
        return [[p[0], p[1]] for p in value]
    if name == "end":
        return [value[0], value[1]]
    return value


def _decode_value(name: str, value: Any) -> Any:
    if name == "style":
        return _decode_style(value)
    if name == "points":
        return tuple((float(p[0]), float(p[1])) for p in value
                     if isinstance(p, (list, tuple)) and len(p) >= 2)
    if name == "end":
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            return (float(value[0]), float(value[1]))
        raise SidecarError("arrow end is malformed")
    return value


def encode_shape(shape: S.Shape) -> Dict[str, Any]:
    props = {f.name: _encode_value(f.name, getattr(shape.props, f.name))
             for f in dataclasses.fields(shape.props)}
    return {
        "kind": shape.kind,
        "x": shape.x,
        "y": shape.y,
        "rotation": shape.rotation,
        "opacity": shape.opacity,
        "props": props,
    }


def decode_shape(data: Any) -> Optional[S.Shape]:
    """Rebuild one shape, or None for a kind this release does not know.

    Unknown keys are ignored and missing ones fall back to the payload's own
    defaults, so a document written by a newer minor release still opens with
    everything this build understands.
    """
    if not isinstance(data, dict):
        return None
    cls = _PROPS_BY_KIND.get(data.get("kind"))
    if cls is None:
        return None
    raw = data.get("props")
    if not isinstance(raw, dict):
        return None

    known = {f.name for f in dataclasses.fields(cls)}
    kwargs: Dict[str, Any] = {}
    for name, value in raw.items():
        if name in known:
            kwargs[name] = _decode_value(name, value)
    try:
        props = cls(**kwargs)
    except TypeError as exc:  # a required field the document did not carry
        raise SidecarError(f"{data.get('kind')} payload is incomplete") from exc

    return S.Shape(
        x=float(data.get("x", 0.0)),
        y=float(data.get("y", 0.0)),
        props=props,
        rotation=float(data.get("rotation", 0.0)),
        opacity=float(data.get("opacity", 1.0)),
    )


# -- document codec ----------------------------------------------------------

def encode(shapes: Sequence[S.Shape], base_png: Optional[bytes] = None,
           base_image: str = "",
           crop: Tuple[float, float, float, float] = crop_mod.UNIT) -> Dict[str, Any]:
    document: Dict[str, Any] = {
        "version": SIDECAR_VERSION,
        "generator": "wayland-feather-shot",
        "base_image": base_image,
        "crop": list(crop),
        "shapes": [encode_shape(s) for s in shapes],
    }
    if base_png:
        document["base"] = {
            "format": "png",
            "data": base64.b64encode(base_png).decode("ascii"),
        }
    return document


def decode(data: Any) -> Document:
    if not isinstance(data, dict):
        raise SidecarError("sidecar is not an object")
    version = data.get("version")
    if not isinstance(version, int):
        raise SidecarError("sidecar has no version")
    if version > SIDECAR_VERSION:
        raise UnsupportedVersion(
            f"sidecar version {version} is newer than {SIDECAR_VERSION}")

    raw_shapes = data.get("shapes")
    if not isinstance(raw_shapes, list):
        raise SidecarError("sidecar has no shapes")
    shapes: List[S.Shape] = []
    for entry in raw_shapes:
        shape = decode_shape(entry)
        if shape is not None:
            shapes.append(shape)

    base_png: Optional[bytes] = None
    base = data.get("base")
    if isinstance(base, dict) and base.get("format") == "png":
        try:
            base_png = base64.b64decode(base.get("data", ""), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise SidecarError("base image is not valid base64") from exc
        if not base_png:
            base_png = None

    return Document(
        shapes=tuple(shapes),
        base_png=base_png,
        base_image=str(data.get("base_image", "")),
        version=version,
        crop=_decode_crop(data.get("crop")),
    )


def _decode_crop(value: Any) -> Tuple[float, float, float, float]:
    """A stored crop rect, falling back to the whole image.

    A nonsense rect degrades to the full image rather than raising: losing the
    crop is recoverable, losing the annotations with it is not.
    """
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return crop_mod.UNIT
    try:
        x, y, w, h = (float(v) for v in value)
    except (TypeError, ValueError):
        return crop_mod.UNIT
    if not (w > 0 and h > 0) or x < 0 or y < 0 or x + w > 1.001 or y + h > 1.001:
        return crop_mod.UNIT
    return (x, y, w, h)


# -- files -------------------------------------------------------------------

def save(image_path: str, shapes: Sequence[S.Shape],
         base_png: Optional[bytes] = None,
         crop: Tuple[float, float, float, float] = crop_mod.UNIT) -> str:
    """Write the sidecar for *image_path* and return its path.

    Written through a temporary file in the same directory and renamed, so a
    crash mid-write cannot leave a half-written document where a readable one
    used to be.
    """
    path = sidecar_path(image_path)
    document = encode(shapes, base_png,
                      base_image=os.path.basename(image_path), crop=crop)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as fh:
        json.dump(document, fh, ensure_ascii=False)
    os.replace(temporary, path)
    return path


def load(image_path: str) -> Optional[Document]:
    """Read the sidecar for *image_path*.

    Returns None when there is not one, and raises :class:`SidecarError` when
    there is one but it cannot be used — the caller opens the flat image in
    both cases, but only the second is worth telling the user about.
    """
    path = sidecar_path(image_path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SidecarError(str(exc)) from exc
    except ValueError as exc:
        raise SidecarError("sidecar is not valid JSON") from exc
    return decode(data)
