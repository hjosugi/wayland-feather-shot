# Packaging

Distribution packaging for wayland-feather-shot. Every format keeps the
project's core promise: **no network permission, no telemetry, local only.**

## Flatpak

`flatpak/io.github.hjosugi.WaylandFeatherShot.yaml` builds against the GNOME
runtime (which already provides GTK 4, PyGObject and pycairo) and installs the
package with pip `--no-deps --no-build-isolation`, so the build is offline and
reproducible. The manifest grants Wayland, IPC, DRI and `xdg-pictures` only —
**no `--share=network`**. Screenshot / ScreenCast / GlobalShortcuts reach the
portals that Flatpak exposes by default.

```console
$ flatpak-builder --user --install --force-clean build-dir \
    packaging/flatpak/io.github.hjosugi.WaylandFeatherShot.yaml
$ flatpak run io.github.hjosugi.WaylandFeatherShot
```

## AUR

`aur/PKGBUILD` builds a wheel and installs it plus the desktop entry, icon,
AppStream metainfo and autostart file. Replace `sha256sums=('SKIP')` with the
real checksum of the release tarball before publishing.

```console
$ cd packaging/aur && makepkg -si
```

## AppStream metainfo

`../data/io.github.hjosugi.WaylandFeatherShot.metainfo.xml` is shared by all
packaging formats and shown in software centres. Validate it with:

```console
$ appstreamcli validate data/io.github.hjosugi.WaylandFeatherShot.metainfo.xml
```

## deb / rpm

Not yet provided. The pip/`pyproject.toml` install and the `install.sh` script
cover source installs in the meantime.
