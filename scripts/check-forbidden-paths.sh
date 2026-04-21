#!/usr/bin/env bash
#
# scripts/check-forbidden-paths.sh
#
# Enforces CLAUDE.md §5 forbidden-paths against staged (or selected) files.
# Invoked by the pre-commit hook installed via scripts/install-hooks.sh;
# also usable standalone for CI and ad-hoc checks.
#
# Usage:
#   check-forbidden-paths.sh                # check staged files (default, hook mode)
#   check-forbidden-paths.sh --all          # check every tracked file in HEAD
#   check-forbidden-paths.sh --files A B    # check specific paths
#   check-forbidden-paths.sh --list         # print the glob table and exit
#   check-forbidden-paths.sh --help
#
# Behavior:
#   - LOCKED globs: commits fail unconditionally. Unlocking a locked path
#     requires the session-specific 16-char engineering keyword (CLAUDE.md
#     §6.4). That keyword is NOT checked here — the workflow is: engineer
#     provisions it out-of-band, Claude uses it in-session, and the CI job
#     bypasses this guard via a separate label-protected path.
#   - OVERRIDABLE globs: commits fail unless env var SAWYER_OVERRIDE is a
#     non-empty value. Claude Code sets SAWYER_OVERRIDE=1 when the operator's
#     message begins with `OVERRIDE:` and logs the justification to
#     .override-log.md per CLAUDE.md §1.3.
#
# Bootstrap mode short-circuit: if BOOTSTRAP.md exists at the repo root and
# git log contains NO commit whose subject begins `chore: archive BOOTSTRAP.md`,
# the guard is suspended per CLAUDE.md §0.2 and the script exits 0 silently.

set -euo pipefail

die() { echo "error: $*" >&2; exit 2; }

# --- glob table (mirrors CLAUDE.md §5 exactly) ------------------------------
# Format: "<status>|<glob>"
globs=(
    "locked|upstream/**"
    "overridable|.github/workflows/**"
    "locked|management-server/app/auth/**"
    "locked|management-server/app/security/**"
    "locked|scripts/merge-upstream.sh"
    "locked|scripts/build-base-image.sh"
    "locked|CLAUDE.md"
    "locked|README.md"
    "locked|**/secrets.yaml"
    "overridable|**/*.age"
    "overridable|compose.yaml"
)

# --- argument parsing (handle info flags before anything else) --------------
mode="staged"
files=()
case "${1:-}" in
    --list)
        printf '%-14s  %s\n' "STATUS" "GLOB"
        for g in "${globs[@]}"; do
            printf '%-14s  %s\n' "${g%%|*}" "${g#*|}"
        done
        exit 0
        ;;
    --help|-h)
        sed -n '1,36p' "$0"
        exit 0
        ;;
    --all)    mode="all"; shift || true ;;
    --files)  mode="files"; shift; files=("$@") ;;
    --staged|"") mode="staged" ;;
    *) die "unknown argument: $1" ;;
esac

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$repo_root" ]] || die "not inside a git repository"
cd "$repo_root"

# --- bootstrap-mode short-circuit (CLAUDE.md §0.1, §5 note) -----------------
if [[ -f BOOTSTRAP.md ]] \
   && ! git log --format='%s' 2>/dev/null | grep -q '^chore: archive BOOTSTRAP\.md'; then
    # Bootstrap mode: §5 is suspended; let this commit through.
    exit 0
fi

# --- file set selection -----------------------------------------------------
case "$mode" in
    staged) mapfile -t files < <(git diff --cached --name-only --diff-filter=ACMR) ;;
    all)    mapfile -t files < <(git ls-files) ;;
    files)  : ;;  # already populated
esac

if [[ ${#files[@]} -eq 0 ]]; then
    exit 0
fi

# --- glob matcher -----------------------------------------------------------
# Uses bash globstar so ** spans directory components.
shopt -s extglob globstar nullglob

match_glob() {
    local path="$1" glob="$2"
    # shellcheck disable=SC2053
    [[ $path == $glob ]] && return 0
    # bash globstar treats `**/foo` as "one or more dirs + foo" inside [[ ]].
    # We need zero-or-more semantics so `**/secrets.yaml` also matches
    # `secrets.yaml` at the repo root.
    if [[ ${glob:0:3} == '**/' ]]; then
        local bare="${glob:3}"
        # shellcheck disable=SC2053
        [[ $path == $bare ]] && return 0
    fi
    return 1
}

# --- scan -------------------------------------------------------------------
violations_locked=()
violations_overridable=()

for f in "${files[@]}"; do
    for gentry in "${globs[@]}"; do
        status="${gentry%%|*}"
        glob="${gentry#*|}"
        if match_glob "$f" "$glob"; then
            case "$status" in
                locked)      violations_locked+=("$f :: $glob") ;;
                overridable) violations_overridable+=("$f :: $glob") ;;
            esac
        fi
    done
done

rc=0

if [[ ${#violations_locked[@]} -gt 0 ]]; then
    {
        echo ""
        echo "ERROR: staged paths match LOCKED globs (CLAUDE.md §5):"
        printf '  %s\n' "${violations_locked[@]}"
        echo ""
        echo "Locked paths cannot be unlocked by OVERRIDE:. They require the"
        echo "session-specific 16-char engineering keyword (CLAUDE.md §6.4)."
        echo "Contact engineering in #nextcloud-ops before retrying."
    } >&2
    rc=1
fi

if [[ ${#violations_overridable[@]} -gt 0 ]]; then
    if [[ -n "${SAWYER_OVERRIDE:-}" ]]; then
        {
            echo ""
            echo "NOTE: staged paths match OVERRIDABLE globs; SAWYER_OVERRIDE is set:"
            printf '  %s\n' "${violations_overridable[@]}"
            echo "Allowed. Ensure .override-log.md is updated (CLAUDE.md §1.3)."
        } >&2
    else
        {
            echo ""
            echo "ERROR: staged paths match OVERRIDABLE globs (CLAUDE.md §5):"
            printf '  %s\n' "${violations_overridable[@]}"
            echo ""
            echo "Retry your operator message prefixed with:"
            echo "    OVERRIDE: <one-sentence justification>"
            echo "Claude will then set SAWYER_OVERRIDE=1 and append an entry"
            echo "to .override-log.md per CLAUDE.md §1.3."
        } >&2
        rc=1
    fi
fi

exit $rc
