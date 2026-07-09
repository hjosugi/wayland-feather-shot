#!/usr/bin/env bash
set -euo pipefail

PKGNAME="wayland-feather-shot"
UPSTREAM_URL="${UPSTREAM_URL:-https://github.com/hjosugi/wayland-feather-shot}"
AUR_REMOTE="${AUR_REMOTE:-ssh://aur@aur.archlinux.org/$PKGNAME.git}"

usage() {
    cat <<EOF
usage: $0 [--push] [--aur-dir DIR] [--export-dir DIR] [--remote URL] [vX.Y.Z]

Prepare the AUR package for an existing release tag. By default this writes a
local AUR checkout under dist/aur-vX.Y.Z and commits the update there. Add
--push to publish that commit to aur.archlinux.org.

Use --export-dir to only write PKGBUILD and .SRCINFO without cloning or
committing to the AUR git repository.

Environment:
  UPSTREAM_URL  GitHub project URL used for the source tarball
  AUR_REMOTE    AUR git remote (default: ssh://aur@aur.archlinux.org/$PKGNAME.git)
EOF
}

push=0
aur_dir=""
export_dir=""
tag=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --push)
            push=1
            ;;
        --aur-dir)
            if [ "$#" -lt 2 ]; then
                echo "--aur-dir requires a directory" >&2
                exit 2
            fi
            aur_dir="$2"
            shift
            ;;
        --export-dir)
            if [ "$#" -lt 2 ]; then
                echo "--export-dir requires a directory" >&2
                exit 2
            fi
            export_dir="$2"
            shift
            ;;
        --remote)
            if [ "$#" -lt 2 ]; then
                echo "--remote requires a git URL" >&2
                exit 2
            fi
            AUR_REMOTE="$2"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        -*)
            echo "unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
        *)
            if [ -n "$tag" ]; then
                echo "only one tag may be supplied" >&2
                exit 2
            fi
            tag="$1"
            ;;
    esac
    shift
done

pyproject_version="$(
    python3 - <<'PY'
import tomllib
with open("pyproject.toml", "rb") as fh:
    print(tomllib.load(fh)["project"]["version"])
PY
)"

if [ -z "$tag" ]; then
    tag="v$pyproject_version"
fi

version="${tag#v}"
if [ "$tag" = "$version" ] || [ -z "$version" ]; then
    echo "release tag must look like vX.Y.Z" >&2
    exit 2
fi

package_version="$(
    python3 - <<'PY'
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

if [ "$pyproject_version" != "$version" ] || [ "$package_version" != "$version" ]; then
    echo "version mismatch: tag=$version pyproject=$pyproject_version package=$package_version" >&2
    exit 1
fi

if ! git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
    echo "tag $tag is required before publishing the AUR package" >&2
    exit 1
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
repo_root="$(pwd)"

tarball="$tmp_dir/$PKGNAME-$tag.github.tar.gz"
curl -L --fail --retry 5 --retry-all-errors --retry-delay 2 \
    -o "$tarball" \
    "$UPSTREAM_URL/archive/refs/tags/$tag.tar.gz"
tarball_sha="$(sha256sum "$tarball" | awk '{print $1}')"

write_aur_files() {
    output_dir="$1"
    mkdir -p "$output_dir"

    sed \
        -e "s/^pkgver=.*/pkgver=$version/" \
        -e "s/^sha256sums=.*/sha256sums=('$tarball_sha')/" \
        "$repo_root/packaging/aur/PKGBUILD" > "$output_dir/PKGBUILD"

    if command -v makepkg >/dev/null 2>&1; then
        (cd "$output_dir" && makepkg --printsrcinfo > .SRCINFO)
    else
        cat > "$output_dir/.SRCINFO" <<EOF
pkgbase = $PKGNAME
	pkgdesc = Flameshot-style, local-only screenshot tool for Wayland (portal capture, annotation, scrolling capture)
	pkgver = $version
	pkgrel = 1
	url = $UPSTREAM_URL
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
	source = $PKGNAME-$version.tar.gz::$UPSTREAM_URL/archive/refs/tags/v$version.tar.gz
	sha256sums = $tarball_sha

pkgname = $PKGNAME
EOF
    fi
}

if [ -n "$export_dir" ]; then
    write_aur_files "$export_dir"
    echo "Exported AUR files to $export_dir"
    exit 0
fi

if [ -z "$aur_dir" ]; then
    aur_dir="dist/aur-$tag"
fi

if [ -e "$aur_dir" ] && [ ! -d "$aur_dir/.git" ]; then
    echo "$aur_dir exists but is not a git checkout" >&2
    exit 1
fi

if [ ! -d "$aur_dir/.git" ]; then
    mkdir -p "$(dirname "$aur_dir")"
    git clone "$AUR_REMOTE" "$aur_dir"
fi

cd "$aur_dir"

if [ -n "$(git status --porcelain)" ]; then
    echo "$aur_dir has uncommitted changes; commit or clean them first" >&2
    exit 1
fi

if git rev-parse -q --verify HEAD >/dev/null; then
    git pull --ff-only
fi

write_aur_files "."

git add PKGBUILD .SRCINFO

if git diff --cached --quiet; then
    echo "AUR package is already up to date for $tag"
    exit 0
fi

if ! git config user.name >/dev/null; then
    git config user.name "wayland-feather-shot release"
fi
if ! git config user.email >/dev/null; then
    git config user.email "aur-publisher@users.noreply.github.com"
fi

git commit -m "Update to $version"

if [ "$push" -eq 1 ]; then
    git push origin HEAD:master
else
    echo "Prepared AUR commit in $aur_dir"
    echo "Review it, then run: git -C '$aur_dir' push origin HEAD:master"
fi
