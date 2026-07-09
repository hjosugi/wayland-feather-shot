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
real checksum of the release tarball before publishing. The release asset
builder does this automatically in `wayland-feather-shot-$version-aur.tar.gz`.

```console
$ cd packaging/aur && makepkg -si
```

To publish or update the AUR package, create the GitHub release tag first, then
sync the AUR git repository:

```console
$ scripts/publish-aur.sh vX.Y.Z
$ git -C dist/aur-vX.Y.Z push origin HEAD:master
```

Use `scripts/publish-aur.sh vX.Y.Z --push` to commit and push in one command.
The script downloads the GitHub tag tarball, writes the real checksum, generates
`.SRCINFO`, and commits the AUR update. It requires an AUR account with SSH
access to `aur.archlinux.org`.

Without AUR SSH access on the current machine, export the files for inspection:

```console
$ scripts/publish-aur.sh vX.Y.Z --export-dir dist/aur-vX.Y.Z-files
```

The release workflow also publishes to AUR automatically when the repository
secret `AUR_SSH_PRIVATE_KEY` is set to a private SSH key whose public key is
registered on the maintainer's AUR account. If the secret is absent, the
workflow skips AUR publishing and still creates the GitHub release.

## AppImage

The AppImage is intentionally a host-runtime wrapper. It carries the app code,
desktop metadata and icon, but runs with `/usr/bin/python3` so GTK4,
PyGObject, pycairo, portals, GStreamer/PipeWire and other desktop integrations
come from the distro packages documented in the README.

Build all release assets from an existing tag:

```console
$ python3 -m pip install --user build installer wheel setuptools
$ scripts/build-release-assets.sh vX.Y.Z
```

This produces the AppImage, Python wheel, Python sdist, corrected AUR source
bundle and `SHA256SUMS` in `dist/release-vX.Y.Z/`.

## AppStream metainfo

`../data/io.github.hjosugi.WaylandFeatherShot.metainfo.xml` is shared by all
packaging formats and shown in software centres. Validate it with:

```console
$ appstreamcli validate data/io.github.hjosugi.WaylandFeatherShot.metainfo.xml
```

## deb / rpm

Not yet provided. The pip/`pyproject.toml` install and the `install.sh` script
cover source installs in the meantime.
