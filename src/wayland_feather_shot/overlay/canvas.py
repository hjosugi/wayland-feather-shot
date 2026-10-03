"""Retained image layers for the screenshot selection overlay."""

import sys

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk  # noqa: E402


def rect(x, y, width, height):
    bounds = Graphene.Rect()
    bounds.init(x, y, width, height)
    return bounds


def color(r, g, b, a=1):
    rgba = Gdk.RGBA()
    rgba.red, rgba.green, rgba.blue, rgba.alpha = r, g, b, a
    return rgba


def dim_outside(snapshot, width, height, selection, alpha):
    """Darken the viewport outside the selection with continuous coverage."""
    shade = color(0, 0, 0, alpha)
    if selection is None:
        snapshot.append_color(shade, rect(0, 0, width, height))
        return
    x0, y0, x1, y1 = selection
    x0, x1 = max(0, min(x0, width)), max(0, min(x1, width))
    y0, y1 = max(0, min(y0, height)), max(0, min(y1, height))
    widths = [y0, width - x1, height - y1, x0]
    if any(widths):
        # Independent strips leave antialiased seams at fractional edges.
        outline = Gsk.RoundedRect()
        outline.init_from_rect(rect(0, 0, width, height), 0)
        snapshot.append_border(outline, widths, [shade] * 4)


class OverlayScene:
    """Keep the screenshot and completed annotations out of per-frame Cairo."""

    def __init__(self, pixbuf):
        self.pixbuf = pixbuf
        fmt = (Gdk.MemoryFormat.R8G8B8A8 if pixbuf.get_has_alpha()
               else Gdk.MemoryFormat.R8G8B8)
        # read_pixel_bytes shares the pixbuf's own buffer; get_pixels plus
        # GLib.Bytes.new copied a 4K screenshot twice (about 40 ms) on the way
        # to the first frame. Nothing writes into the screenshot afterwards.
        self.background = Gdk.MemoryTexture.new(
            pixbuf.get_width(), pixbuf.get_height(), fmt,
            pixbuf.read_pixel_bytes(), pixbuf.get_rowstride())
        self._shapes = ()
        self._content = self.background

    def content(self, shapes):
        """Composite immutable shapes only when their history changes.

        Render onto the screenshot so Cairo's text antialiasing retains the
        same backdrop as direct drawing, rather than a transparent layer.
        """
        shapes = tuple(shapes)
        if shapes == self._shapes:
            return self._content
        texture = self.background
        if shapes:
            w, h = self.pixbuf.get_width(), self.pixbuf.get_height()
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
            cr = cairo.Context(surface)
            cr.set_source_rgb(0, 0, 0)
            cr.paint()
            Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, 0, 0)
            cr.paint()
            for shape in shapes:
                shape.draw(cr, self.pixbuf)
            surface.flush()
            fmt = (Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED
                   if sys.byteorder == 'little'
                   else Gdk.MemoryFormat.A8R8G8B8_PREMULTIPLIED)
            texture = Gdk.MemoryTexture.new(
                w, h, fmt, GLib.Bytes.new(bytes(surface.get_data())),
                surface.get_stride())
        self._shapes, self._content = shapes, texture
        return texture


class OverlayCanvas(Gtk.Widget):
    """A plain widget whose snapshot is drawn by a callback (draw.py), so
    the window's gesture controllers can be attached to it directly."""

    def __init__(self, snapshot_func, on_resize=None):
        super().__init__(hexpand=True, vexpand=True)
        self._snapshot_func = snapshot_func
        self._on_resize = on_resize
        self._size = (0, 0)

    def do_size_allocate(self, width, height, baseline):
        # Tell the window after the allocation, not during it: it moves
        # the bars, which are siblings being allocated in the same pass.
        if self._on_resize is not None and (width, height) != self._size:
            self._size = (width, height)
            GLib.idle_add(lambda: (self._on_resize(width, height), False)[1])

    def do_snapshot(self, snapshot):
        self._snapshot_func(self, snapshot,
                            self.get_width(), self.get_height())
