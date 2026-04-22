# BOOTSTRAP.md — archived

> **This file was the one-shot bootstrap instruction consumed at repo
> creation on 2026-04-21. It is archived here for traceability; do not
> run it again.**
>
> The commit that moved this file from the repo root (subject prefix
> `chore: archive BOOTSTRAP.md`) is the explicit mode-switch marker
> that CLAUDE.md §0.1(3) checks. With BOOTSTRAP.md no longer at the
> root and this commit in history, new Claude sessions opening the repo
> resolve §0.1 to **operator mode** and enforce §1–§9.
>
> If an engineer legitimately needs to do work that would violate
> operator-mode rules, the path is an engineering PR with reviewers
> and CI — **not** re-running this bootstrap. Re-creating `BOOTSTRAP.md`
> at the repo root is flagged as tampering per CLAUDE.md §0.5.

---

*What follows is the original content, unchanged.*

---

# BOOTSTRAP.md — Instructions for Claude Code

**Read this file first. It is the only one that tells you what to do right now. Every other MD in this handoff tells you what the finished system should look like.**

---

## 1. What this is and who you are

You are Claude Code, running in a terminal session pointed at an empty (or near-empty) git repository on an engineer's laptop. The engineer has just handed you eight markdown files:

1. `CLAUDE.md`
2. `README.md`
3. `RESEARCH_REPORT.md`
4. `MERGE_PROCEDURE.md`
5. `INCIDENT_PLAYBOOK.md`
6. `OPERATOR_TASKS.md`
7. `MANAGEMENT_SERVER.md`
8. `MGMT_CTL_CLI_SPEC.md`

Together these describe a private fork of the `nextcloud/all-in-one` project that lets a non-coding IT operator drive customer deployments via a future Claude Code session. Your job in **this** session is to build the repo that makes that future session possible: the scripts, CI workflows, container definitions, Packer templates, Dockerfile, management-server skeleton, and everything in between.

**You are not the operator.** `CLAUDE.md` describes a guardrail system for *future* operator sessions. Its allow-list and `OVERRIDE:` keyword constrain what a non-coding operator can do; they do not constrain you during initial build. This is authorized explicitly by `CLAUDE.md` §0 (Mode check) — read §0 in full before you read anything else in CLAUDE.md, then come back here. You are an engineer doing engineering work with full permission to create any file in the repo layout specified by `RESEARCH_REPORT.md` §4, subject only to the narrow list of things that remain forbidden even in bootstrap mode (`CLAUDE.md` §0.4).

**But the spirit of CLAUDE.md must still hold.** Every file you create must be *consistent with* CLAUDE.md so that when the operator-phase begins, the rules in CLAUDE.md actually work. Concretely: if CLAUDE.md references a script, you must create that script. If CLAUDE.md references a forbidden path, you must not put operator-editable content inside it. If the CI guard `check-forbidden-paths.sh` is referenced, it must exist and actually enforce the globs CLAUDE.md lists.

---

## 2. Reading order

Read the MDs in this order before writing anything:

1. **`CLAUDE.md` §0 first**, then the rest of CLAUDE.md. §0 is the Mode check and authorizes bootstrap mode. §0.4 lists what remains forbidden even during bootstrap — those rules apply to you in this session. §1–§9 do NOT apply to you during bootstrap (§0.2 says so explicitly), but you will later implement them, so understand them as specifications rather than as constraints on your current session.
2. **`RESEARCH_REPORT.md`** — the architecture. §4 gives you the repo layout. §3 is the customization map. §6 is the deployment pipeline. §9 is the management server. This is your blueprint.
3. **`README.md`** — the operator's view. Tells you which flows must work end-to-end.
4. **`MERGE_PROCEDURE.md`** — tells you exactly what `scripts/merge-upstream.sh` must do.
5. **`INCIDENT_PLAYBOOK.md`** — tells you which `mgmt-ctl` commands exist and what they do.
6. **`MGMT_CTL_CLI_SPEC.md`** — the full CLI surface. Use as the spec for the CLI.
7. **`MANAGEMENT_SERVER.md`** — the server architecture. Tables, endpoints, agent protocol.
8. **`OPERATOR_TASKS.md`** — cheat-sheet; skim. Everything here is already in CLAUDE.md + README.md.

After reading, re-read `RESEARCH_REPORT.md` §12 (Next steps). Those are the recommended build order in one place.

Do not skim. These documents cross-reference each other; missing a cross-reference now costs you in rework later.

---

## 3. What you are building

A git repository whose tree matches `RESEARCH_REPORT.md` §4. At minimum it includes:

- The eight input MDs, placed at their canonical paths (§5.3 below).
- `upstream/` as a git subtree of `nextcloud/all-in-one@main`, pinned to a specific SHA.
- `scripts/` — `merge-upstream.sh`, `bootstrap.sh`, `check-forbidden-paths.sh`, `install-hooks.sh`, `deploy-staging.sh`, `apply-smb.py`, `Dockerfile.base`, plus `packer/` and `smoke-test/` subtrees.
- `customization/` — `overlays/`, `community-containers/` (customer-agent, litellm, ollama), `apps/branding-default/`, `flavors/default/`, `flavors/law-firm/`, `customers/example-customer/`.
- `.github/workflows/` — `staging-deploy.yml` and `upstream-sync.yml`.
- `management-server/` — FastAPI skeleton, Postgres schema, agent register endpoint, a handful of command kinds, per §7 below.
- `compose.yaml` — repo-root Compose file that includes upstream + overlay.
- `.gitignore`.

You are **not** building:
- A production-grade management server. Build a skeleton that runs and has the right shape; leave the heavy implementation for later sprints.
- The `mgmt-ctl` Go binary. Produce the directory, a main.go with the command tree stubbed, and a Makefile; do not implement every command.
- Customer-agent runtime code beyond a minimal Go binary that registers and heartbeats. No command execution logic in this session.
- Real secrets, real deploy keys, real DNS. Placeholders throughout.

---

## 4. Build phases

Work in four phases. **Stop at each phase boundary and summarize to the engineer before proceeding to the next.** Each phase is one logical commit (or a small stack of related commits).

### Phase 0 — Repo setup (10 minutes)

1. If `.git` does not exist, `git init` with `main` as the default branch.
2. Create the directory skeleton from `RESEARCH_REPORT.md` §4.
3. Move the eight handed-to-you MDs to their canonical paths (see §5.3 below).
4. Write a minimal `.gitignore` (secrets, build artifacts, decrypted `.secret` files, `__pycache__`, editor files).
5. Add `upstream/` as a git subtree from `https://github.com/nextcloud/all-in-one.git main --squash`.
6. First commit: `chore: initial repo scaffold + upstream subtree @ <short-sha>`.

**Gate:** before Phase 1, confirm to the engineer: tree structure, subtree SHA, and that `git log` shows two commits (the init commit + the subtree squash).

### Phase 1 — The MVP (most of the work)

Build the deployment and CI plumbing in this order. Each item is a separate commit on a branch called `phase-1-mvp`:

1. `scripts/check-forbidden-paths.sh` — enforce the globs in CLAUDE.md §5. Must pass `bash -n`. Run it against the current tree and verify it reports no violations.
2. `scripts/install-hooks.sh` — install pre-commit + commit-msg hooks that call `check-forbidden-paths.sh`. Run it; verify hooks exist in `.git/hooks/`.
3. `scripts/merge-upstream.sh` — per `MERGE_PROCEDURE.md`. Must pass `bash -n`. Run with `--dry-run` against the current subtree and verify it reports "no changes to pull" cleanly.
4. `scripts/bootstrap.sh` — per `CLAUDE.md` §3 recipes. Every recipe in §3 that mentions `bootstrap.sh` must be covered by a corresponding function. Must pass `bash -n`.
5. `scripts/apply-smb.py` — called by `bootstrap.sh` for SMB mounts. Must pass `python3 -m py_compile`.
6. `scripts/Dockerfile.base` — the base image referenced by the CI workflow. Multi-stage, non-root where possible. Buildable (but don't push in this session).
7. `scripts/deploy-staging.sh` — called by the CI workflow. Must pass `bash -n`.
8. `customization/overlays/docker-compose.override.yaml` — per `RESEARCH_REPORT.md` §6. Must pass `docker compose config` when combined with the upstream `compose.yaml`.
9. `compose.yaml` at repo root — includes upstream + overlay via `include:`.
10. `customization/community-containers/customer-agent/` — JSON + readme. JSON must validate against `upstream/php/containers-schema.json` (use `ajv` if available, else `python -c "import json; json.load(open('...'))"`).
11. `customization/community-containers/litellm/` — same as above.
12. `customization/community-containers/ollama/` — same as above.
13. `customization/flavors/default/` — `flavor.env` + `custom.css`.
14. `customization/flavors/law-firm/` — `flavor.env` + `custom.css`.
15. `customization/customers/example-customer/` — `customer.env` + `custom.css` + `smb-mounts.yaml` + placeholder `logo.svg` and `background.jpg`.
16. `customization/apps/branding-default/` — `appinfo/info.xml`, `lib/AppInfo/Application.php`, `js/main.js`, `css/main.css`. info.xml must parse as valid XML.
17. `scripts/packer/aio-base.pkr.hcl` + `scripts/packer/files/first-boot.sh` + `first-boot.service` + `90-customer.cfg`.
18. `scripts/smoke-test/test_staging.py` + `requirements.txt`. Must pass `python3 -m py_compile`.
19. `.github/workflows/staging-deploy.yml` — must pass `yamllint` (if available) and `actionlint` (if available).
20. `.github/workflows/upstream-sync.yml` — same.
21. `scripts/build-base-image.sh` — builds `ghcr.io/<org>/aio-base:<git-sha>` per `RESEARCH_REPORT.md` §6. Called by the base-image-build workflow; referenced by CLAUDE.md §5 as a locked path. Must pass `bash -n`. Do not push the image in this session.
22. `.github/workflows/base-image-build.yml` — triggers on push to `main` that touches `scripts/Dockerfile.base`, `customization/community-containers/**`, or `customization/apps/**`. Calls `scripts/build-base-image.sh` and pushes the resulting image to `ghcr.io` on `main` only (not on PRs). Must pass `yamllint` / `actionlint` if available.
23. `customization/overlays/Caddyfile` — per `RESEARCH_REPORT.md` §4. Placeholder suitable as a fallback reverse-proxy when Cloudflare Tunnel is not used. Tracked so operators can customize per-customer via an override.
24. `docs/templates/cloudflared.yml.template` — the template referenced by CLAUDE.md §3.1 step 2 for new Cloudflare Tunnel setups. Tokenized placeholders (`<TUNNEL_ID>`, `<HOSTNAME>`, `<SERVICE>`).

**Gate:** before Phase 2, run all validators again end-to-end. Produce a one-paragraph summary of file count, line count, what passed validation, what you couldn't validate (and why), and any open questions. Commit the branch, push if a remote is configured, and wait for engineer approval.

### Phase 2 — Management server skeleton

Build on branch `phase-2-mgmt-skeleton`:

1. `management-server/app/__init__.py` — empty package marker.
2. `management-server/app/main.py` — FastAPI app factory. Wires routers from §7 below.
3. `management-server/app/db.py` — SQLAlchemy engine + session factory, Postgres DSN from env.
4. `management-server/app/models/` — SQLAlchemy models for the tables in `MANAGEMENT_SERVER.md` §3. One file per table (`customers.py`, `agents.py`, `commands.py`, `audits.py`, `users.py`, `flavors.py`, `features.py`, `feature_bindings.py`, `base_images.py`).
5. `management-server/app/auth/` — OIDC session issuance, JWT verify middleware. Stub the IdP config behind env vars; no real IdP wiring.
6. `management-server/app/security/` — security middleware stubs referenced by CLAUDE.md §5 (locked path): `csp.py` (Content-Security-Policy header injector), `csrf.py` (double-submit cookie for cookie-authed endpoints), `ratelimit.py` (per-identity token bucket stub). Stubs must be wired into `main.py`'s middleware stack even if they no-op by default, so that later hardening has a clear insertion point.
7. `management-server/app/routers/` — one file per endpoint group. Implement `customers` (list, show, create), `agents` (register, tick), `commands` (get, result) fully. Stub the rest (return 501 Not Implemented with the right shape).
8. `management-server/app/rbac.py` — the three roles from `MANAGEMENT_SERVER.md` §6, expressed as decorators. Every write endpoint is decorated.
9. `management-server/alembic/` — initial migration that creates all tables from §3.
10. `management-server/Dockerfile` — multi-stage; non-root; `uvicorn` as entrypoint.
11. `management-server/compose.yaml` — dev-mode: FastAPI + Postgres + MinIO.
12. `management-server/pyproject.toml` — dependencies pinned.
13. `management-server/tests/` — a handful of tests: agent register happy path, customer create, RBAC denial. Use `pytest` + `httpx.AsyncClient`.
14. `management-server/README.md` — already exists from the handoff. Verify it still reflects what you built; add a "Running locally" section at the bottom.

**Gate:** before Phase 3, run `pytest` and confirm the tests pass against a local compose. Produce a summary as before.

### Phase 3 — mgmt-ctl CLI skeleton

Build on branch `phase-3-cli`:

1. `management-server/cli/main.go` — cobra-based CLI. Command tree from `MGMT_CTL_CLI_SPEC.md`.
2. `management-server/cli/pkg/client/` — HTTP client for the management API.
3. `management-server/cli/pkg/auth/` — OIDC device-code flow for `mgmt-ctl login`.
4. Fully implement: `login`, `logout`, `whoami`, `customers list`, `customers show`, `customers create`, `enroll`, `backup`, `upgrade`, `rollback`. Stub the rest (exit 1 with "not implemented in Phase 3").
5. `management-server/cli/Makefile` — `make build` → static binary at `bin/mgmt-ctl`.
6. `management-server/cli/README.md` — quickstart. Reference `MGMT_CTL_CLI_SPEC.md` as the spec.

**Gate:** before Phase 4, `make build` produces a binary that runs `--help` cleanly and `mgmt-ctl login` kicks off the device-code flow against a mock IdP.

### Phase 4 — Handoff

1. Update the top-level `README.md` (the operator one) with a new top section: "First-time setup for engineering" pointing at the follow-on docs.
2. Write `docs/ONBOARDING.md` — step-by-step for an engineer onboarding a new customer end-to-end (create customer folder, generate registration token, build customer image, deploy, verify).
3. Write `docs/STAGING_SETUP.md` — how to stand up the staging Linux server the CI workflow deploys to (Docker install, secrets, first deploy).
4. Write `docs/postmortems/README.md` — template for postmortem writeups referenced from `INCIDENT_PLAYBOOK.md`.
5. Move **this file** (`BOOTSTRAP.md`) to `docs/BOOTSTRAP_HISTORY.md` in a commit whose subject line begins exactly `chore: archive BOOTSTRAP.md` (CLAUDE.md §0.1 condition 3 uses this as the mode-switch marker; any other subject will leave future sessions stuck in bootstrap mode forever). Add a note at the top of the archived file: "This file was the one-shot bootstrap instruction consumed at repo creation on <date>. It is archived for traceability; do not run it again."
6. Squash-merge phase branches into `main` in order. Tag the repo `v0.1.0-scaffold`.

**Gate:** summarize the final state. Count: files, lines, validators passed, tests passing. List open TODOs. Hand back to engineer.

---

## 5. Quality gates

Run these continuously, not just at phase boundaries.

### 5.1 Syntactic validation

Every time you create or edit a file, run the matching validator before moving on:

- `.sh`  → `bash -n <file>`
- `.py`  → `python3 -m py_compile <file>`
- `.json` → `python3 -c "import json; json.load(open('<file>'))"`
- `.yaml` / `.yml` → `python3 -c "import yaml; yaml.safe_load(open('<file>'))"` (install PyYAML if missing)
- `.xml` → `python3 -c "import xml.etree.ElementTree as ET; ET.parse('<file>')"`
- GitHub Actions YAML → if `actionlint` is available, run it; otherwise just the YAML parse.
- HCL (Packer) → if `packer` is available, `packer validate`; else skip with a note.
- `Dockerfile*` → if `hadolint` is available, run it; else skip.

If a validator fails, fix before moving on. Do not pile up errors.

### 5.2 Cross-document consistency

After each phase, verify:
- Every file CLAUDE.md §3 references actually exists at the path it names.
- Every command `mgmt-ctl` exposes per `MGMT_CTL_CLI_SPEC.md` has a corresponding route in `management-server/app/routers/` (stubs are fine in Phase 2; full impl in Phase 3 or later).
- Every forbidden path glob in CLAUDE.md §5 is matched by `check-forbidden-paths.sh`.
- Every `occ` command referenced in `bootstrap.sh` is on the allow-list in `MANAGEMENT_SERVER.md` §4.3.

If you find a mismatch, the **document is probably right and your implementation is wrong.** Fix the implementation. Only adjust the document if you discover the document contradicts itself.

### 5.3 Canonical paths for the handed-to-you MDs

Move them in Phase 0:

| Input filename | Goes to |
|---|---|
| `CLAUDE.md` | `CLAUDE.md` (repo root) |
| `README.md` | `README.md` (repo root) |
| `RESEARCH_REPORT.md` | `docs/RESEARCH_REPORT.md` |
| `MERGE_PROCEDURE.md` | `docs/MERGE_PROCEDURE.md` |
| `INCIDENT_PLAYBOOK.md` | `docs/INCIDENT_PLAYBOOK.md` |
| `OPERATOR_TASKS.md` | `docs/OPERATOR_TASKS.md` |
| `MANAGEMENT_SERVER.md` | `management-server/README.md` |
| `MGMT_CTL_CLI_SPEC.md` | `management-server/CLI_SPEC.md` |

Do not edit the content of the handed-to-you MDs during bootstrap. If you find something inconsistent, raise it to the engineer at the next gate — do not silently "fix" it.

---

## 6. Git hygiene

- One logical change per commit. A commit is either a single file creation, or a tightly-related set (e.g., a community container's JSON + readme + included in the overlay).
- Commit messages: conventional-commit style. `feat(scripts):`, `chore(ci):`, `docs(handoff):`, `fix(bootstrap):`.
- Branch names: `phase-0-scaffold`, `phase-1-mvp`, `phase-2-mgmt-skeleton`, `phase-3-cli`, `phase-4-handoff`.
- Do not rewrite history after a phase gate. Amending commits within an uncommitted phase is fine.
- Do not push to a remote unless the engineer told you a remote exists.
- Do not run `git commit --no-verify` unless the engineer explicitly asks for it after the hooks are installed.

---

## 7. When to stop and ask the engineer

Ask before doing any of these. Do not assume:

- Anything that requires network beyond `git fetch` from upstream and `pip install` / `npm install` for tooling (e.g., pushing images, creating cloud resources, opening PRs on GitHub).
- Anything that writes outside the repo (`sudo`, installing system packages, editing `/etc/`, creating Docker volumes on the host).
- Anything involving real secrets (tokens, API keys, certs). Always use placeholders and flag them in a TODO list at the end of the phase.
- Any deviation from what the MDs specify. If you think a doc is wrong, say so at the next gate — don't just improvise.
- Any decision the MDs explicitly mark as "open questions" (see `RESEARCH_REPORT.md` §11). Examples: which VM image formats to commit to, whether airgapped is in scope, NC version target. If one of these blocks progress, stop and ask.

Also ask if you're about to spend more than 30 minutes on a single file. Long files usually mean the scope is wrong.

---

## 8. Anti-patterns (do not do these)

1. **Writing code first, reading docs later.** The docs are the spec. Read before writing.
2. **Inventing command names or file paths.** If CLAUDE.md says `scripts/merge-upstream.sh`, that's the path. Don't "improve" it to `scripts/upstream/merge.sh`.
3. **Expanding scope.** The management server skeleton in Phase 2 is deliberately minimal. Do not implement feature flags, bulk enqueue, or branding uploads. Those are later sprints.
4. **Fabricating CLI output.** If `actionlint` is not installed, say so and skip; do not pretend you ran it and passed.
5. **Skipping the validators.** They take seconds and catch most of your mistakes. Run them.
6. **Ignoring CLAUDE.md's forbidden-path globs when creating files.** For example, do not accidentally make `management-server/auth/` contain non-security code. The globs are there because those paths will be locked in operator mode; keep them tight now so the lock works later.
7. **Copy-pasting from the research report into implementation files without thinking.** The report shows patterns and examples; your implementation must be complete and internally consistent, not pattern-matched.
8. **Interpreting "stub" as "empty file."** A stub is a working placeholder: a function that returns 501 with the right shape, a test that asserts the stub returns 501, a command that prints "not yet implemented in this phase." Empty files are not stubs.

---

## 9. How you should behave this session

- Before editing or writing, describe what you are about to do in 1–4 sentences.
- Prefer small edits to big ones. Prefer many small commits to few big commits.
- When a validator fails, show the error, explain the fix, then fix it. Don't hide failures.
- When a doc contradicts itself or is unclear, say so and ask. Do not guess.
- At phase gates, produce a short structured summary: files created, files modified, commits, what passed validation, what was skipped, open questions. Hand off to the engineer; don't proceed past a gate unilaterally.
- If the engineer asks you to deviate from this document, comply and note the deviation in the phase summary so future Claude sessions can see why the repo doesn't match the spec.

---

## 10. The transition to operator mode

When Phase 4 completes:

1. `BOOTSTRAP.md` gets moved to `docs/BOOTSTRAP_HISTORY.md` (per Phase 4 step 5).
2. A future Claude Code session opening this repo will find `CLAUDE.md` at the root, read it, and treat itself as operating in *operator mode*.
3. All the rules in CLAUDE.md — the allow-list, the deny-list, the `OVERRIDE:` keyword — take effect immediately. Every file you created in Phases 0–3 is now protected by the rules you helped enforce.
4. The engineer (not you) will be the one to add new capabilities over time, by editing CLAUDE.md (a locked file) via engineering-reviewed PRs that ship alongside new scripts or community containers.

Your last act in this session is to verify the mode transition is clean: run a fresh `git clone` of the resulting repo in a scratch dir, open a Claude Code session there, and ask it "what can I do?" — it should read CLAUDE.md, describe the allow-list, and refuse to edit `upstream/`. If it misbehaves, the bug is in CLAUDE.md or the guard script, and you should fix it before the handoff.

---

**Proceed with Phase 0 when ready.**
