#!/usr/bin/env bash
#
# scripts/install-hooks.sh
#
# Installs the local git hooks that enforce CLAUDE.md §5 and §1.3.
#
# Hooks installed:
#   pre-commit  — runs scripts/check-forbidden-paths.sh against staged files.
#   commit-msg  — when SAWYER_OVERRIDE=1 is set by the committer, requires
#                 the commit subject to begin with "[OVERRIDE]" (CLAUDE.md §7),
#                 and verifies .override-log.md has been updated in the same
#                 commit (CLAUDE.md §1.3).
#
# Idempotent: safe to re-run. Existing hooks are backed up once to
# `<name>.pre-sawyer.bak` on first install only, so subsequent runs don't
# clobber that backup.
#
# Usage:
#   scripts/install-hooks.sh            # install both hooks
#   scripts/install-hooks.sh --uninstall  # restore backups if present
#   scripts/install-hooks.sh --help

set -euo pipefail

die() { echo "error: $*" >&2; exit 2; }
log() { echo "install-hooks: $*"; }

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$repo_root" ]] || die "not inside a git repository"
cd "$repo_root"

hooks_dir="$(git rev-parse --git-path hooks)"
[[ -d "$hooks_dir" ]] || die "git hooks dir not found: $hooks_dir"

guard="scripts/check-forbidden-paths.sh"
[[ -x "$guard" ]] || die "$guard missing or not executable; run after Phase 1 item 1 lands"

# ----------------------------------------------------------------------------

cmd="${1:-install}"
case "$cmd" in
    install|"") action=install ;;
    --uninstall|uninstall) action=uninstall ;;
    --help|-h)
        sed -n '1,26p' "$0"
        exit 0
        ;;
    *) die "unknown argument: $cmd" ;;
esac

install_hook() {
    local name="$1" body="$2"
    local target="$hooks_dir/$name"
    if [[ -f "$target" && ! -f "$target.pre-sawyer.bak" ]]; then
        # Preserve whatever was there before on first install only.
        cp -p "$target" "$target.pre-sawyer.bak"
        log "backed up existing $name to $name.pre-sawyer.bak"
    fi
    printf '%s\n' "$body" > "$target"
    chmod +x "$target"
    log "installed $name -> $target"
}

uninstall_hook() {
    local name="$1"
    local target="$hooks_dir/$name"
    if [[ -f "$target.pre-sawyer.bak" ]]; then
        mv "$target.pre-sawyer.bak" "$target"
        log "restored $name from backup"
    elif [[ -f "$target" ]]; then
        rm -f "$target"
        log "removed $name (no backup to restore)"
    fi
}

pre_commit_body='#!/usr/bin/env bash
# Installed by scripts/install-hooks.sh — do not hand-edit; re-run the
# installer to update.
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel)"
exec "$repo_root/scripts/check-forbidden-paths.sh" --staged
'

commit_msg_body='#!/usr/bin/env bash
# Installed by scripts/install-hooks.sh — do not hand-edit.
# Enforces CLAUDE.md §7 commit-subject convention and §1.3 override-log
# requirement when SAWYER_OVERRIDE is set.
set -euo pipefail
msg_file="$1"
[[ -n "${SAWYER_OVERRIDE:-}" ]] || exit 0

first_line="$(head -n1 "$msg_file")"
if [[ "$first_line" != "[OVERRIDE]"* ]]; then
    echo "commit-msg: SAWYER_OVERRIDE=1 but subject does not start with [OVERRIDE]." >&2
    echo "            CLAUDE.md §7 requires override commits to be visibly marked." >&2
    exit 1
fi

# .override-log.md must be staged in this commit.
if ! git diff --cached --name-only | grep -qx ".override-log.md"; then
    echo "commit-msg: SAWYER_OVERRIDE=1 but .override-log.md is not staged." >&2
    echo "            CLAUDE.md §1.3 requires an audit entry in the same commit." >&2
    exit 1
fi

exit 0
'

case "$action" in
    install)
        install_hook pre-commit "$pre_commit_body"
        install_hook commit-msg "$commit_msg_body"
        log "done. hooks are active for this clone."
        ;;
    uninstall)
        uninstall_hook pre-commit
        uninstall_hook commit-msg
        log "done."
        ;;
esac
