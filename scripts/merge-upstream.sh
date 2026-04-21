#!/usr/bin/env bash
#
# scripts/merge-upstream.sh
#
# Safe wrapper around `git subtree pull` for the `upstream/` subtree.
# Implements docs/MERGE_PROCEDURE.md. Called by the weekly
# .github/workflows/upstream-sync.yml action (with --ci) and usable
# manually for out-of-cycle pulls.
#
# Usage:
#   scripts/merge-upstream.sh              # interactive: pull, validate, leave
#                                          # branch locally; operator pushes.
#   scripts/merge-upstream.sh --dry-run    # pull, validate, then roll back.
#   scripts/merge-upstream.sh --ci         # pull, validate, push, open PR.
#   scripts/merge-upstream.sh --help
#
# Failure modes (per MERGE_PROCEDURE.md §4):
#   §4.1  "Working tree is not clean" — commit or stash, retry.
#   §4.2  "Upstream sync modified files OUTSIDE upstream/" — someone
#         committed to upstream/ directly in the past; escalate.
#   §4.3  "JSON validation failed" / "docker compose config failed" —
#         upstream schema drift; fix the overlay and retry.

set -euo pipefail

UPSTREAM_REMOTE="https://github.com/nextcloud/all-in-one.git"
UPSTREAM_BRANCH="main"
SUBTREE_PREFIX="upstream"
OVERLAY="customization/overlays/docker-compose.override.yaml"
COMPOSE_ROOT="compose.yaml"
CUSTOM_CONTAINERS_DIR="customization/community-containers"
SCHEMA_PATH="upstream/php/containers-schema.json"

die() { echo "merge-upstream: error: $*" >&2; exit 1; }
log() { echo "merge-upstream: $*"; }

mode="interactive"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --ci) mode="ci"; shift ;;
        --dry-run) mode="dry-run"; shift ;;
        --help|-h) sed -n '1,28p' "$0"; exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
done

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$repo_root" ]] || die "not inside a git repository"
cd "$repo_root"

# --- §4.1: clean tree required ---------------------------------------------
if ! git diff --quiet || ! git diff --cached --quiet; then
    die "Working tree is not clean. Commit or stash your changes, then re-run."
fi

# --- branch setup ----------------------------------------------------------
today="$(date -u +%Y%m%d)"
branch="upstream-sync/$today"
base_branch="$(git rev-parse --abbrev-ref HEAD)"
[[ "$base_branch" != "HEAD" ]] || die "refusing to run from a detached HEAD"

if git rev-parse --verify "$branch" >/dev/null 2>&1; then
    die "branch $branch already exists; delete or rename it before retrying"
fi

log "creating branch $branch from $base_branch"
git checkout -b "$branch"

rollback() {
    log "rolling back to $base_branch"
    git checkout --quiet "$base_branch" 2>/dev/null || true
    git branch -D "$branch" 2>/dev/null || true
}

# Anything that goes wrong past this point should leave us on base_branch.
trap 'rc=$?; [[ $rc -ne 0 ]] && rollback; exit $rc' ERR

# --- subtree pull ----------------------------------------------------------
log "pulling $UPSTREAM_REMOTE#$UPSTREAM_BRANCH into $SUBTREE_PREFIX/ (squash)"
git subtree pull --prefix="$SUBTREE_PREFIX" "$UPSTREAM_REMOTE" "$UPSTREAM_BRANCH" --squash

# Detect the "upstream hasn't moved" case cleanly.
if git diff --quiet "$base_branch".."$branch" -- "$SUBTREE_PREFIX/"; then
    log "no changes to pull (upstream is already at our pinned tip)"
    rollback
    exit 0
fi

# --- §4.2: nothing outside upstream/ may have changed ----------------------
non_upstream="$(git diff --name-only "$base_branch".."$branch" \
                | grep -v "^$SUBTREE_PREFIX/" || true)"
if [[ -n "$non_upstream" ]]; then
    log "Upstream sync appears to have modified files OUTSIDE upstream/:"
    printf '  %s\n' $non_upstream >&2
    die "refusing to proceed; someone likely edited upstream/ in the past — escalate per MERGE_PROCEDURE.md §4.2"
fi

# --- §4.3: validate community-container JSONs against upstream schema ------
if [[ -d "$CUSTOM_CONTAINERS_DIR" ]]; then
    log "validating $CUSTOM_CONTAINERS_DIR/*/*.json against $SCHEMA_PATH"
    # shellcheck disable=SC2044
    for jf in $(find "$CUSTOM_CONTAINERS_DIR" -maxdepth 2 -name '*.json' -print); do
        if command -v ajv >/dev/null 2>&1; then
            if ! ajv validate -s "$SCHEMA_PATH" -d "$jf" >/dev/null 2>&1; then
                die "JSON schema validation failed: $jf"
            fi
        else
            if ! python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$jf" >/dev/null 2>&1; then
                die "JSON parse failed: $jf"
            fi
            # Minimal structural check without jsonschema:
            python3 - "$jf" <<'PY' >/dev/null 2>&1 || die "JSON structural check failed: $jf"
import json, sys
d = json.load(open(sys.argv[1]))
assert "aio_services_v1" in d and isinstance(d["aio_services_v1"], list) and d["aio_services_v1"], "aio_services_v1 missing or empty"
for svc in d["aio_services_v1"]:
    for k in ("image", "container_name", "image_tag"):
        assert k in svc, f"service missing required key {k}"
PY
        fi
    done
fi

# --- §4.3: docker compose config round-trip --------------------------------
if command -v docker >/dev/null 2>&1 && [[ -f "$COMPOSE_ROOT" ]]; then
    log "validating compose.yaml + overlay via docker compose config"
    if ! docker compose -f "$COMPOSE_ROOT" -f "$OVERLAY" config --quiet 2>&1; then
        die "docker compose config failed; overlay likely out of sync with upstream schema"
    fi
else
    log "docker not available — skipping compose config check (CI runs it)"
fi

# --- summary + per-mode action ---------------------------------------------
# The pre-split SHA appears in the subtree squash commit message.
short_sha="$(git log -1 --grep='git-subtree-split' --format='%B' \
             | awk '/git-subtree-split:/ {print substr($2,1,12); exit}')"
short_sha="${short_sha:-unknown}"

log "subtree pull succeeded. upstream tip now at: $short_sha"

case "$mode" in
    dry-run)
        log "dry-run: rolling back so no branch is left behind"
        trap - ERR
        rollback
        log "done (dry-run)."
        ;;
    ci)
        log "ci: pushing $branch and opening PR"
        git push -u origin "$branch"
        if command -v gh >/dev/null 2>&1; then
            gh pr create \
                --title "chore(upstream-sync): pull nextcloud/all-in-one @ $short_sha" \
                --body "Scheduled weekly upstream sync run by \`scripts/merge-upstream.sh --ci\`.

Upstream tip: \`$short_sha\`

Reviewer checklist (docs/MERGE_PROCEDURE.md §2, §5):
- [ ] Upstream changelog reviewed for renamed containers / env vars / schema changes.
- [ ] Our overlay (\`customization/overlays/docker-compose.override.yaml\`) still references current field names.
- [ ] Community-container JSONs (customer-agent, litellm, ollama) still parse against upstream's containers-schema.json.
- [ ] Smoke tests pass on staging for 48h before production promotion." \
                --label upstream-sync \
                --label needs-engineering-review || log "gh pr create failed; PR not opened"
        else
            log "gh CLI not available in this environment; branch pushed, PR not opened"
        fi
        ;;
    interactive)
        log "interactive: branch $branch left in place on your clone."
        log "next steps:"
        log "    git push -u origin $branch"
        log "    open a PR and assign engineering for review"
        ;;
esac
