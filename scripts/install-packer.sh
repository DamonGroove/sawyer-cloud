#!/usr/bin/env bash
#
# scripts/install-packer.sh
#
# Installs HashiCorp Packer at a pinned version into ${INSTALL_DIR:-./bin}.
# No sudo, no system-wide install. Verifies SHA256 against HashiCorp's
# published checksum file; verifies the GPG signature when `gpg` is
# available locally.
#
# Used by .github/workflows/release-vm.yml; runnable locally for dev.
#
# Env inputs:
#   PACKER_VERSION  default 1.11.2
#   INSTALL_DIR     default ./bin
#   PLATFORM        default $(uname -s | tr '[:upper:]' '[:lower:]')
#   ARCH            default $(uname -m mapped: x86_64→amd64, aarch64→arm64)
#
# Idempotent: re-running with the same version is a no-op (verifies the
# binary already at $INSTALL_DIR/packer reports the requested version
# and exits 0 without re-downloading).

set -euo pipefail

PACKER_VERSION="${PACKER_VERSION:-1.11.2}"
INSTALL_DIR="${INSTALL_DIR:-./bin}"

die() { echo "install-packer: error: $*" >&2; exit 1; }
log() { echo "install-packer: $*"; }

# --- platform detection ----------------------------------------------------
PLATFORM="${PLATFORM:-$(uname -s | tr '[:upper:]' '[:lower:]')}"
case "$PLATFORM" in
    linux|darwin|windows) ;;
    *) die "unsupported platform: $PLATFORM" ;;
esac

raw_arch="${ARCH:-$(uname -m)}"
case "$raw_arch" in
    x86_64|amd64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    *) die "unsupported arch: $raw_arch" ;;
esac

ZIP_NAME="packer_${PACKER_VERSION}_${PLATFORM}_${ARCH}.zip"
SUMS_NAME="packer_${PACKER_VERSION}_SHA256SUMS"
SIG_NAME="packer_${PACKER_VERSION}_SHA256SUMS.sig"
BASE_URL="https://releases.hashicorp.com/packer/${PACKER_VERSION}"

# --- short-circuit if the right version is already installed --------------
mkdir -p "$INSTALL_DIR"
target="$INSTALL_DIR/packer"
if [[ -x "$target" ]]; then
    if "$target" version 2>/dev/null | grep -q "v${PACKER_VERSION}\b"; then
        log "packer ${PACKER_VERSION} already at $target — nothing to do"
        exit 0
    fi
fi

# --- prerequisites ---------------------------------------------------------
for cmd in curl unzip sha256sum; do
    command -v "$cmd" >/dev/null 2>&1 || die "$cmd is required"
done

# --- download to a tempdir -------------------------------------------------
tmpdir="$(mktemp -d -t packer-install.XXXXXX)"
trap 'rm -rf "$tmpdir"' EXIT

log "downloading $ZIP_NAME"
curl -fsSL -o "$tmpdir/$ZIP_NAME" "$BASE_URL/$ZIP_NAME"

log "downloading $SUMS_NAME"
curl -fsSL -o "$tmpdir/$SUMS_NAME" "$BASE_URL/$SUMS_NAME"

# --- verify SHA256 ---------------------------------------------------------
log "verifying SHA256"
(
    cd "$tmpdir"
    grep "  $ZIP_NAME\$" "$SUMS_NAME" | sha256sum -c -
)

# --- verify GPG signature when gpg is present ------------------------------
# HashiCorp's release-signing key is well-known but rotates; if `gpg` and
# the key aren't both available we warn and continue with checksum-only.
if command -v gpg >/dev/null 2>&1; then
    log "downloading $SIG_NAME"
    curl -fsSL -o "$tmpdir/$SIG_NAME" "$BASE_URL/$SIG_NAME"
    if gpg --list-keys 0xC874011F0AB405110D02105534365D9472D7468F >/dev/null 2>&1 \
       || gpg --recv-keys 0xC874011F0AB405110D02105534365D9472D7468F 2>/dev/null; then
        log "verifying GPG signature"
        if gpg --verify "$tmpdir/$SIG_NAME" "$tmpdir/$SUMS_NAME" >/dev/null 2>&1; then
            log "GPG signature OK"
        else
            die "GPG signature verification failed"
        fi
    else
        log "GPG key not available locally; skipped signature verification (checksum still verified)"
    fi
else
    log "gpg not installed; skipped signature verification (checksum still verified)"
fi

# --- install ---------------------------------------------------------------
log "extracting to $INSTALL_DIR"
unzip -q -o "$tmpdir/$ZIP_NAME" -d "$tmpdir/extract"
install -m 0755 "$tmpdir/extract/packer" "$target"

log "installed: $target"
"$target" version
