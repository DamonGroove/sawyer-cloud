#!/usr/bin/env bash
#
# scripts/release-vm.sh <tag>
#
# One-command VM artifact release. Tags HEAD as `<tag>-vm`, pushes the
# tag to origin, and tells you where to find the artifacts once CI
# completes (~30 min).
#
# Under the hood: pushing a tag matching `v*-vm` triggers
# .github/workflows/release-vm.yml, which installs Packer + qemu on a
# GitHub Actions runner, runs `packer build scripts/packer/aio-base.pkr.hcl`,
# and uploads the qcow2 + vmdk artifacts as assets on the GitHub Release
# for the tag.
#
# Usage:
#     scripts/release-vm.sh v0.1.1
#     scripts/release-vm.sh v0.1.1-vm      # already suffixed; left as-is
#
# Env inputs:
#   REMOTE           default: origin
#   SKIP_CLEAN_CHECK default: (unset — clean working tree required)

set -euo pipefail

die() { echo "release-vm: error: $*" >&2; exit 1; }
log() { echo "release-vm: $*"; }

[[ $# -eq 1 ]] || die "usage: $(basename "$0") <tag>  (e.g. v0.1.1 or v0.1.1-vm)"

tag="$1"

# Normalize: ensure the -vm suffix so the workflow trigger fires.
if [[ "$tag" != *-vm ]]; then
    log "normalizing tag '$tag' -> '${tag}-vm' (workflow triggers on v*-vm)"
    tag="${tag}-vm"
fi

# Shape check. Semver-ish + optional qualifier + -vm suffix.
[[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9.]+)*-vm$ ]] \
    || die "tag must match v<major>.<minor>.<patch>[-qual]-vm (got: $tag)"

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" \
    || die "not inside a git repository"
cd "$repo_root"

remote="${REMOTE:-origin}"

# Refuse a dirty tree — the tag points at HEAD, and uncommitted changes
# would not be in the artifact. SKIP_CLEAN_CHECK=1 bypasses for expert use.
if [[ -z "${SKIP_CLEAN_CHECK:-}" ]]; then
    if ! git diff --quiet || ! git diff --cached --quiet; then
        die "working tree is not clean; commit or stash first, or set SKIP_CLEAN_CHECK=1"
    fi
fi

if git rev-parse --verify "refs/tags/$tag" >/dev/null 2>&1; then
    die "tag '$tag' already exists locally; pick another or delete with 'git tag -d $tag'"
fi

head_sha="$(git rev-parse --short HEAD)"
head_subject="$(git log -1 --format=%s)"

log "tagging $head_sha ('$head_subject') as $tag"
git tag -a "$tag" -m "VM artifact release $tag

Built from $head_sha. Artifacts published by .github/workflows/release-vm.yml."

log "pushing $tag to $remote"
git push "$remote" "$tag"

# Derive the GitHub Releases URL if origin looks like github.com.
origin_url="$(git remote get-url "$remote" 2>/dev/null || true)"
if [[ "$origin_url" =~ github\.com[:/]+([^/]+)/([^/.]+)(\.git)?$ ]]; then
    owner="${BASH_REMATCH[1]}"
    repo="${BASH_REMATCH[2]}"
    log "CI is building now. Artifacts will appear at:"
    log "  https://github.com/${owner}/${repo}/releases/tag/$tag"
    log "Track workflow progress at:"
    log "  https://github.com/${owner}/${repo}/actions/workflows/release-vm.yml"
else
    log "CI is building now. Check the repo's Releases page in ~30 min."
fi
