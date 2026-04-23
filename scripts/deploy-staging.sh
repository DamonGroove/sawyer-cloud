#!/usr/bin/env bash
#
# scripts/deploy-staging.sh
#
# Deploys the current repo state to the staging Linux server. Called by
# .github/workflows/staging-deploy.yml after the base image is published,
# running on the staging host itself (the workflow SSHes in and invokes
# this script; see docs/STAGING_SETUP.md when it lands).
#
# Responsibilities:
#   1. Pull the named image tag.
#   2. Sync compose files + overlay + staging-customer folder into
#      $DEPLOY_ROOT (outside the git working tree on the host).
#   3. Run `docker compose up -d` against compose.yaml + overlay.
#   4. Wait for Nextcloud to reach a healthy state.
#   5. Invoke bootstrap-aio in section:theming,apps,ai mode (idempotent;
#      applies any new customer.env values).
#   6. Run the smoke-test harness (scripts/smoke-test/test_staging.py).
#   7. On smoke-test success, emit a green marker file consumed by the
#      workflow's subsequent promote-to-staging-green step.
#
# Intentionally not:
#   - Pushing anything back to the registry (base-image-build.yml does that).
#   - Modifying the production customer folder (staging only).
#   - Opening GitHub PRs (that is the upstream-sync workflow's job).

set -euo pipefail

die() { echo "deploy-staging: error: $*" >&2; exit 1; }
log() { echo "deploy-staging: $*"; }

# --- inputs ----------------------------------------------------------------
IMAGE_TAG="${IMAGE_TAG:-latest}"
STAGING_CUSTOMER="${STAGING_CUSTOMER:-staging-customer}"
COMPOSE_ROOT="${COMPOSE_ROOT:-compose.yaml}"
OVERLAY="${OVERLAY:-customization/overlays/docker-compose.override.yaml}"
DEPLOY_ROOT="${DEPLOY_ROOT:-/srv/sawyer-cloud-staging}"
NC_READY_TIMEOUT="${NC_READY_TIMEOUT:-600}"
GREEN_MARKER="${GREEN_MARKER:-${DEPLOY_ROOT}/.staging-green-marker}"

command -v docker >/dev/null 2>&1 || die "docker is required"
repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$repo_root"

[[ -f "$COMPOSE_ROOT" ]] || die "$COMPOSE_ROOT not found (run from repo root)"
[[ -f "$OVERLAY" ]] || die "$OVERLAY not found"

log "image tag:       $IMAGE_TAG"
log "staging customer: $STAGING_CUSTOMER"
log "deploy root:     $DEPLOY_ROOT"

# --- 1. pull ---------------------------------------------------------------
log "pulling images referenced by $COMPOSE_ROOT + $OVERLAY"
docker compose -f "$COMPOSE_ROOT" -f "$OVERLAY" pull

# --- 2. sync artifacts -----------------------------------------------------
log "syncing customization artifacts to $DEPLOY_ROOT"
mkdir -p "$DEPLOY_ROOT"
# Rsync excludes other customers so staging never touches their data.
if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
        --exclude 'customization/customers/*' \
        --include "customization/customers/${STAGING_CUSTOMER}/***" \
        "$repo_root/" "$DEPLOY_ROOT/"
else
    # Fallback: cp -a (less precise but functional for small repos).
    cp -a "$repo_root/." "$DEPLOY_ROOT/"
fi

# --- 3. bring the stack up -------------------------------------------------
log "restarting docker compose stack"
(
    cd "$DEPLOY_ROOT"
    docker compose -f "$COMPOSE_ROOT" -f "$OVERLAY" up -d --remove-orphans
)

# --- 4. wait for NC ready --------------------------------------------------
log "waiting up to ${NC_READY_TIMEOUT}s for Nextcloud"
start=$SECONDS
ready=false
while (( SECONDS - start < NC_READY_TIMEOUT )); do
    if docker exec --user www-data nextcloud-aio-nextcloud php /var/www/html/occ status 2>/dev/null \
        | grep -q 'installed: true'; then
        ready=true; break
    fi
    sleep 10
done
$ready || die "Nextcloud did not become ready within ${NC_READY_TIMEOUT}s"
log "Nextcloud is up"

# --- 5. re-apply customer config via bootstrap-aio -------------------------
log "running bootstrap-aio in update mode against staging customer"
docker exec \
    -e DEPLOYMENT_MODE=update \
    -e CUSTOMER_NAME="$STAGING_CUSTOMER" \
    -e CUSTOMER_FLAVOR="${STAGING_FLAVOR:-default}" \
    -e CUSTOMIZATION_ROOT=/customization \
    nextcloud-aio-mastercontainer \
    /usr/local/bin/bootstrap-aio || die "bootstrap-aio failed"

# --- 6. smoke tests --------------------------------------------------------
log "running smoke tests"
if [[ -x scripts/smoke-test/test_staging.py ]]; then
    python3 scripts/smoke-test/test_staging.py \
        --host "${STAGING_HOST:-localhost}" \
        --customer "$STAGING_CUSTOMER"
else
    die "smoke-test harness missing"
fi

# --- 7. green marker -------------------------------------------------------
printf 'tag=%s\nsha=%s\ntime=%s\n' \
    "$IMAGE_TAG" "$(git rev-parse HEAD)" "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
    > "$GREEN_MARKER"
log "wrote green marker at $GREEN_MARKER"

log "staging deploy complete"
