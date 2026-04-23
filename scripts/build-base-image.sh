#!/usr/bin/env bash
#
# scripts/build-base-image.sh   (locked in operator mode per CLAUDE.md §5)
#
# Builds the sawyer-cloud aio-base image. Called by
# .github/workflows/base-image-build.yml on main, and runnable locally for
# testing. Does NOT push unless PUSH=true is set explicitly.
#
# Env inputs:
#   REGISTRY        (default: ghcr.io)
#   DOCKER_ORG      (default: sawyer-cloud)
#   AIO_VERSION     (default: latest) — upstream mastercontainer tag to pin on
#   PUSH            (default: false)  — set to "true" to push after build
#   PLATFORMS       (default: linux/amd64) — multi-arch via buildx
#
# Tags produced:
#   ${REGISTRY}/${DOCKER_ORG}/aio-base:<git-short-sha>
#   ${REGISTRY}/${DOCKER_ORG}/aio-base:latest        (main-branch builds only)

set -euo pipefail

die() { echo "build-base-image: error: $*" >&2; exit 1; }
log() { echo "build-base-image: $*"; }

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$repo_root" ]] || die "not inside a git repository"
cd "$repo_root"

command -v docker >/dev/null 2>&1 || die "docker is required (docker buildx especially)"

REGISTRY="${REGISTRY:-ghcr.io}"
DOCKER_ORG="${DOCKER_ORG:-sawyer-cloud}"
AIO_VERSION="${AIO_VERSION:-latest}"
PUSH="${PUSH:-false}"
PLATFORMS="${PLATFORMS:-linux/amd64}"

SHA="$(git rev-parse --short HEAD)"
BUILD_DATE="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
IMAGE="${REGISTRY}/${DOCKER_ORG}/aio-base"

# Only tag :latest when we're on main (or in CI with a clear main signal).
# Locally, don't accidentally move :latest — someone could deploy off your
# laptop build.
tag_latest="false"
branch="$(git rev-parse --abbrev-ref HEAD || echo '')"
if [[ "$branch" == "main" || "${GITHUB_REF_NAME:-}" == "main" ]]; then
    tag_latest="true"
fi

log "repo:       $repo_root"
log "image:      $IMAGE"
log "tag (sha):  $SHA"
log "tag latest: $tag_latest"
log "platforms:  $PLATFORMS"
log "push:       $PUSH"
log "aio base:   ghcr.io/nextcloud-releases/all-in-one:${AIO_VERSION}"

args=(
    --file scripts/Dockerfile.base
    --build-arg "BUILD_SHA=${SHA}"
    --build-arg "BUILD_DATE=${BUILD_DATE}"
    --build-arg "AIO_VERSION=${AIO_VERSION}"
    --platform "$PLATFORMS"
    --tag "${IMAGE}:${SHA}"
)

if [[ "$tag_latest" == "true" ]]; then
    args+=( --tag "${IMAGE}:latest" )
fi

if [[ "$PUSH" == "true" ]]; then
    args+=( --push )
else
    # --load only works on single-platform builds; default single-arch is fine.
    if [[ "$PLATFORMS" == *,* ]]; then
        log "multi-platform build but PUSH=false — buildx cannot load images"
        log "producing cache-only build; export manually if you need artifacts"
    else
        args+=( --load )
    fi
fi

docker buildx build "${args[@]}" .

log "done. tags:"
log "    ${IMAGE}:${SHA}"
if [[ "$tag_latest" == "true" ]]; then
    log "    ${IMAGE}:latest"
fi
if [[ "$PUSH" == "true" ]]; then
    log "pushed to ${REGISTRY}"
else
    log "local-only; set PUSH=true to publish"
fi
