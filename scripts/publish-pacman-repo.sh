#!/usr/bin/env bash
set -euo pipefail

PKGNAME="wayland-feather-shot"
REPO_NAME="$PKGNAME"
RELEASE_TAG="pacman-repo"
KEY_FILE="packaging/pacman/$PKGNAME.asc"

usage() {
    cat <<EOF
usage: $0 [--push] [--repo-dir DIR] [--sign-key KEYID] [vX.Y.Z]

Build the pacman package for an existing release tag and wrap it in a pacman
repository database. By default this writes the repository files to
dist/pacman-repo-vX.Y.Z. Add --push to upload them to the "$RELEASE_TAG" GitHub
release, which is where the Server line in pacman.conf points.

--sign-key names the GPG key that signs the package and the database. The
signatures must verify against $KEY_FILE, the key users
are told to trust, and --push refuses to publish an unsigned repository.

Environment:
  PACMAN_REPO_SIGN_KEY  default for --sign-key
  MAKEPKG_ARGS          extra makepkg arguments (e.g. --noconfirm)
  GH_REPO               GitHub repository to publish to (gh's default otherwise)
EOF
}

push=0
repo_dir=""
sign_key="${PACMAN_REPO_SIGN_KEY:-}"
tag=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --push)
            push=1
            ;;
        --repo-dir)
            if [ "$#" -lt 2 ]; then
                echo "--repo-dir requires a directory" >&2
                exit 2
            fi
            repo_dir="$2"
            shift
            ;;
        --sign-key)
            if [ "$#" -lt 2 ]; then
                echo "--sign-key requires a GPG key id" >&2
                exit 2
            fi
            sign_key="$2"
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

if [ -z "$tag" ]; then
    tag="v$(
        python3 - <<'PY'
import tomllib
with open("pyproject.toml", "rb") as fh:
    print(tomllib.load(fh)["project"]["version"])
PY
    )"
fi
version="${tag#v}"

if [ "$push" -eq 1 ] && [ -z "$sign_key" ]; then
    echo "--push requires --sign-key: the published repository must be signed" >&2
    exit 2
fi

for tool in makepkg repo-add; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "$tool not found; the pacman repository has to be built on Arch Linux" >&2
        exit 1
    fi
done

if [ -z "$repo_dir" ]; then
    repo_dir="dist/pacman-repo-$tag"
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

# publish-aur.sh checks the tag and the versions, and writes the PKGBUILD with
# the real checksum of the tag tarball.
scripts/publish-aur.sh "$tag" --export-dir "$tmp_dir/build"

mkdir -p "$repo_dir"
repo_dir="$(cd "$repo_dir" && pwd)"
rm -f "$repo_dir/$REPO_NAME".db* "$repo_dir/$REPO_NAME".files* \
    "$repo_dir/$PKGNAME"-*.pkg.tar.zst*

sign_args=()
if [ -n "$sign_key" ]; then
    sign_args=(--sign --key "$sign_key")
fi
read -ra makepkg_args <<< "${MAKEPKG_ARGS:-}"

(
    cd "$tmp_dir/build"
    PKGDEST="$repo_dir" PKGEXT=.pkg.tar.zst \
        makepkg --force --syncdeps "${makepkg_args[@]}" "${sign_args[@]}"
)

pkgs=("$repo_dir/$PKGNAME-$version"-*.pkg.tar.zst)
if [ "${#pkgs[@]}" -ne 1 ] || [ ! -f "${pkgs[0]}" ]; then
    echo "expected exactly one $PKGNAME $version package in $repo_dir" >&2
    exit 1
fi
pkg="${pkgs[0]}"

repo-add "${sign_args[@]}" "$repo_dir/$REPO_NAME.db.tar.gz" "$pkg"

# pacman asks the server for NAME.db and NAME.files, which repo-add leaves as
# symlinks. Release assets cannot be symlinks, so ship the archives under
# those names.
for kind in db files; do
    for suffix in "" .sig; do
        archive="$repo_dir/$REPO_NAME.$kind.tar.gz$suffix"
        if [ -e "$archive" ]; then
            mv -f "$archive" "$repo_dir/$REPO_NAME.$kind$suffix"
        fi
    done
done

repo_files=("$repo_dir/$REPO_NAME.db" "$repo_dir/$REPO_NAME.files")

if [ -n "$sign_key" ]; then
    gpg --batch --yes --dearmor --output "$tmp_dir/repo-key.gpg" "$KEY_FILE"
    for file in "$pkg" "${repo_files[@]}"; do
        if ! gpgv --keyring "$tmp_dir/repo-key.gpg" "$file.sig" "$file"; then
            echo "$(basename "$file") is not signed by the key in $KEY_FILE" >&2
            exit 1
        fi
    done
    repo_files+=("$repo_dir/$REPO_NAME.db.sig" "$repo_dir/$REPO_NAME.files.sig")
else
    echo "warning: no --sign-key given; the repository is unsigned" >&2
fi

if [ "$push" -ne 1 ]; then
    echo "Built pacman repository in $repo_dir"
    exit 0
fi

if ! gh release view "$RELEASE_TAG" >/dev/null 2>&1; then
    gh release create "$RELEASE_TAG" \
        --latest=false \
        --title "pacman repository" \
        --notes "Package database for pacman; see the Install section of the README for the pacman.conf entry. Regular downloads are attached to the versioned releases."
fi

# Upload the package before the database, so the database never names a file
# that is not there yet.
gh release upload "$RELEASE_TAG" "$pkg" "$pkg.sig" --clobber
gh release upload "$RELEASE_TAG" "${repo_files[@]}" --clobber

pkg_name="$(basename "$pkg")"
gh release view "$RELEASE_TAG" --json assets --jq '.assets[].name' |
    while read -r asset; do
        case "$asset" in
            "$pkg_name"|"$pkg_name.sig") ;;
            *.pkg.tar.zst|*.pkg.tar.zst.sig)
                gh release delete-asset "$RELEASE_TAG" "$asset" --yes
                ;;
        esac
    done

echo "Published $pkg_name to the $RELEASE_TAG release"
