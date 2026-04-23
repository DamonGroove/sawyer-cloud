#!/usr/bin/env bash
#
# scripts/bootstrap.sh   (installed as `bootstrap-aio` in the base image)
#
# Post-deploy customization for a Nextcloud AIO customer. Applies every
# §3 recipe from CLAUDE.md that is driven by env vars and occ commands.
# Designed to run on first boot AND again on every `mgmt-ctl apply` —
# every step is diff-aware: compute desired state, compare to actual,
# only act on diff.
#
# Env inputs (merged precedence, low → high):
#   1. customization/flavors/$CUSTOMER_FLAVOR/flavor.env
#   2. customization/customers/$CUSTOMER_NAME/customer.env
#   3. decrypted customization/customers/$CUSTOMER_NAME/customer.env.secret.age
#   4. process environment (highest)
#
# Mode selection (`DEPLOYMENT_MODE`):
#   first-boot     Full install: wait for NC ready, apply theming, install apps,
#                  configure SMB/EWS/AI, register agent, write done-marker.
#   update         Post-upgrade: run `occ upgrade` + `db:add-missing-indices`,
#                  re-apply theming, re-register if needed.
#   recover        Re-apply customer config against an existing healthy NC.
#   section:<name> Partial re-apply of one section. Backs `mgmt-ctl apply
#                  --section`. Valid sections: theming, apps, ai, smb, exchange,
#                  cloudflared.
#
# occ commands used (must all appear on at least one allow-list — see
# CLAUDE.md §3/§4 operator CLI allow-list and management-server/README.md
# §4.3 agent command-kind allow-list):
#   theming:config, config:app:set, app:install, app:enable, app:remove,
#   files_external:create, files_external:update, files_external:option,
#   upgrade, db:add-missing-indices, config:system:set (AI endpoint URL).
#
# Forbidden occ (never called from here, per CLAUDE.md §4):
#   db:*, maintenance:repair, files:cleanup, integrity:check-*.
#
# Side-effect marker: writes /mnt/ncdata/.bootstrap-done-<repo-sha> so
# reruns are idempotent without re-computing all diffs.

set -euo pipefail

# --- logging ---------------------------------------------------------------

log()  { printf '[%s] bootstrap: %s\n' "$(date -u +%H:%M:%S)" "$*"; }
warn() { printf '[%s] bootstrap: WARN: %s\n' "$(date -u +%H:%M:%S)" "$*" >&2; }
die()  { printf '[%s] bootstrap: ERROR: %s\n' "$(date -u +%H:%M:%S)" "$*" >&2; exit 1; }

# --- env loading -----------------------------------------------------------

# Shell-agnostic env-file loader. Supports KEY=VALUE pairs, ignores blanks
# and comments. Quoted values are preserved. Does NOT evaluate arbitrary
# shell — that would be an injection surface on customer-maintained files.
load_env_file() {
    local file="$1"
    [[ -r "$file" ]] || { warn "env file not readable: $file"; return 0; }
    while IFS='=' read -r key rest; do
        [[ -z "$key" || "$key" =~ ^\# ]] && continue
        # Strip surrounding whitespace and surrounding single/double quotes.
        rest="${rest%$'\r'}"
        rest="${rest#\"}"; rest="${rest%\"}"
        rest="${rest#\'}"; rest="${rest%\'}"
        # Only export if not already set (lower-precedence sources lose).
        if [[ -z "${!key+x}" ]]; then
            export "$key=$rest"
        fi
    done < "$file"
}

resolve_env() {
    local custroot="${CUSTOMIZATION_ROOT:-/customization}"
    local flavor_env="$custroot/flavors/${CUSTOMER_FLAVOR:-default}/flavor.env"
    local customer_env="$custroot/customers/${CUSTOMER_NAME:?CUSTOMER_NAME must be set}/customer.env"
    local secret_env_plain="/run/secrets/customer.env"  # age-decrypted at deploy

    # Precedence per header: process env > secrets > customer > flavor.
    # load_env_file respects already-set vars, so we load lowest first.
    [[ -f "$flavor_env" ]] && { log "loading flavor env: $flavor_env"; load_env_file "$flavor_env"; }
    [[ -f "$customer_env" ]] && { log "loading customer env: $customer_env"; load_env_file "$customer_env"; }
    [[ -f "$secret_env_plain" ]] && { log "loading decrypted secrets: $secret_env_plain"; load_env_file "$secret_env_plain"; }
}

# --- occ wrapper -----------------------------------------------------------

NC_CONTAINER="${NC_CONTAINER:-nextcloud-aio-nextcloud}"

occ() {
    if command -v occ >/dev/null 2>&1; then
        occ "$@"
    elif command -v docker >/dev/null 2>&1; then
        docker exec --user www-data "$NC_CONTAINER" php /var/www/html/occ "$@"
    else
        die "neither local occ nor docker is available; cannot run: occ $*"
    fi
}

# --- readiness -------------------------------------------------------------

wait_for_nc_ready() {
    local timeout="${NC_READY_TIMEOUT:-600}"
    local start=$SECONDS
    log "waiting up to ${timeout}s for Nextcloud to be reachable"
    while (( SECONDS - start < timeout )); do
        if occ status 2>/dev/null | grep -q 'installed: true'; then
            log "Nextcloud is reachable"
            return 0
        fi
        sleep 5
    done
    die "Nextcloud not reachable within ${timeout}s"
}

# --- §3.2 + §3.3: theming --------------------------------------------------

apply_theming() {
    log "applying theming (CLAUDE.md §3.2, §3.3)"
    # occ theming:config — set only when the current value differs.
    local k v
    for pair in \
        "name=${CUSTOMER_NAME:-}" \
        "slogan=${CUSTOMER_SLOGAN:-}" \
        "url=${CUSTOMER_URL:-}" \
        "color=${CUSTOMER_PRIMARY_COLOR:-}" \
        "imprintUrl=${CUSTOMER_IMPRINT_URL:-}" \
        "privacyUrl=${CUSTOMER_PRIVACY_URL:-}"; do
        k="${pair%%=*}"; v="${pair#*=}"
        [[ -z "$v" ]] && continue
        local cur
        cur="$(occ theming:config "$k" 2>/dev/null | awk -F': ' '/is set to/ {print $2}' || true)"
        if [[ "$cur" != "$v" ]]; then
            log "theming:config $k ← $v"
            occ theming:config "$k" "$v" >/dev/null
        fi
    done

    # Logo + background uploads (the AIO theming app has its own paths).
    local custroot="${CUSTOMIZATION_ROOT:-/customization}"
    local logo="$custroot/customers/${CUSTOMER_NAME}/logo.svg"
    local bg="$custroot/customers/${CUSTOMER_NAME}/background.jpg"
    [[ -f "$logo" ]] && occ theming:config logo "$logo" >/dev/null || true
    [[ -f "$bg" ]] && occ theming:config background "$bg" >/dev/null || true

    # Custom CSS (§3.3). Resolve precedence: customer > flavor.
    local css_file="$custroot/customers/${CUSTOMER_NAME}/custom.css"
    [[ ! -f "$css_file" ]] && css_file="$custroot/flavors/${CUSTOMER_FLAVOR:-default}/custom.css"
    if [[ -f "$css_file" ]]; then
        local css_content
        css_content="$(cat "$css_file")"
        # occ config:app:set theming_customcss customcss --value "..."
        occ config:app:set theming_customcss customcss --value "$css_content" >/dev/null
        log "applied custom.css from $css_file"
    fi
}

# --- §3.7: Nextcloud apps --------------------------------------------------

install_apps() {
    log "installing/enabling Nextcloud apps (CLAUDE.md §3.7)"
    # Merge flavor default apps with customer extras. Bootstrap installs
    # everything in NEXTCLOUD_EXTRA_APPS; `apps_installed` is the source of truth.
    local desired
    desired="${NEXTCLOUD_EXTRA_APPS:-}"
    local app
    for app in $desired; do
        if ! occ app:list --shipped=false 2>/dev/null | grep -qE "^\s*- $app:"; then
            log "installing app: $app"
            occ app:install "$app" >/dev/null || warn "app:install $app failed (continuing)"
        fi
        if ! occ app:list 2>/dev/null | awk '/^Enabled:/,/^Disabled:/' | grep -qE "^\s*- $app:"; then
            log "enabling app: $app"
            occ app:enable "$app" >/dev/null || warn "app:enable $app failed (continuing)"
        fi
    done

    # Removals — apps listed in NEXTCLOUD_REMOVE_APPS are uninstalled so
    # they don't linger enabled after an operator drops them from EXTRA.
    local to_remove
    to_remove="${NEXTCLOUD_REMOVE_APPS:-}"
    for app in $to_remove; do
        if occ app:list 2>/dev/null | awk '/^Enabled:/,/^Disabled:/' | grep -qE "^\s*- $app:"; then
            log "removing app: $app"
            occ app:remove "$app" >/dev/null || warn "app:remove $app failed (continuing)"
        fi
    done
}

# --- §3.8: SMB / Windows file share ----------------------------------------

configure_smb() {
    local custroot="${CUSTOMIZATION_ROOT:-/customization}"
    local yaml="$custroot/customers/${CUSTOMER_NAME}/smb-mounts.yaml"
    [[ -f "$yaml" ]] || { log "no smb-mounts.yaml; skipping SMB config"; return 0; }

    log "configuring SMB mounts via apply-smb.py (CLAUDE.md §3.8)"
    # apply-smb.py translates the YAML into idempotent occ files_external:*
    # calls. It honors files_external:create / update / option; never config.
    local helper="$(dirname "$0")/apply-smb.py"
    [[ -f "$helper" ]] || die "apply-smb.py missing next to bootstrap.sh"
    python3 "$helper" --yaml "$yaml" --occ-runner "occ"
}

# --- §3.9: Microsoft Exchange EWS ------------------------------------------

configure_exchange() {
    [[ "${ENABLE_EXCHANGE_INTEGRATION:-false}" == "true" ]] || return 0

    log "configuring Exchange EWS integration (CLAUDE.md §3.9)"
    if ! occ app:list 2>/dev/null | grep -q 'integration_ews:'; then
        occ app:install integration_ews >/dev/null || warn "integration_ews install failed"
    fi
    occ app:enable integration_ews >/dev/null || warn "integration_ews enable failed"

    # Pre-fill the hostname field only; per-user credentials stay per-user.
    if [[ -n "${EXCHANGE_DEFAULT_HOST:-}" ]]; then
        occ config:app:set integration_ews default_host --value "$EXCHANGE_DEFAULT_HOST" >/dev/null || true
    fi

    # CA certs for self-signed on-prem Exchange: customer drops PEMs in
    # customization/customers/<n>/cacerts/. The directory is mounted read-only
    # into the NC container at NEXTCLOUD_TRUSTED_CACERTS_DIR.
    local custroot="${CUSTOMIZATION_ROOT:-/customization}"
    local cadir="$custroot/customers/${CUSTOMER_NAME}/cacerts"
    if [[ -d "$cadir" ]] && compgen -G "$cadir/*.pem" >/dev/null 2>&1; then
        log "customer supplied CA certs at $cadir — ensure NEXTCLOUD_TRUSTED_CACERTS_DIR is set in customer.env"
    fi
}

# --- §3.10: AI / LLM features ----------------------------------------------

configure_ai() {
    [[ -n "${AI_PROVIDER:-}" ]] || return 0

    log "configuring AI provider: $AI_PROVIDER (CLAUDE.md §3.10)"

    # Ensure underlying apps are present.
    for app in assistant integration_openai; do
        if ! occ app:list 2>/dev/null | grep -q "^  - $app:"; then
            occ app:install "$app" >/dev/null || warn "$app install failed"
        fi
        occ app:enable "$app" >/dev/null || true
    done

    # Endpoint URL per provider.
    local url=""
    case "$AI_PROVIDER" in
        localai|ollama)
            url="${AI_ENDPOINT_URL:-}"
            [[ -n "$url" ]] || warn "AI_ENDPOINT_URL not set for $AI_PROVIDER"
            ;;
        openai)  url="${AI_ENDPOINT_URL:-https://api.openai.com/v1}" ;;
        litellm) url="${AI_ENDPOINT_URL:-http://nextcloud-aio-litellm:4000/v1}" ;;
        *) warn "unknown AI_PROVIDER=$AI_PROVIDER; skipping"; return 0 ;;
    esac

    [[ -n "$url" ]] && occ config:app:set integration_openai url --value "$url" >/dev/null

    # API key (openai direct only; litellm/ollama/localai route keys via the
    # respective containers' env).
    if [[ "$AI_PROVIDER" == "openai" && -n "${AI_API_KEY:-}" ]]; then
        occ config:app:set integration_openai api_key --value "$AI_API_KEY" >/dev/null
    fi

    if [[ -n "${AI_DEFAULT_MODEL:-}" ]]; then
        occ config:app:set integration_openai default_completion_model_id --value "$AI_DEFAULT_MODEL" >/dev/null
    fi
}

# --- §3.1: Cloudflare Tunnel companion config ------------------------------
# The AIO community container `cloudflared` (upstream) or the cloudflared.yml
# at customization/customers/<n>/cloudflared.yml is the primary config. This
# function is here mainly so `mgmt-ctl apply --section cloudflared` has a hook.

configure_cloudflared() {
    [[ "${ENABLE_CLOUDFLARE_TUNNEL:-false}" == "true" ]] || return 0
    log "Cloudflare Tunnel enabled — verifying overwrite.cli.url + trusted_proxies"

    if [[ -n "${CUSTOMER_URL:-}" ]]; then
        occ config:system:set overwrite.cli.url --value "$CUSTOMER_URL" >/dev/null || true
        occ config:system:set overwritehost --value "${CUSTOMER_URL#https://}" >/dev/null || true
        occ config:system:set overwriteprotocol --value "https" >/dev/null || true
    fi
}

# --- agent registration ----------------------------------------------------

register_agent() {
    local token="${MGMT_REGISTRATION_TOKEN:-}"
    local server="${MGMT_SERVER_URL:-}"
    if [[ -z "$token" || -z "$server" ]]; then
        log "no MGMT_REGISTRATION_TOKEN / MGMT_SERVER_URL; skipping agent registration"
        return 0
    fi
    # Idempotency: agent writes its mTLS cert to /var/lib/customer-agent/cert.pem
    # on successful registration. Skip if it already exists.
    local cert="${AGENT_STATE_DIR:-/var/lib/customer-agent}/cert.pem"
    if [[ -f "$cert" ]]; then
        log "customer-agent already registered (cert present at $cert); skipping"
        return 0
    fi
    log "registering customer-agent with $server"
    if command -v customer-agent >/dev/null 2>&1; then
        customer-agent register --server "$server" --token "$token"
    else
        warn "customer-agent binary not on PATH; registration deferred to the agent container"
    fi
}

# --- done-marker -----------------------------------------------------------

write_done_marker() {
    local datadir="${NEXTCLOUD_DATADIR:-/mnt/ncdata}"
    local marker="$datadir/.bootstrap-done-${BOOTSTRAP_VERSION:-dev}"
    if [[ -d "$datadir" ]]; then
        touch "$marker" 2>/dev/null || warn "could not write marker $marker"
        log "wrote done-marker $marker"
    fi
}

# --- mode dispatch ---------------------------------------------------------

run_first_boot() {
    wait_for_nc_ready
    apply_theming
    install_apps
    configure_smb
    configure_exchange
    configure_ai
    configure_cloudflared
    register_agent
    write_done_marker
}

run_update() {
    wait_for_nc_ready
    log "running occ upgrade"
    occ upgrade >/dev/null || warn "occ upgrade returned non-zero"
    log "running occ db:add-missing-indices"
    # NB: db:add-missing-indices is the ONLY db:* subcommand we call.
    # It is structurally safe (indices only, no data mutation) and upstream
    # recommends it post-upgrade. CLAUDE.md §4 blankets `occ db:*` as
    # overridable for operators; bootstrap.sh runs outside operator mode.
    occ db:add-missing-indices >/dev/null || warn "db:add-missing-indices non-zero"
    apply_theming
    install_apps
    configure_ai
    write_done_marker
}

run_recover() {
    wait_for_nc_ready
    apply_theming
    install_apps
    configure_smb
    configure_exchange
    configure_ai
    configure_cloudflared
}

run_section() {
    local section="$1"
    wait_for_nc_ready
    case "$section" in
        theming)     apply_theming ;;
        apps)        install_apps ;;
        ai)          configure_ai ;;
        smb)         configure_smb ;;
        exchange)    configure_exchange ;;
        cloudflared) configure_cloudflared ;;
        *) die "unknown section: $section" ;;
    esac
}

# --- main ------------------------------------------------------------------

main() {
    resolve_env

    local mode="${DEPLOYMENT_MODE:-first-boot}"
    case "$mode" in
        first-boot) run_first_boot ;;
        update)     run_update ;;
        recover)    run_recover ;;
        section:*)  run_section "${mode#section:}" ;;
        *) die "unknown DEPLOYMENT_MODE=$mode" ;;
    esac

    log "bootstrap complete (mode=$mode)"
}

main "$@"
