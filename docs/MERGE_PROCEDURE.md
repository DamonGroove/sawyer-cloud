# Upstream Merge Procedure

This document describes how upstream `nextcloud/all-in-one` changes get pulled into our fork. Read this before running `scripts/merge-upstream.sh` manually.

**TL;DR:** The scheduled GitHub Action runs it weekly. If it opens a PR, engineering reviews and merges. If you need to pull upstream out-of-cycle (security advisory, customer-blocking bug fix), run `scripts/merge-upstream.sh` yourself, then follow the rest of this doc.

---

## 1. Why this matters

Every upstream change is a potential source of breakage. Upstream's philosophy is "features march forward" — they deprecate, rename, and restructure without long compatibility windows. Our fork is designed to shield customers from that, but the shielding only works if the upstream subtree stays unmodified and our overlays stay aligned with upstream's current shape.

The merge procedure exists to detect the two ways this can break:

- **Our overlays got stale.** Upstream renamed something we reference (a container name, a JSON key, an env var). The build still passes, but the overlay no longer does what it claims. Caught by the smoke test on staging.
- **Someone edited upstream/ directly.** Shouldn't happen — `CLAUDE.md` §5 forbids it and CI enforces — but if it did, we'd hit a merge conflict here. Conflicts in upstream/ mean "revert whatever ill-advised direct edit was made, then re-merge."

---

## 2. The normal path (weekly scheduled)

1. **Monday 07:00 UTC** — `.github/workflows/upstream-sync.yml` triggers.
2. The workflow runs `scripts/merge-upstream.sh --ci`. That script:
    - Creates `upstream-sync/<date>` branch.
    - Runs `git subtree pull --prefix=upstream/ https://github.com/nextcloud/all-in-one.git main --squash`.
    - Fails loudly if any file OUTSIDE `upstream/` changed as part of the merge (shouldn't happen, but sanity-check).
    - Validates our community-container JSONs against `upstream/php/containers-schema.json`.
    - Runs `docker compose config` against `compose.yaml` + overlay to catch YAML drift.
3. If the script exits clean, the workflow pushes the branch and opens a PR with the merge log in the body.
4. PR labels: `upstream-sync`, `needs-engineering-review`.
5. Engineering reviews the PR:
    - Reads upstream's changelog (linked in PR body).
    - Scans the diff for: renamed files, renamed containers, new required env vars, removed features, schema changes to `containers.json`, security-relevant changes to the mastercontainer's PHP.
    - If anything in our overlay references a renamed thing, opens a follow-up commit on the same branch to adjust.
6. Engineering merges the PR. The `staging-deploy.yml` workflow takes over — builds the image, deploys to staging, runs smoke tests.
7. **On green staging for 48 hours** with no customer reports, engineering uses `mgmt-ctl images promote <tag> --to production` to mark the tag deployable to customers.
8. Customer rollouts happen per-customer via `mgmt-ctl upgrade <slug> --to <tag>`. **Upgrades are never automatic.** Operators or engineering roll forward each customer with eyes on the customer's state.

---

## 3. The out-of-cycle path (security advisory, blocker fix)

Same steps, compressed timeline:

1. Ask engineering to trigger the workflow manually (`workflow_dispatch`) on the `upstream-sync.yml`. Or run locally: `scripts/merge-upstream.sh`.
2. Engineering reviews same day.
3. If the fix is urgent, the 48-hour soak on staging can be shortened to a few hours, but only by engineering (not operators) and only with Slack +1 from a second engineer.
4. Customer rollouts can start immediately after promotion if the fix is a security fix. Communicate to customers before rolling; avoid rolling during customer business hours when possible.

---

## 4. What to do if `merge-upstream.sh` fails

The script fails for exactly three reasons. Each has a specific response.

### 4.1 "Working tree is not clean"

Commit or stash your local work, then re-run. The script refuses to merge into a dirty tree because a failed merge could leave the working state ambiguous.

### 4.2 "Upstream sync appears to have modified files OUTSIDE upstream/"

This is a red flag. It means someone — almost certainly a past engineer using `OVERRIDE:` inappropriately — committed changes to `upstream/` directly, and now those commits are conflicting with upstream's real changes.

**Do not try to fix this yourself.** Do the following in order:

1. Note which files are listed in the error output.
2. Revert the branch: the script has already done this automatically; you should be back on `main` with no new branch.
3. Open an issue in `#nextcloud-ops` with the file list.
4. Engineering investigates: `git log -- upstream/<path>` will show who introduced the unauthorized change and when. The fix is to revert that change (and add the offending path to the pre-commit guard if somehow it escaped).
5. Once the unauthorized change is reverted, re-run `merge-upstream.sh`.

### 4.3 "JSON validation failed" or "docker-compose config failed"

This usually means upstream renamed a key or tightened the schema. Our overlay references the old shape.

Response:

1. Look at the error — the failing file is named.
2. Compare that file's fields against `upstream/php/containers-schema.json` on the newly-merged branch.
3. Adjust the overlay file to match the new schema. Commit on the same branch.
4. Re-run the validation step manually: `docker compose -f compose.yaml -f customization/overlays/docker-compose.override.yaml config --quiet`.
5. When it passes, push and open the PR.

Because these are schema changes by upstream, the fix is always cosmetic — we rename a field, we don't restructure our overlay.

---

## 5. Reading the upstream changelog

The things that matter for us, in priority order:

**High — always check.**
- Changes to `containers.json` format or `containers-schema.json`.
- Renamed container names (would break our `AIO_COMMUNITY_CONTAINERS` references and `docker exec` targets).
- Renamed or removed env vars (`NEXTCLOUD_*`, `AIO_*`, `APACHE_*`, `TALK_PORT`, `SKIP_DOMAIN_VALIDATION`).
- Security-relevant changes to the mastercontainer's docker socket interaction.
- Changes to the community-containers mechanism (how JSONs are discovered, the `/var/www/docker-aio/community-containers/` path).
- Nextcloud minimum version bump — check that our `info.xml` for the branding app still declares a compatible range.

**Medium — check if relevant.**
- New optional services (e.g., a new feature flag). If potentially useful, add to the `features` catalog in the management server.
- Bumped container image versions for services we don't customize (Postgres, Redis) — harmless but worth smoke-testing.
- Changes to `reverse-proxy.md` — if the customer-facing doc we link from CLAUDE.md §3.1 changed its advice, update our recipe.

**Low — informational.**
- UI changes to the AIO web interface itself. We rarely send operators there; it mostly matters for engineering.
- Doc-only changes.

If the changelog is empty (a quiet week upstream), the sync PR should still merge — subtree commits are cheap and the discipline of weekly merges keeps the lag short.

---

## 6. Pinning strategy

Our subtree currently tracks upstream's `main` branch. This is intentional for a few reasons:

- Upstream's release tags (e.g., `v11.0.0`) are synthetic — they track their AIO version, not the mastercontainer version directly. Tracking `main` gets us fixes faster.
- Our smoke tests on staging catch breakage before it reaches customers.
- Our customers are never on `main` — they're on promoted `:production` tags, which are our own versioning.

That said, we could pin to a specific upstream tag if a customer needs it (e.g., a compliance customer who only accepts labeled releases). The mechanism: edit `scripts/merge-upstream.sh` to pass the tag instead of `main`. This would be an engineering-only change.

---

## 7. When NOT to merge upstream

Situations where we deliberately delay the upstream merge:

- **During a customer-affecting incident.** Don't mix root-cause analysis with fresh changes. Freeze `main` until the incident is resolved and postmortem is filed.
- **During a Nextcloud major-version upgrade on the customer side.** Upstream sometimes bundles NC version bumps inside AIO releases; if we're already mid-migration on customer instances, stacking another version bump is asking for it.
- **When the upstream PR log shows "breaking changes" labels the team hasn't had time to read.** Just wait a week, let other users report issues upstream first.

In all three cases, the weekly scheduled workflow will still open a PR — engineering simply lets it sit (labels it `hold`) until the blocker clears.
