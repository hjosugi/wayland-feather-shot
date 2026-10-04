"""The background frame on the region overlay.

The result can sit on a stage: a solid, gradient or image fill around it,
rounded corners, a shadow, a border, a watermark (editor/background.py has
the model, editor/render.py draws it). The screen shows the selection as
captured, so the frame's page in the "…" menu has its own preview, and the
size label shows the framed size. Copy, save and pin take the framed
result; OCR reads the selection without it. A mixin of
overlay.window.OverlayWindow.
"""

from __future__ import annotations

from dataclasses import replace

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from ..editor import background as bg
from ..editor import render
from ..util.i18n import _

# The preview is rendered from the selection shrunk to this longer edge; the
# frame's sizes are fractions of the picture, so it scales as a whole.
PREVIEW_EDGE = 360


class OverlayFrameMixin:
    """``background`` holds the frame (none until one is picked)."""

    def _build_frame_page(self, back):
        """The frame's controls and preview; *back* returns to the menu.

        Two columns of controls, in a scrolled box: the page has to fit
        beside the "…" button wherever the selection put it, and a popover
        that cannot be placed is not shown at all.
        """
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        back_button = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        back_button.add_css_class("wfs-menu-item")
        back_button.set_tooltip_text(_("Back"))
        back_button.connect("clicked", lambda *_: back())
        header.append(back_button)
        title = Gtk.Label(label=_("Background & framing"), xalign=0)
        title.add_css_class("heading")
        header.append(title)
        page.append(header)

        self._frame_picture = Gtk.Picture()
        self._frame_picture.set_size_request(260, 140)
        self._frame_picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self._frame_picture.set_can_shrink(True)
        page.append(self._frame_picture)

        grid = Gtk.Grid(row_spacing=6, column_spacing=8)
        self._frame_widgets = widgets = {}
        self._frame_cells = cells = {}

        def put(key, label, widget, row, column):
            caption = Gtk.Label(label=label, xalign=0)
            caption.add_css_class("wfs-caption")
            widget.set_hexpand(True)
            grid.attach(caption, column * 2, row, 1, 1)
            grid.attach(widget, column * 2 + 1, row, 1, 1)
            widgets[key] = widget
            cells[key] = (caption, widget)

        def scale(low, high, step, value):
            widget = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,
                                              low, high, step)
            widget.set_value(value)
            widget.set_draw_value(False)
            widget.set_size_request(110, -1)
            widget.connect("value-changed", self._on_frame_changed)
            return widget

        def dropdown(names, selected):
            widget = Gtk.DropDown.new_from_strings(names)
            widget.set_selected(selected)
            widget.connect("notify::selected", self._on_frame_changed)
            return widget

        settings = self.background
        put("fill", _("Background"), dropdown(
            [_("None"), _("Solid"), _("Gradient"), _("Image…")],
            bg.FILLS.index(settings.fill)), 0, 0)
        put("gradient", _("Gradient"), dropdown(
            [name.capitalize() for name in bg.GRADIENT_PRESETS],
            list(bg.GRADIENT_PRESETS).index(settings.gradient)), 0, 1)
        put("padding", _("Padding"),
            scale(0.0, 0.35, 0.01, settings.padding), 1, 0)
        put("corner_radius", _("Corners"),
            scale(0.0, 0.08, 0.002, settings.corner_radius), 1, 1)
        put("shadow", _("Shadow"),
            scale(0.0, 1.0, 0.05, settings.shadow), 2, 0)
        put("aspect", _("Aspect"), dropdown(
            [_("Auto") if name == "auto" else name for name in bg.ASPECTS],
            bg.ASPECTS.index(settings.aspect)), 2, 1)
        put("alignment", _("Align"), dropdown(
            [name.replace("-", " ").capitalize() for name in bg.ALIGNMENTS],
            bg.ALIGNMENTS.index(settings.alignment)), 3, 0)
        watermark = Gtk.Entry()
        watermark.set_placeholder_text(_("Watermark text"))
        watermark.set_text(settings.watermark.text)
        watermark.connect("changed", self._on_frame_changed)
        put("watermark", _("Watermark"), watermark, 4, 0)
        tile = scale(0, 6, 1, settings.watermark.density)
        tile.set_tooltip_text(
            _("0 places one mark in the corner; higher tiles it"))
        put("tile", _("Repeat"), tile, 4, 1)

        border = Gtk.CheckButton(label=_("Border around the screenshot"))
        border.set_active(settings.border.enabled)
        border.connect("toggled", self._on_frame_changed)
        grid.attach(border, 2, 3, 2, 1)
        widgets["border"] = border

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_propagate_natural_width(True)
        scroller.set_propagate_natural_height(True)
        scroller.set_child(grid)
        page.append(scroller)
        self._show_frame_cells()
        return page

    def _show_frame_cells(self):
        """Hide what the frame does not use: the gradient without a
        gradient fill, the repeat without a watermark."""
        cells, widgets = self._frame_cells, self._frame_widgets
        shown = {
            "gradient": bg.FILLS[widgets["fill"].get_selected()]
            == "gradient",
            "tile": bool(widgets["watermark"].get_text().strip()),
        }
        for key, visible in shown.items():
            for widget in cells[key]:
                widget.set_visible(visible)

    def _on_frame_changed(self, *_args):
        """Read the controls into ``background`` and show the result."""
        widgets = self._frame_widgets
        fill = bg.FILLS[widgets["fill"].get_selected()]
        if fill == "image" and not self.background.image_path:
            self._choose_frame_image()
            return
        text = widgets["watermark"].get_text()
        self.background = replace(
            self.background,
            fill=fill,
            gradient=list(bg.GRADIENT_PRESETS)[
                widgets["gradient"].get_selected()],
            padding=widgets["padding"].get_value(),
            corner_radius=widgets["corner_radius"].get_value(),
            shadow=widgets["shadow"].get_value(),
            aspect=bg.ASPECTS[widgets["aspect"].get_selected()],
            alignment=bg.ALIGNMENTS[widgets["alignment"].get_selected()],
            border=bg.Border(enabled=widgets["border"].get_active()),
            watermark=bg.Watermark(enabled=bool(text.strip()), text=text,
                                   density=widgets["tile"].get_value()),
        )
        self._show_frame_cells()
        self._refresh_frame_preview()
        self._redraw()                  # the size label shows the frame

    def _choose_frame_image(self):
        """Pick the image to fill the background with."""
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Choose a background image"))

        def chosen(dlg, result):
            try:
                gfile = dlg.open_finish(result)
            except GLib.Error:
                # Cancelled: back to whatever fill was there before.
                self._frame_widgets["fill"].set_selected(
                    bg.FILLS.index(self.background.fill))
                return
            self.background = replace(self.background,
                                      image_path=gfile.get_path())
            self._on_frame_changed()

        dialog.open(self._view.window, None, chosen)

    def _refresh_frame_preview(self):
        """Render the framed selection, small, into the frame page."""
        picture = getattr(self, "_frame_picture", None)
        if picture is None or self.sel is None:
            return
        # The shrunk selection is kept while it stays the same: sliding a
        # control re-renders only the small frame.
        key = (self.sel, tuple(self.shapes))
        if self._frame_base is None or self._frame_base[0] != key:
            base = self._export_cropped()
            longest = max(base.get_width(), base.get_height())
            if longest > PREVIEW_EDGE:
                k = PREVIEW_EDGE / longest
                base = base.scale_simple(
                    max(1, round(base.get_width() * k)),
                    max(1, round(base.get_height() * k)),
                    GdkPixbuf.InterpType.BILINEAR)
            self._frame_base = (key, base)
        framed = render.flatten(self._frame_base[1], [], self.background)
        picture.set_paintable(Gdk.Texture.new_for_pixbuf(framed))

    def _framed_size(self):
        """The size of the framed result, or None without a frame."""
        if self.sel is None or not self.background.enabled:
            return None
        layout = bg.layout((float(self.sel[2]), float(self.sel[3])),
                           self.background)
        return (max(1, round(layout.canvas[0])),
                max(1, round(layout.canvas[1])))

    def _export_result(self) -> GdkPixbuf.Pixbuf:
        """What copy, save and pin hand out: the selection with its
        annotations, on its frame if there is one."""
        image = self._export_cropped()
        if not self.background.enabled:
            return image
        return render.flatten(image, [], self.background)
