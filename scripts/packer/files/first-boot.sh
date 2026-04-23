#!/usr/bin/env bash
#
# scripts/packer/files/first-boot.sh  (installed as /usr/local/bin/first-boot.sh)
#
# Runs once, after the VM's first network-online boot. Reads the
# customer config mounted at /mnt/sawyer-config/ (a cloud-init NoCloud
# datasource or a 9p/virtiofs share from the hypervisor) and starts the
# sawyer-cloud docker stack.
#
# On success, masks itself so subsequent boots do not re-run.

set -euo pipefail

LOG=/var/log/first-boot.sh.log
exec >>"$LOG" 2>&1

echo "=== first-boot: $(date -u '+%Y-%m-%d %H:%M:%SZ') ==="

CONFIG_DIR="${CONFIG_DIR:-/mnt/sawyer-config}"
DEPLOY_DIR="${DEPLOY_DIR:-/srv/sawyer-cloud}"

# --- 1. wait for config directory -----------------------------------------
timeout=120
while (( timeout-- > 0 )); do
    if [[ -f "$CONFIG_DIR/customer.env" ]]; then
        break
    fi
    sleep 2
done
if [[ ! -f "$CONFIG_DIR/customer.env" ]]; then
    echo "first-boot: no $CONFIG_DIR/customer.env after 4min; aborting"
    exit 1
fi

# --- 2. decrypt secrets (optional) ----------------------------------------
if [[ -f "$CONFIG_DIR/customer.env.secret.age" ]]; then
    if [[ -z "${AGE_IDENTITY_FILE:-}" ]]; then
        echo "first-boot: AGE_IDENTITY_FILE not set but encrypted secrets present"
        exit 1
    fi
    age --decrypt -i "$AGE_IDENTITY_FILE" \
        -o "$DEPLOY_DIR/customer.env.secret" \
        "$CONFIG_DIR/customer.env.secret.age"
    chmod 0600 "$DEPLOY_DIR/customer.env.secret"
fi

# --- 3. sync the customer folder into place --------------------------------
mkdir -p "$DEPLOY_DIR"
rsync -a --delete "$CONFIG_DIR/customer/" "$DEPLOY_DIR/customization/customers/"
# compose files were baked into the base image at /sawyer/compose/ during build;
# copy them in if they're not already present (rsync --existing preserves
# operator edits if any).
if [[ -d /sawyer/compose ]]; then
    rsync -a /sawyer/compose/ "$DEPLOY_DIR/"
fi

# --- 4. source customer.env + start the stack ------------------------------
# shellcheck disable=SC1091
. "$CONFIG_DIR/customer.env"

cd "$DEPLOY_DIR"
CUSTOMER_NAME="${CUSTOMER_NAME:?customer.env must set CUSTOMER_NAME}" \
CUSTOMER_FLAVOR="${CUSTOMER_FLAVOR:-default}" \
MGMT_SERVER_URL="${MGMT_SERVER_URL:?customer.env must set MGMT_SERVER_URL}" \
DEPLOYMENT_MODE=first-boot \
AIO_IMAGE_TAG="${AIO_IMAGE_TAG:-latest}" \
docker compose -f compose.yaml -f customization/overlays/docker-compose.override.yaml up -d

# --- 5. mask self ----------------------------------------------------------
systemctl mask first-boot.service
echo "=== first-boot: complete ==="
