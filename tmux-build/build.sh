#!/bin/bash
# Build tmux from upstream git master as a Debian .deb package.
#
# Motivation: upstream master has synchronized output mode (DECSET 2026)
# which fixes terminal flickering in tools like Claude Code.
#
# Usage:
#   ./tmux-build/build.sh              # Build only
#   ./tmux-build/build.sh --install    # Build and install

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
UPSTREAM_REPO="https://github.com/tmux/tmux.git"
UPSTREAM_DIR="$BUILD_DIR/tmux-upstream"
# Debian source package version to steal debian/ directory from
DEB_SRC_VERSION="3.6a-2"

INSTALL=0
if [[ "${1:-}" == "--install" ]]; then
    INSTALL=1
fi

mkdir -p "$BUILD_DIR"

# ── Phase 1: Install build dependencies ──────────────────────────────
echo "==> Phase 1: Installing build dependencies..."
sudo apt-get -y build-dep tmux
sudo apt-get -y install autoconf automake pkg-config devscripts

# ── Phase 2: Clone or update upstream ────────────────────────────────
echo "==> Phase 2: Cloning/updating upstream tmux..."
if [[ -d "$UPSTREAM_DIR/.git" ]]; then
    git -C "$UPSTREAM_DIR" fetch --all
    git -C "$UPSTREAM_DIR" checkout master
    git -C "$UPSTREAM_DIR" reset --hard origin/master
else
    git clone "$UPSTREAM_REPO" "$UPSTREAM_DIR"
fi

# ── Phase 3: Determine version ───────────────────────────────────────
echo "==> Phase 3: Determining version..."
GIT_DATE="$(git -C "$UPSTREAM_DIR" log -1 --format=%cd --date=format:%Y%m%d)"
GIT_SHA="$(git -C "$UPSTREAM_DIR" log -1 --format=%h)"
# Base version from Debian source (strip the Debian revision)
BASE_VERSION="${DEB_SRC_VERSION%-*}"
SNAPSHOT_VERSION="${BASE_VERSION}+git${GIT_DATE}.${GIT_SHA}"
FULL_VERSION="${SNAPSHOT_VERSION}-1~local1"
echo "    Upstream HEAD: ${GIT_SHA} (${GIT_DATE})"
echo "    Package version: ${FULL_VERSION}"

# ── Phase 4: Prepare build tree ──────────────────────────────────────
echo "==> Phase 4: Preparing build tree..."
BUILD_TREE="$BUILD_DIR/tmux-${SNAPSHOT_VERSION}"
rm -rf "$BUILD_TREE"
# Copy upstream source without .git
git -C "$UPSTREAM_DIR" archive --format=tar HEAD | (mkdir -p "$BUILD_TREE" && tar -C "$BUILD_TREE" -xf -)

# ── Phase 5: Get Debian packaging ────────────────────────────────────
echo "==> Phase 5: Downloading Debian source package..."
# Only download if we don't already have the .dsc
DEB_DSC="$BUILD_DIR/tmux_${DEB_SRC_VERSION}.dsc"
if [[ ! -f "$DEB_DSC" ]]; then
    (cd "$BUILD_DIR" && apt-get source --download-only tmux="${DEB_SRC_VERSION}")
fi

# Extract debian/ directory from the Debian source package
DEBIAN_EXTRACT="$BUILD_DIR/tmux-debian-extract"
rm -rf "$DEBIAN_EXTRACT"
(cd "$BUILD_DIR" && dpkg-source -x --no-check "$DEB_DSC" "$DEBIAN_EXTRACT")
cp -a "$DEBIAN_EXTRACT/debian" "$BUILD_TREE/debian"
rm -rf "$DEBIAN_EXTRACT"

# ── Phase 6: Adapt for git master ────────────────────────────────────
echo "==> Phase 6: Adapting Debian packaging for git master..."

# Switch to native format (avoids needing orig tarball + quilt patches)
echo "3.0 (native)" > "$BUILD_TREE/debian/source/format"

# Drop all quilt patches (they're for the release, not git master)
rm -rf "$BUILD_TREE/debian/patches"

# Create etc/ directory needed by configure.ac's AC_CONFIG_AUX_DIR(etc)
# (exists in release tarballs but not in git)
mkdir -p "$BUILD_TREE/etc"

# Update changelog with our snapshot version
(cd "$BUILD_TREE" && dch \
    --newversion "$FULL_VERSION" \
    --distribution unstable \
    "Local build from upstream git master (${GIT_SHA}).")

# ── Phase 7: Build ───────────────────────────────────────────────────
echo "==> Phase 7: Building..."
(cd "$BUILD_TREE" && dpkg-buildpackage -us -uc -b --jobs=auto)

# ── Phase 8: Report / install ────────────────────────────────────────
echo ""
echo "==> Phase 8: Build complete!"
echo ""
echo "Built packages:"
ls -1 "$BUILD_DIR"/tmux_*.deb "$BUILD_DIR"/tmux-dbgsym_*.deb 2>/dev/null || true
echo ""

DEB_FILE="$(ls -1 "$BUILD_DIR"/tmux_*.deb 2>/dev/null | head -1)"
if [[ -z "$DEB_FILE" ]]; then
    echo "ERROR: No .deb file found!" >&2
    exit 1
fi

echo "Package info:"
dpkg-deb -I "$DEB_FILE" | grep -E '(Package|Version|Architecture):'
echo ""

if [[ "$INSTALL" -eq 1 ]]; then
    echo "==> Installing..."
    sudo dpkg -i "$DEB_FILE"
    echo ""
    echo "Installed tmux version:"
    tmux -V
else
    echo "To install, run:"
    echo "  sudo dpkg -i $DEB_FILE"
    echo "Or re-run with --install flag:"
    echo "  $0 --install"
fi
