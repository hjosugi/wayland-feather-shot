#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -gt 1 ]; then
    echo "usage: $0 [vX.Y.Z]" >&2
    exit 2
fi

TAG="${1:-}"
if [ -z "$TAG" ]; then
    VERSION="$(python3 - <<'PY'
import tomllib
with open("pyproject.toml", "rb") as fh:
    print(tomllib.load(fh)["project"]["version"])
PY
)"
    TAG="v$VERSION"
else
    VERSION="${TAG#v}"
fi

if [ "$TAG" = "$VERSION" ] || [ -z "$VERSION" ]; then
    echo "release tag must look like vX.Y.Z" >&2
    exit 2
fi

PYPROJECT_VERSION="$(python3 - <<'PY'
import tomllib
with open("pyproject.toml", "rb") as fh:
    print(tomllib.load(fh)["project"]["version"])
PY
)"
PACKAGE_VERSION="$(python3 - <<'PY'
import ast
with open("src/wayland_feather_shot/__init__.py", "r", encoding="utf-8") as fh:
    module = ast.parse(fh.read())
for node in module.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__version__":
                print(ast.literal_eval(node.value))
                raise SystemExit
raise SystemExit("__version__ not found")
PY
)"

if [ "$PYPROJECT_VERSION" != "$VERSION" ] || [ "$PACKAGE_VERSION" != "$VERSION" ]; then
    echo "version mismatch: tag=$VERSION pyproject=$PYPROJECT_VERSION package=$PACKAGE_VERSION" >&2
    exit 1
fi

if ! git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
    echo "tag $TAG is required before building release assets" >&2
    exit 1
fi

ASSET_DIR="dist/release-$TAG"
APPDIR="$(mktemp -d)/WaylandFeatherShot.AppDir"
TOOL_DIR="${TMPDIR:-/tmp}/wayland-feather-shot-release-tools"
mkdir -p "$ASSET_DIR" "$TOOL_DIR"
rm -rf build src/*.egg-info "$ASSET_DIR"
mkdir -p "$ASSET_DIR"

python3 -m build --sdist --wheel --outdir "$ASSET_DIR"

mkdir -p \
    "$APPDIR/usr/bin" \
    "$APPDIR/usr/src" \
    "$APPDIR/usr/share/applications" \
    "$APPDIR/usr/share/metainfo" \
    "$APPDIR/usr/share/icons/hicolor/scalable/apps" \
    "$APPDIR/usr/share/doc/wayland-feather-shot"
cp -R src/wayland_feather_shot "$APPDIR/usr/src/"
cp bin/wayland-feather-shot "$APPDIR/usr/bin/wayland-feather-shot"
chmod +x "$APPDIR/usr/bin/wayland-feather-shot"
cp packaging/appimage/AppRun "$APPDIR/AppRun"
chmod +x "$APPDIR/AppRun"
cp data/io.github.hjosugi.WaylandFeatherShot.desktop "$APPDIR/io.github.hjosugi.WaylandFeatherShot.desktop"
cp data/io.github.hjosugi.WaylandFeatherShot.desktop \
    "$APPDIR/usr/share/applications/io.github.hjosugi.WaylandFeatherShot.desktop"
cp data/io.github.hjosugi.WaylandFeatherShot.metainfo.xml \
    "$APPDIR/usr/share/metainfo/io.github.hjosugi.WaylandFeatherShot.metainfo.xml"
cp data/io.github.hjosugi.WaylandFeatherShot.metainfo.xml \
    "$APPDIR/usr/share/metainfo/io.github.hjosugi.WaylandFeatherShot.appdata.xml"
cp data/icons/io.github.hjosugi.WaylandFeatherShot.svg "$APPDIR/io.github.hjosugi.WaylandFeatherShot.svg"
cp data/icons/io.github.hjosugi.WaylandFeatherShot.svg \
    "$APPDIR/usr/share/icons/hicolor/scalable/apps/io.github.hjosugi.WaylandFeatherShot.svg"
cp README.md CHANGELOG.md LICENSE "$APPDIR/usr/share/doc/wayland-feather-shot/"
ln -s io.github.hjosugi.WaylandFeatherShot.svg "$APPDIR/.DirIcon"

APPIMAGETOOL="$TOOL_DIR/appimagetool-x86_64.AppImage"
if ! [ -x "$APPIMAGETOOL" ]; then
    curl -L --fail --retry 3 \
        -o "$APPIMAGETOOL" \
        https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x "$APPIMAGETOOL"
fi

ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGETOOL" \
    "$APPDIR" \
    "$ASSET_DIR/wayland-feather-shot-$VERSION-x86_64.AppImage"
chmod +x "$ASSET_DIR/wayland-feather-shot-$VERSION-x86_64.AppImage"
"$ASSET_DIR/wayland-feather-shot-$VERSION-x86_64.AppImage" --appimage-extract-and-run --version

GITHUB_TARBALL="$TOOL_DIR/wayland-feather-shot-$TAG.github.tar.gz"
curl -L --fail --retry 5 \
    --retry-all-errors --retry-delay 2 \
    -o "$GITHUB_TARBALL" \
    "https://github.com/hjosugi/wayland-feather-shot/archive/refs/tags/$TAG.tar.gz"
GITHUB_TARBALL_SHA="$(sha256sum "$GITHUB_TARBALL" | awk '{print $1}')"

AUR_DIR="$(mktemp -d)/wayland-feather-shot"
mkdir -p "$AUR_DIR"
sed \
    -e "s/^pkgver=.*/pkgver=$VERSION/" \
    -e "s/^sha256sums=.*/sha256sums=('$GITHUB_TARBALL_SHA')/" \
    packaging/aur/PKGBUILD > "$AUR_DIR/PKGBUILD"
if command -v makepkg >/dev/null 2>&1; then
    (cd "$AUR_DIR" && makepkg --printsrcinfo > .SRCINFO)
else
    cat > "$AUR_DIR/.SRCINFO" <<EOF
pkgbase = wayland-feather-shot
	pkgdesc = Flameshot-style, local-only screenshot tool for Wayland (portal capture, annotation, scrolling capture)
	pkgver = $VERSION
	pkgrel = 1
	url = https://github.com/hjosugi/wayland-feather-shot
	arch = any
	license = MIT
	makedepends = python-build
	makedepends = python-installer
	makedepends = python-wheel
	makedepends = python-setuptools
	depends = python
	depends = python-gobject
	depends = gtk4
	depends = python-cairo
	optdepends = wl-clipboard: clipboard copy survives after the app closes
	optdepends = gst-plugin-pipewire: scrolling capture
	optdepends = gst-plugins-base: scrolling capture
	optdepends = python-numpy: faster scroll stitching
	source = wayland-feather-shot-$VERSION.tar.gz::https://github.com/hjosugi/wayland-feather-shot/archive/refs/tags/v$VERSION.tar.gz
	sha256sums = $GITHUB_TARBALL_SHA

pkgname = wayland-feather-shot
EOF
fi
tar -C "$(dirname "$AUR_DIR")" -czf "$ASSET_DIR/wayland-feather-shot-$VERSION-aur.tar.gz" wayland-feather-shot

(
    cd "$ASSET_DIR"
    rm -f SHA256SUMS
    sha256sum \
        "wayland-feather-shot-$VERSION-x86_64.AppImage" \
        "wayland_feather_shot-$VERSION-py3-none-any.whl" \
        "wayland_feather_shot-$VERSION.tar.gz" \
        "wayland-feather-shot-$VERSION-aur.tar.gz" > SHA256SUMS
)

ls -lh "$ASSET_DIR"
