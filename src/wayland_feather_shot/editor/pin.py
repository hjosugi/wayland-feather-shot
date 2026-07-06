"""Pin-to-screen: a frameless, draggable window that floats a capture.

Flameshot's "pin" keeps a capture on screen above other windows. On Wayland
always-on-top is not universally available to regular clients — stacking is
the compositor's call — so this is a plain frameless window the compositor
places; that already covers the common "keep this visible while I work" use.

Drag the image to move it (Gtk.WindowHandle), Esc or middle-click closes,
Ctrl+C copies it again.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from .. import save as save_mod

MAX_W, MAX_H = 1000, 800


class PinWindow(Gtk.ApplicationWindow):
    def __init__(self, app, pixbuf):
        super().__init__(application=app)
        self.pixbuf = pixbuf
        self.set_decorated(False)
        self.set_resizable(False)
        app.hold()
        self.connect("destroy", lambda *_: app.release())

        handle = Gtk.WindowHandle()  # dragging anywhere moves the window
        picture = Gtk.Picture.new_for_pixbuf(pixbuf)
        picture.set_can_shrink(True)
        picture.add_css_class("wfs-pin")
        handle.set_child(picture)
        self.set_child(handle)
        self._install_css()

        iw, ih = pixbuf.get_width(), pixbuf.get_height()
        scale = min(1.0, MAX_W / max(1, iw), MAX_H / max(1, ih))
        self.set_default_size(max(1, int(iw * scale)), max(1, int(ih * scale)))

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

        middle = Gtk.GestureClick()
        middle.set_button(2)  # middle-click dismisses
        middle.connect("pressed", lambda *_: self.close())
        handle.add_controller(middle)

    def _install_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(b".wfs-pin { border: 1px solid "
                                b"rgba(0,0,0,0.5); }")
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _on_key(self, _ctrl, keyval, _keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        if (state & Gdk.ModifierType.CONTROL_MASK
                and Gdk.keyval_to_lower(keyval) == Gdk.KEY_c):
            try:
                save_mod.copy_pixbuf(self.pixbuf)
            except Exception:
                pass
            return True
        return False
