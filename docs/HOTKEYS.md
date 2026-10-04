# Hotkeys

Two different things get called "shortcut" around a screenshot tool:

- **Global keys** such as Ctrl+PrtSc, which launch a capture from anywhere.
  On Wayland an application cannot grab a key by itself; the desktop decides.
- **In-app keys** that work while the region overlay or the editor is open.

This page covers both. `wayland-feather-shot diagnose` detects your desktop
and prints the exact commands for it.

## Global keys

Feather Shot ships two mechanisms; pick one per desktop.

| Mechanism | How it works | Best for |
| --- | --- | --- |
| Native binding | Your desktop's own keyboard settings run `wayland-feather-shot gui`. Nothing needs to stay running. | GNOME, Hyprland, Sway, anything |
| Portal daemon | `wayland-feather-shot daemon` registers the keys through the GlobalShortcuts portal and stays running. The desktop shows the binding in its own settings and may ask for approval once. | KDE Plasma, GNOME 46+ |

Default keys with either mechanism:

| Key | Action |
| --- | --- |
| Ctrl+PrtSc | full screen (`full`): the overlay with everything selected |
| Ctrl+Shift+PrtSc | region capture (`gui`) |

With Ctrl+PrtSc the whole screen starts out selected: annotate it, copy it
with Enter, or pull a handle in to cut a part out of it.

`wayland-feather-shot copy` selects a region and copies it straight to the
clipboard (releasing the drag is the whole job). It has no default key;
bind it by hand like the commands below if you want it.

Scrolling capture has no key: it is in the app's menu (right-click Feather
Shot in the dock or app grid, "Scrolling capture"), or run
`wayland-feather-shot scroll`.

### GNOME

**Native (recommended).** Run the helper once:

```console
$ ./scripts/setup-hotkey.sh
```

It adds two custom keybindings through `gsettings` (Settings → Keyboard →
Custom Shortcuts, named "Feather Shot (full screen)" and "Feather Shot
(region)") and is safe to rerun. The command
is the installed `wayland-feather-shot`, or this checkout's
`bin/wayland-feather-shot` when nothing is installed. To undo, delete the
entries in that settings page.

GNOME keeps Print, Shift+Print and Alt+Print for its own screenshot UI;
Ctrl+Print is free by default, which is why it is the default here.

**Portal daemon (GNOME 46 or newer).** The daemon needs two things:

1. It must be running. A package install adds an autostart entry
   (`io.github.hjosugi.WaylandFeatherShot.Daemon.desktop`) that starts it at
   login. From a git checkout, install the entries with
   `scripts/install-desktop-entry.sh --autostart`, then log out and in, or
   start it by hand once with `./bin/wayland-feather-shot daemon`.
2. The portal must know the app id. The hotkey daemon registers it at start-up
   through `org.freedesktop.host.portal.Registry` (xdg-desktop-portal 1.18 or
   newer), and the portal accepts that only when a desktop entry named
   `io.github.hjosugi.WaylandFeatherShot.desktop` exists in an applications
   directory it can see. Packages install it; `scripts/install-desktop-entry.sh`
   installs it for a checkout.

GNOME binds the keys without a dialog. They appear under Settings → Keyboard
→ Applications once the daemon has registered them.

### KDE Plasma

Plasma implements the GlobalShortcuts portal. Start the daemon (the autostart
entry does this at login), approve the shortcut dialog once, and the keys show
up under System Settings → Shortcuts → Feather Shot, where you can change them.
Alternatively add custom shortcuts by hand: `wayland-feather-shot full` on
Ctrl+PrtSc and `wayland-feather-shot gui` on Ctrl+Shift+PrtSc.

### Hyprland

```ini
# ~/.config/hypr/hyprland.conf
bind = CTRL, Print, exec, wayland-feather-shot full
bind = CTRL SHIFT, Print, exec, wayland-feather-shot gui
```

### Sway and other wlroots compositors

```
# ~/.config/sway/config
bindsym Ctrl+Print exec wayland-feather-shot full
bindsym Ctrl+Shift+Print exec wayland-feather-shot gui
```

`xdg-desktop-portal-wlr` does not implement the GlobalShortcuts portal, so the
daemon reports failure there; the native binding is the way.

### Other desktops

Bind `wayland-feather-shot full` and `gui` in your desktop's keyboard
settings. If the desktop implements the GlobalShortcuts portal,
`wayland-feather-shot daemon` works too.

### Changing the daemon's keys

The region key can be overridden on the command line, in the portal's
trigger syntax:

```console
$ wayland-feather-shot daemon --shortcut "CTRL+SHIFT+s"
```

For a permanent change, use the desktop's own shortcut settings once the
keys are registered, or edit the `Exec=` line of the autostart entry. The
settings window (`wayland-feather-shot settings`, or "Settings" in the app's
launcher menu) has a "Keyboard settings…" button that opens them: Settings →
Keyboard on GNOME, System Settings → Shortcuts on KDE Plasma. On Hyprland
and Sway, which keep the keys in their config file, it shows the lines to
add instead.

### Checking that it works

```console
$ wayland-feather-shot gui                 # the capture path itself
$ wayland-feather-shot diagnose            # portals, detected desktop, the binding for it
$ wayland-feather-shot daemon --bind-once  # portal path: register the keys, then exit
$ wayland-feather-shot daemon              # stay running and log every key press
```

In the foreground the daemon logs each activation and the exact command it
launches. The autostarted daemon logs to the journal:

```console
$ journalctl --user -b -g "feather-shot daemon"
```

### Troubleshooting

- **`could not bind shortcuts (... An app id is required)`** — the portal
  does not know which application is asking. Either the desktop entry named
  after the app id is missing (git checkout: run
  `scripts/install-desktop-entry.sh`; AppImage integrated under a different
  file name: install the entry from `data/` under its proper name), or
  xdg-desktop-portal is older than 1.18 and has no Registry. The native
  binding does not need any of this.
- **The daemon says "shortcuts bound" but the key does nothing** — make sure
  only one daemon is running, and look for `activated` lines in its log. On
  GNOME, check Settings → Keyboard → Applications for the binding, and that
  no custom shortcut uses the same key.
- **Ctrl+PrtSc opens the desktop's own screenshot tool** — the desktop has its
  own binding on that key; change or remove it in the keyboard settings.
- **Pressing the key again while a capture is open does nothing** — on
  purpose. One capture at a time; finish or close it first.
- **`gui` works but no key does** — the binding mechanism is the problem, not
  the capture. Re-read the section for your desktop above.

## In-app keys

### Region overlay (`gui`)

Before a region is selected:

| Key | Action |
| --- | --- |
| drag | select a region |
| click, Enter | select the whole screen and start editing |
| Esc | quit |

With a region selected:

| Key | Action |
| --- | --- |
| V | move the selection (the resize handles work with every tool) |
| S | hand: grab a placed shape and move it; Shift+click or Ctrl+click picks several, which then move together; the picked shapes' frame resizes and rotates them (Shift keeps the proportions or snaps the angle) |
| P, L, A, G | pen, line, arrow, numbered step arrow |
| R, E, H | rectangle, ellipse, highlighter |
| T, U | text, speech bubble (click, then type on the canvas: Enter is a newline, Ctrl+Enter finishes, Esc cancels); a click on a placed text or bubble, or a double-click on one with the hand, types into it again |
| M, J | numbered marker, emoji sticker (click to place) |
| B, X, O | blur, pixelate, spotlight (dims everything outside it) |
| [ , ] | smaller or larger line width, or text size while the text, bubble or emoji tool is active |
| Ctrl+A | pick every shape with the hand |
| Delete, Backspace | delete the picked shapes |
| arrows, Shift+arrows | nudge the picked shapes by 1 px, by 10 px |
| Ctrl+Up, Ctrl+Down | raise, lower the picked shapes |
| Enter, Ctrl+C, double-click inside the selection | copy to the clipboard and close |
| Ctrl+S | save and close |
| Ctrl+Shift+S | save as… |
| Ctrl+O | open the save folder |
| Ctrl+Z, Ctrl+Shift+Z or Ctrl+Y | undo, redo (annotations and selection changes alike) |
| Ctrl+wheel, touchpad pinch, Ctrl++, Ctrl+- | zoom in and out around the pointer |
| Ctrl+1, Ctrl+0 | zoom to the selection, back to the whole screen |
| wheel, Shift+wheel | pan while zoomed in |
| Esc | quit without saving |

### Editor (`edit`, the history, window and scrolling captures, scripted captures)

| Key | Tool |
| --- | --- |
| V | select / move a shape |
| P, L, A, G | pen, line, arrow, numbered step arrow |
| R, E, H, S | rectangle, ellipse, highlighter, spotlight |
| T, U, J | text, speech bubble, emoji sticker |
| B, X, M | blur, pixelate, numbered marker |
| C | crop (Enter applies, Esc cancels) |

| Key | Action |
| --- | --- |
| Ctrl+S | quick save |
| Ctrl+Shift+S | save as… |
| Ctrl+C | copy the image to the clipboard |
| Ctrl+Shift+C | copy the saved file's path |
| Ctrl+O | open the save folder |
| Ctrl+P | pin the image to the screen |
| Ctrl+Z, Ctrl+Shift+Z or Ctrl+Y | undo, redo |
| Ctrl+A | select all shapes |
| Ctrl++, Ctrl+- | zoom in, zoom out |
| Ctrl+1, Ctrl+0 | fit to window, 100 % |
| Ctrl+Up, Ctrl+Down | raise, lower the selected shape |
| arrows, Shift+arrows | nudge the selection by 1 px, by 10 px |
| Delete, Backspace | delete the selected shapes |
| Esc | close |
