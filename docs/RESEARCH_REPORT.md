# Nextcloud AIO Private Fork — Research Report & Architecture Plan

**Status:** Draft for review
**Scope:** Strategy for maintaining a private fork of `nextcloud/all-in-one`, customizing it per customer, and operating it via Claude Code driven by a non-coding IT operator.
**Upstream reference:** <https://github.com/nextcloud/all-in-one>

---

## 1. Executive summary

Nextcloud All-in-One (AIO) is the official turnkey Nextcloud deployment. It is built around a **mastercontainer** orchestration pattern: a PHP application that reads a declarative `php/containers.json`, talks to the Docker socket, and spins up all the downstream containers (Nextcloud, Apache, Postgres, Redis, Talk, Collabora, etc.). This architecture turns out to be unusually friendly to the use case described in the brief — customizing per customer, deploying as an image, and merging upstream regularly — **provided we do not fork by modifying upstream files.**

The central recommendation of this report is: **do not maintain a patched fork of upstream. Instead, treat upstream as an unmodified git subtree (or vendored submodule) and add everything custom in overlay directories.** Every customization surface the brief asks for is reachable through supported extension points: community container JSONs, `docker-compose.override.yaml`, environment variables documented by upstream, the Nextcloud theming app, the `theming_customcss` app, Nextcloud apps from the app store, and `NEXTCLOUD_EXEC_COMMANDS` / `NEXTCLOUD_STARTUP_APPS` / `NEXTCLOUD_ADDITIONAL_APKS`. Merge conflicts with upstream approach zero as a direct consequence.

The IT operator workflow is gated by a `CLAUDE.md` with an explicit allow-list of tasks. Anything outside the allow-list fails closed unless the operator types an `OVERRIDE:` keyword at the start of their message, which Claude Code is instructed to refuse when missing. This gives the operator a forgiving environment for supported tasks (branding, Cloudflare tunnels, CSS/JS tweaks, enabling community containers, Exchange/SMB integration, AI/LLM features) and a hard brake for anything that could destabilize the app, weaken security posture, or break the upstream merge.

Deployment uses a two-stage image pipeline: a **base image** built nightly from the current customer-agnostic state of our fork, and a **customer image** built per customer by layering their environment on top at build time — or, preferably, by running the same base image with a per-customer `.env` + `docker-compose.override.yaml` and a bootstrap script that applies branding and integrations on first boot. Docker and VM (cloud-init-driven) variants use the same bootstrap script. A GitHub Action runs on every merge to `main`, builds the base image, and deploys it to a staging Linux server for smoke testing before customer rollouts.

A lightweight **management server** — a small Django/FastAPI service plus an agent container running inside each customer instance — gives the team a single pane of glass to enable features, push upgrades, and run maintenance jobs across the fleet.

The rest of this document walks through the findings from the upstream repository, explains what is already solved versus what we need to build, and lays out the repo structure, branching model, bootstrap flow, and management-server design in enough detail for implementation.

---

## 2. What the upstream repo actually is

The upstream repository hosts three things worth distinguishing:

**(a) The mastercontainer source code.** The `php/` directory is a Slim-framework PHP app that the mastercontainer runs. It reads `php/containers.json` — a declarative description of every service in the stack validated by `php/containers-schema.json` — and then talks to `/var/run/docker.sock` to create, start, stop, and update those containers. It also serves the AIO web interface on ports 8080 (self-signed) and 8443 (ACME-issued) and writes its own config to the `nextcloud_aio_mastercontainer` Docker volume as `configuration.json`. This is the part that is least safe to modify in a fork; patching PHP files here will conflict on nearly every upstream merge.

**(b) Container definitions in `php/containers.json`.** Every downstream container — `nextcloud-aio-nextcloud`, `nextcloud-aio-apache`, `nextcloud-aio-postgresql`, `nextcloud-aio-redis`, `nextcloud-aio-talk`, `nextcloud-aio-collabora`, `nextcloud-aio-imaginary`, `nextcloud-aio-clamav`, `nextcloud-aio-fulltextsearch`, `nextcloud-aio-whiteboard`, `nextcloud-aio-notify-push`, `nextcloud-aio-docker-socket-proxy` — is a JSON object in this file. Each entry specifies image, image_tag (usually `%AIO_CHANNEL%`), environment variables, volumes, ports, depends_on, optional `nextcloud_exec_commands` to run inside the Nextcloud container after startup, a `backup_volumes` flag, healthcheck config, and a `profiles` array that ties the container to a feature flag. Optional services like Talk, Collabora, and ClamAV live behind profiles and are only instantiated when the operator flips the corresponding feature in the AIO web interface. Editing this file to add customer-specific services is tempting; we should not, because every upstream release updates it.

**(c) The community-containers extension point.** `community-containers/<name>/<name>.json` is the *supported* way to add containers outside upstream's curated list. Each definition follows the same schema as `containers.json`. The mastercontainer reads the community directory at startup and exposes the containers in the AIO web UI under a "Show/Hide available Community Containers" section (AIO 11.0.0+). The env var `AIO_COMMUNITY_CONTAINERS="name1 name2"` enables them from the docker run line or Compose file. Crucially, the upstream maintainer has publicly confirmed you can bind-mount your own directory into `/var/www/docker-aio/community-containers/` and register JSONs there — meaning we can ship our own containers without upstreaming them. This is the hook we will rely on heavily.

**Other upstream features worth noting for our plan:**

- `manual-install/` — a `docker-compose.yaml` generator (`update-yaml.sh`) that transforms `containers.json` into a plain Compose file, usable without the mastercontainer at all. If the mastercontainer ever becomes a blocker, this is our escape hatch.
- `nextcloud-aio-helm-chart/` — the official Helm chart. Not a priority for our VM/Docker workflow but useful for future Kubernetes customers.
- `compose.yaml` at repo root — the **recommended** way to run the mastercontainer in production. Environment variables on the mastercontainer (`NEXTCLOUD_DATADIR`, `NEXTCLOUD_MOUNT`, `NEXTCLOUD_UPLOAD_LIMIT`, `NEXTCLOUD_MAX_TIME`, `NEXTCLOUD_MEMORY_LIMIT`, `NEXTCLOUD_STARTUP_APPS`, `NEXTCLOUD_ADDITIONAL_APKS`, `NEXTCLOUD_ADDITIONAL_PHP_EXTENSIONS`, `NEXTCLOUD_TRUSTED_CACERTS_DIR`, `AIO_COMMUNITY_CONTAINERS`, `TALK_PORT`, `SKIP_DOMAIN_VALIDATION`, `WATCHTOWER_DOCKER_SOCKET_PATH`, plus hardware-accel flags) are the **entire documented customization surface at the mastercontainer level**. Anything you need to configure per-customer outside of the AIO web UI goes here.
- `reverse-proxy.md` — the canonical doc for running AIO behind any reverse proxy, including Cloudflare Tunnel, Caddy, Nginx, Traefik, and Apache.
- `migration.md` — documents migrating from legacy Nextcloud installs to AIO and between AIO instances. Relevant for onboarding customers who already self-host.

---

## 3. Mapping the brief's requirements to upstream's extension points

The brief lists a set of customizations the IT operator will need to do routinely. Every one of them maps to a supported extension point — which is the whole reason fork-as-subtree works.

### 3.1 Cloudflare Tunnel for serving the web UI

Already supported. Upstream's own docs state that "from AIO perspective a Cloudflare Tunnel works like a reverse proxy," so the standard reverse-proxy configuration applies: run the mastercontainer with `--env APACHE_PORT=11000 --env APACHE_IP_BINDING=127.0.0.1` (or whatever fits the environment), then configure the `cloudflared` tunnel to route the customer domain to `http://127.0.0.1:11000`. Upstream also ships a `community-containers/caddy/` definition that can serve as a TLS-terminating reverse proxy in front of AIO. Nothing in upstream needs to be modified to support this.

**Caveats we must tell customers** (lifted from upstream): Cloudflare performs TLS termination, so the traffic is decrypted on Cloudflare's side; the free plan caps uploads at 100 MB without chunking; Cloudflare's 100-second request cap means very large uploads will fail unless the proxy is bypassed; the built-in TURN server for Talk does not work through Cloudflare Tunnel; Collabora needs the Cloudflare IP ranges added to its WOPI allowlist to work; and Cloudflare's Rocket Loader breaks Nextcloud's login prompt and must be disabled. These are not bugs we can fix — they are Cloudflare limitations. The CLAUDE.md we write will flag them when the operator enables the Cloudflare flow.

**Our overlay:** A `cloudflared` service in `docker-compose.override.yaml`, a Cloudflare tunnel token in the customer `.env`, and a bootstrap step that registers the tunnel and applies the four "Cloudflare hygiene" settings (WOPI allowlist, Rocket Loader reminder, chunking config, TURN recommendation) via `occ` commands. No upstream files touched.

### 3.2 UI changes: CSS, JS, branding

Nextcloud has three layers of customization, from least to most invasive:

1. **Built-in Theming app.** Enabled by default. Covers the name, web link, slogan, primary color, background image, logo, and favicon. All settable via `occ theming:config <key> <value>`, so we can script them from the bootstrap script and drive them from customer `.env` vars (`CUSTOMER_NAME`, `CUSTOMER_PRIMARY_COLOR`, etc.). No code changes needed.
2. **`theming_customcss` app.** Official Nextcloud app that adds a text field for arbitrary CSS, stored in the `oc_appconfig` table. Settable via `occ config:app:set theming_customcss customcss --value "..."`. This is the right place for customer-specific CSS tweaks and the hook for all the "make the UI look like the customer's brand" work. The bootstrap script reads `/customization/<customer>/custom.css` and pipes it in.
3. **Custom JS** is trickier. Nextcloud does not expose a first-class custom-JS text field for security reasons. The supported paths are: (a) install a custom Nextcloud app that registers scripts via `\OCP\Util::addScript`, or (b) drop a CSP-compatible script tag into a custom theme bundled as an app. We recommend maintaining a small internal "branding" Nextcloud app per deployment flavor, living in `/customization/apps/branding-<flavor>/`, that loads any needed JS. This app is installed during bootstrap via `occ app:install` pointing at the directory. Because it is our code, not upstream's, merges never touch it.

For full rebranding — changing the name everywhere, replacing email logos, setting imprint/privacy URLs — the Theming app + `theming_customcss` + our branding app is sufficient for web UI. **Branded mobile and desktop clients** are a paid Nextcloud Enterprise service (MSI, MDM packages for iOS/Android); the brief should note this is not something we can produce from the fork alone. For customers who need branded clients, we either sell the Enterprise subscription separately or accept the unbranded clients.

### 3.3 Self-hosted Microsoft Exchange integration

Two realistic paths:

- **`ksainc/integration_ews`** — open-source, on the Nextcloud app store, bidirectional sync of contacts, calendars, and tasks via EWS. Supports Exchange 2007–2022, Exchange Online, Kerio Connect, SmarterMail. Installed via `occ app:install integration_ews`. Per-user auth (hostname, username in `user@domain` or `DOMAIN\user` form, password) through the user's Personal Settings. Good enough for most customers. Our bootstrap installs it; the operator configures Exchange credentials per-user via the UI.
- **Sendent / Nextcloud Exchange Connector** — commercial, more polished, covers free/busy and meeting scheduling in addition to calendars and contacts. Appropriate for customers with a budget.

Nextcloud's built-in **Mail** app can talk to Exchange over IMAP/SMTP if EWS is not needed. For CalDAV/CardDAV-style read-only visibility, the Calendar app can subscribe to a read-only feed if the Exchange admin exposes one.

Our overlay: an env flag `ENABLE_EXCHANGE_INTEGRATION=true` that triggers `occ app:install integration_ews` in bootstrap. No upstream changes.

### 3.4 Windows SMB connections

Already first-class. `smbclient` is bundled in the Nextcloud container by upstream ("`ffmpeg`, `smbclient` and `nodejs` are included by default"). The built-in **External Storage Support** app (shipped in core Nextcloud) supports SMB/CIFS mounts — per-user, per-group, or admin-wide — authenticated with a static credential, session credential, or Kerberos. Scripted via `occ files_external:create`, `occ files_external:config`, and `occ files_external:option`.

For **CIFS-mounted data directories**, upstream documents mounting the SMB share into the host via `/etc/fstab` and then pointing `NEXTCLOUD_DATADIR` at the mount point. This is a host-level config change, which we can do at VM-image build time via cloud-init.

Our overlay: an env-flag-gated section in bootstrap that reads `SMB_MOUNTS_YAML` and calls `occ files_external:*` for each. No upstream changes.

### 3.5 Rebranding

Covered by 3.2. Explicit mapping from `.env` variables to `occ theming:config` calls:

```
CUSTOMER_NAME              → occ theming:config name
CUSTOMER_SLOGAN            → occ theming:config slogan
CUSTOMER_URL               → occ theming:config url
CUSTOMER_PRIMARY_COLOR     → occ theming:config color
CUSTOMER_LOGO_PATH         → occ theming:config logo <file>
CUSTOMER_BACKGROUND_PATH   → occ theming:config background <file>
CUSTOMER_IMPRINT_URL       → occ theming:config imprintUrl
CUSTOMER_PRIVACY_URL       → occ theming:config privacyUrl
```

Plus `occ config:app:set theming_customcss customcss --value "$(cat /customization/$CUSTOMER/custom.css)"`.

### 3.6 AI / LLM features

Upstream already ships `community-containers/local-ai/` (LocalAI) as an official community container, giving us an OpenAI-compatible inference endpoint running next to Nextcloud. The **Nextcloud Assistant** app plus **`integration_openai`** ("OpenAI and LocalAI integration") connects to LocalAI, Ollama, or any OpenAI-compatible endpoint (IONOS, Together, Mistral, Groq). For non-OpenAI-shaped APIs (Claude direct, Bedrock, Vertex), a LiteLLM proxy sidecar acts as a translation layer — this is a standard pattern and we ship it as a custom community container.

Pieces we install from bootstrap:

- Nextcloud apps: `assistant`, `integration_openai`, optionally `context_chat`, `stt_whisper`, `translate` (for translation provider).
- Community container: `local-ai` (from upstream's community-containers dir) or our own `ollama` / `litellm` community container JSONs.
- Env vars: `AI_PROVIDER=localai|ollama|openai|litellm`, `AI_ENDPOINT_URL`, `AI_API_KEY` (encrypted at rest in our management DB), `AI_DEFAULT_MODEL`.
- `occ` configs: `occ config:app:set integration_openai url --value "..."`, etc.

For Nextcloud 30+, upstream recommends running an "AI worker" systemd service to speed up AI task pickup beyond the default cron interval. If we're targeting Nextcloud 30+ we should add this to the bootstrap.

### 3.7 Summary table

| Requirement | Upstream support | Our overlay adds |
|---|---|---|
| Cloudflare Tunnel | Documented reverse proxy mode | `cloudflared` service, hygiene `occ` commands |
| UI CSS | `theming_customcss` app | Per-customer `custom.css` file + bootstrap install |
| UI JS | None native — needs a custom app | `apps/branding-<flavor>/` mini-app + bootstrap install |
| Rebranding | Theming app + `theming_customcss` | Env-var-driven `occ theming:config` calls |
| Exchange integration | `ksainc/integration_ews` on app store | Env-gated `occ app:install` + per-user config |
| Windows SMB | External Storage app + `smbclient` in container | Env-driven `occ files_external:*` calls |
| AI / LLM | LocalAI community container, Assistant app, `integration_openai` | LiteLLM/Ollama custom community containers + bootstrap configs |
| Adding a new container | Community containers JSON schema | Our community containers in `customization/community-containers/` |
| Extra Alpine packages | `NEXTCLOUD_ADDITIONAL_APKS` env | Per-customer `.env` entry |
| Extra PHP extensions | `NEXTCLOUD_ADDITIONAL_PHP_EXTENSIONS` env | Per-customer `.env` entry |
| Upload limits, memory, timeouts | `NEXTCLOUD_*` env vars | Per-customer `.env` entry |
| Default apps installed | `NEXTCLOUD_STARTUP_APPS` env | Per-flavor `.env` defaults |

Everything is env-vars and overlays. Nothing in this table requires editing upstream code.

---

## 4. Repository layout

The fork is organized so that `upstream/` is a git subtree that we treat as read-only. Everything else is ours.

```
nextcloud-aio-private/
├── upstream/                         # git subtree of nextcloud/all-in-one@<pinned>
│   └── (DO NOT MODIFY — used read-only, re-synced via scripts/merge-upstream.sh)
├── customization/
│   ├── community-containers/         # our custom containers (same schema as upstream)
│   │   ├── litellm/
│   │   │   ├── litellm.json
│   │   │   └── readme.md
│   │   ├── ollama/
│   │   └── customer-agent/           # the management-server agent (see §9)
│   ├── apps/
│   │   └── branding-default/         # our custom NC app for JS and deep branding
│   ├── flavors/                      # per-flavor defaults (small, medium, large, law-firm, etc.)
│   │   ├── default/
│   │   │   ├── flavor.env
│   │   │   ├── custom.css
│   │   │   └── logo.svg
│   │   └── law-firm/
│   ├── customers/                    # per-customer overlays (gitignored secrets, public config tracked)
│   │   └── acme-corp/
│   │       ├── customer.env          # tracked, no secrets
│   │       ├── customer.env.secret.age  # age-encrypted
│   │       ├── custom.css
│   │       ├── logo.svg
│   │       └── cloudflared.yml
│   └── overlays/
│       ├── docker-compose.override.yaml
│       └── Caddyfile
├── scripts/
│   ├── merge-upstream.sh             # safe subtree pull + conflict check
│   ├── bootstrap.sh                  # applied at first boot / post-deploy
│   ├── build-base-image.sh           # builds the single customer-agnostic base image
│   ├── deploy-staging.sh
│   ├── check-forbidden-paths.sh      # operator-mode guard; see CLAUDE.md §5
│   ├── install-hooks.sh
│   ├── apply-smb.py                  # called by bootstrap.sh for SMB mounts
│   ├── Dockerfile.base
│   ├── packer/                       # VM image build (qcow2/vmdk/raw)
│   └── smoke-test/                   # post-deploy staging smoke tests
├── management-server/                # FastAPI + Postgres + Go CLI; see §9. The operator CLI
│                                     # `mgmt-ctl` is a single static Go binary at
│                                     # management-server/cli/, NOT a shell wrapper in scripts/.
├── .github/
│   └── workflows/
│       ├── staging-deploy.yml
│       ├── base-image-build.yml
│       └── upstream-sync.yml
├── docs/
│   ├── RESEARCH_REPORT.md            # this file
│   ├── OPERATOR_TASKS.md
│   ├── MERGE_PROCEDURE.md
│   ├── INCIDENT_PLAYBOOK.md
│   └── templates/
│       └── cloudflared.yml.template  # referenced by CLAUDE.md §3.1
├── CLAUDE.md                         # the IT operator gate — see §7
├── README.md                         # the IT operator runbook
└── compose.yaml                      # entry point: includes upstream + overlays
```

The thing that makes this repo merge-safe is the one-way data flow: upstream → `upstream/`. We never write into `upstream/`. Customizations live in `customization/` and compose together at runtime. If an upstream release renames `containers.json` or the schema, we find out by running the integration test on the staging server (§8), not by getting a merge conflict.

---

## 5. Fork strategy: subtree vs submodule vs patches

We evaluated three approaches:

**(a) Patched fork.** Traditional GitHub fork, rebase upstream's `main` onto ours periodically. Downside: every patch in our tree is a potential merge conflict. Bad fit for "IT operators making changes and merging upstream safely."

**(b) Git submodule.** `upstream/` as a submodule pinned to a SHA. Upside: cleanest mental model. Downside: submodules are operationally fussy — the IT operator has to remember `git submodule update --init --recursive`, CI gets weird, and building the image requires fetching the submodule at build time. Workable but not friendly.

**(c) Git subtree (recommended).** `upstream/` is a subtree managed via `git subtree pull --prefix=upstream/ https://github.com/nextcloud/all-in-one.git main --squash`. Upside: the subtree's contents live in our history like regular files (no extra tooling for cloners), the single `merge-upstream.sh` script does the pull, squash, and produces a conflict report, and rollback is a regular `git revert`. The recommended pattern.

The `scripts/merge-upstream.sh` wrapper does the heavy lifting:

1. Checks out a new branch `upstream-sync/<date>`.
2. Runs `git subtree pull --prefix=upstream/ ... --squash`.
3. If there is any conflict, fails loudly and prints which files conflict. Conflicts in `upstream/` are a red flag (someone modified `upstream/` which they should not have); conflicts outside `upstream/` indicate our overlays referencing a file that upstream renamed.
4. Runs `scripts/integration-test.sh` against the staging server.
5. Opens a PR with the upstream changelog pasted into the description.

This script is invoked either by the operator via Claude Code (`OVERRIDE:` is **not** required for merging upstream — merging is a first-class task) or automatically by the `.github/workflows/upstream-sync.yml` scheduled action.

---

## 6. Customer deployment: image pipeline and bootstrap

The current manual flow the brief describes — spin up an image, make changes, clone the image, deploy — is replaced by an automated pipeline.

**Base image (`ghcr.io/<org>/aio-base:<git-sha>` and `:latest`)** is rebuilt on every push to `main`. It bundles: the upstream `compose.yaml` + mastercontainer image, our `customization/community-containers/`, our `customization/apps/branding-<flavor>/` apps, the `bootstrap.sh` script at `/usr/local/bin/bootstrap-aio`, and the management-server agent. Crucially, the base image contains **no customer-specific data** — no logos, no CSS, no domain names, no API keys. It is identical across all customers.

**Customer deployment** is: `docker compose up -d` (or `virt-install` for VM) with a customer-specific `.env` file mounted and two customer-specific volumes attached (`customization/customers/<name>/` read-only, and the normal Nextcloud data volume). On first boot, the base image's entrypoint runs `bootstrap-aio`, which:

1. Reads the `.env` to determine `DEPLOYMENT_MODE=first-boot|update|recover`, customer name, flavor, feature flags.
2. Resolves defaults by merging `flavors/<flavor>/flavor.env` ← `customers/<name>/customer.env` ← process environment.
3. If `first-boot`: waits for Nextcloud to be reachable, runs `occ maintenance:install` equivalents, applies theming, installs customer-selected apps (`integration_ews`, `assistant`, `integration_openai`, `files_external`, etc.), configures SMB mounts, registers the Cloudflare tunnel, configures AI endpoints, seeds LDAP settings if applicable.
4. If `update`: runs `occ upgrade`, `occ db:add-missing-indices`, restarts relevant containers.
5. Registers the instance with the management server (one-time registration token).
6. Writes a done-marker to `/mnt/ncdata/.bootstrap-done-<version>` so reruns are idempotent.

The bootstrap script is written to be run multiple times safely. Every step is diff-aware (compute desired state, compare to actual, only act on diff).

**VM deployment** uses the same script. A small cloud-init or Ignition config at VM creation time installs Docker, pulls the base image, writes the customer `.env`, and starts `docker compose`. This is the vehicle for customers whose infrastructure is VMware, Proxmox, or bare metal where Docker-Machine provisioning is not a fit. We maintain a Packer template in `scripts/packer/` that bakes Docker + the base image + the bootstrap script into a qcow2/vmdk/raw. The Packer build reuses the same base image artifact, so the Docker and VM paths never drift.

**Streamlining the existing "clone-the-image" workflow.** The team's current motion — spin up an image, customize, clone, deploy — reappears almost verbatim in this pipeline, except "customize" becomes "populate a customer folder in `customization/customers/<name>/` and commit it," "clone" becomes the automated image-tagging step in CI, and "deploy" is a one-shot `mgmt-ctl deploy <customer>` command. The two wins: the customization is now version-controlled (audit trail, rollback, review), and updates no longer require re-cloning — they flow through `mgmt-ctl upgrade <customer>` without rebuilding the base image unless the base itself changed.

---

## 7. The IT operator interaction model

This is the most novel part of the plan and the most important to get right.

**The problem.** The operator is not a coder. They need Claude Code to be a useful tool for customizations and maintenance, but they cannot be trusted (nor should they bear the cognitive burden) to judge which changes are safe. Claude, by default, will happily edit anything and explain it well; that is a hazard here because a "helpful" edit to `upstream/` or to a mastercontainer PHP file will cause silent breakage on the next upstream merge.

**The mechanism.** `CLAUDE.md` at the repo root is a document Claude Code reads on every session. It encodes:

1. **An explicit allow-list of tasks** the operator can request freely. These are the tasks in the README. For each allow-listed task, Claude is given a concrete recipe (which files to edit, which scripts to run, which commits to make).
2. **A deny-list** of files and directories. `upstream/` is denied entirely. Anything in `.github/workflows/` that changes security posture is denied. The mastercontainer's docker socket mount is denied. Changes to SELinux options, seccomp, `security_opt`, or the `privileged` flag are denied.
3. **The `OVERRIDE:` gate.** If the operator's request requires doing something on the deny-list, Claude refuses and instructs the operator to retry with `OVERRIDE: <justification>` as the first line of their message. The justification is logged to a local commit-message file `.override-log.md` (and committed on the operator's behalf) so there is an audit trail. Claude is instructed that `OVERRIDE:` by itself is not enough — there has to be plausible justification text after it. Even with `OVERRIDE:`, certain operations (modifying `upstream/` directly, weakening auth, deleting backups) remain forbidden; those require a second, session-specific keyword provisioned out-of-band by the engineering team.
4. **A "when in doubt, ask" clause.** If the task is ambiguous, Claude asks the operator exactly one clarifying question, proposes a plan, and waits for confirmation before acting.
5. **Claude's self-check.** Before every commit, Claude re-reads the list of files changed and verifies none of them match the deny-list globs. If any match and the operator did not supply `OVERRIDE:`, Claude aborts and reverts.

This mechanism is prompt-based and therefore not a security boundary — a sufficiently clever prompt could talk Claude into circumventing it. It is a **guardrail**, not a barrier. For actual protection against accidental destruction, we layer on:

- GitHub branch protection on `main` (no direct pushes; everything through PRs reviewed by engineering).
- A `.github/workflows/guard.yml` action that runs on every PR: diffs the PR against `upstream/` and fails the build if any file under `upstream/` changed without a `upstream-approved-change` label set by engineering.
- Commit signing and enforced commit authorship (operator's identity is distinct from engineering's).
- The management server is the only path to deploy to production; the operator cannot push directly to a customer server.

Together, the `CLAUDE.md` guardrail keeps 95% of operator slip-ups from ever becoming a commit, and the CI + ops guardrails catch the remaining 5%.

### 7.1 The allow-list (concretely)

These are the tasks the operator can do without `OVERRIDE:`. Each is paired with a Claude-readable recipe in `CLAUDE.md`.

- Add or remove a Cloudflare Tunnel for a customer.
- Change brand colors, logo, favicon, slogan, name, imprint/privacy URLs for a customer.
- Replace or edit the `custom.css` for a customer or a flavor.
- Add, change, or remove JS in `customization/apps/branding-<flavor>/`.
- Enable or disable an upstream community container for a customer (`AIO_COMMUNITY_CONTAINERS=...`).
- Enable or disable an allow-listed custom community container (LiteLLM, Ollama, customer-agent).
- Install, update, or remove a Nextcloud app from the official app store via `occ`.
- Configure SMB external storage mounts for a customer.
- Configure the Exchange EWS integration for a customer.
- Configure AI/LLM provider (LocalAI, Ollama, OpenAI, LiteLLM) for a customer.
- Tune upload limits, PHP memory, max execution time via `NEXTCLOUD_*` env vars.
- Add/remove Alpine packages (`NEXTCLOUD_ADDITIONAL_APKS`) or PHP extensions (`NEXTCLOUD_ADDITIONAL_PHP_EXTENSIONS`) from the allow-listed set.
- Trigger a backup, restore, or upgrade via `mgmt-ctl`.
- Open a new customer folder and populate it from a flavor template.
- Pull upstream updates via `scripts/merge-upstream.sh`.

### 7.2 The deny-list (concretely)

These require `OVERRIDE: <justification>` at the start of the operator's message:

- Any write to a file under `upstream/`.
- Any edit to `php/` files, `containers.json`, `containers-schema.json`.
- Any edit to `.github/workflows/` that changes secrets, permissions, or the staging deploy target.
- Any change to the docker socket mount, `privileged`, `cap_add`, `security_opt`, `SELinux` options.
- Any change to `compose.yaml` top-level structure (add/remove of the mastercontainer or its volumes).
- Any addition of a community container outside the allow-listed set.
- Any edit to `CLAUDE.md` or `README.md` itself.
- Any change to secrets storage, encryption keys, or backup retention policies.
- Any change to the management server's authentication, authorization, or API surface.
- Any `rm -rf`, `docker volume rm`, or `occ db:*` destructive commands.

---

## 8. CI/CD

### 8.1 Staging deploy on merge to main

`.github/workflows/staging-deploy.yml` runs on every push to `main`:

1. Checkout (including `upstream/` subtree).
2. Build the base image and push to `ghcr.io/<org>/aio-base:sha-<short>`.
3. SSH to the staging Linux server (hardcoded, one box is enough) using a deploy key stored in GitHub Secrets.
4. On the staging server: pull the new base image, run `docker compose up -d` against a staging `.env` (owned by engineering, not operators).
5. Wait for the mastercontainer health endpoint to return 200 on port 8080.
6. Run `scripts/smoke-test.sh` which hits the Nextcloud home page, logs in as a synthetic user, uploads a small file, enables a community container, and verifies the Exchange/SMB/AI paths respond on a mock.
7. If any step fails, the job fails and tags the Slack channel. If all pass, the image is retagged `:staging-green`.

### 8.2 Customer rollout (manual, via management server)

Customer rollouts are deliberately not automatic on merge. The operator (or engineering) issues `mgmt-ctl upgrade <customer>` which (a) confirms the target image is `:staging-green` or newer, (b) takes a pre-upgrade backup via AIO's built-in borg-based backup, (c) pulls the new image, (d) restarts the mastercontainer, (e) re-runs `bootstrap-aio` in `update` mode, (f) runs a per-customer smoke test. On failure it restores the backup.

### 8.3 Scheduled upstream sync

`.github/workflows/upstream-sync.yml` runs weekly. It runs `merge-upstream.sh` in dry-run mode and opens a PR if there are changes. Engineering reviews and merges; the `staging-deploy.yml` takes over from there.

---

## 9. Management server

This is the "turn on features and do upgrades and other maintenance things" tool the brief asks for.

### 9.1 Architecture

- **Management API** (`management-server/`): a small FastAPI (Python) service plus Postgres. Deployed on a single server inside the team's network, reachable by operators via the web UI and by agents via outbound HTTPS only.
- **Customer agent** (`customization/community-containers/customer-agent/`): a tiny container that runs inside every customer instance. Calls out to the management API every N seconds with instance health, version, container states, and any queued maintenance commands. It is strictly outbound — no inbound ports opened on the customer's network. Authenticates to the API with a per-instance mTLS cert issued at registration time.
- **Web UI**: a straightforward HTML table of instances (customer, version, last-seen, features enabled, health) with buttons for the common actions (enable feature, upgrade, backup now, restart container, tail logs).

### 9.2 Operations exposed

Per-instance and bulk:

- Enable/disable feature flags (Talk, Collabora, ClamAV, Fulltextsearch, Whiteboard, Imaginary, Docker Socket Proxy, any allow-listed community container).
- Trigger `occ app:install|app:remove|app:enable|app:disable <id>`.
- Trigger a backup (AIO's built-in borg).
- Trigger an upgrade to a specific base image tag.
- Apply a new branding overlay (CSS, logo, colors) — uploads the overlay to the instance, agent applies it via `occ theming:*`.
- View tail of any AIO container's logs.
- Execute an allow-listed `occ` command.
- See Nextcloud version, app versions, disk usage, active users.

Not exposed (intentionally): arbitrary shell on the customer host, arbitrary SQL, direct filesystem access to the Nextcloud data dir.

### 9.3 Security model

- Each customer instance has its own mTLS cert and its own API scope. Compromise of one instance's cert grants read/write to that instance only.
- Operator actions are authenticated via SSO (Entra, Keycloak, or whatever the team uses) and authorized against a role matrix. "Operator" can enable features, trigger upgrades, view logs. "Admin" can additionally add customers, rotate certs, change the base image tag. "Engineering" can additionally push new community-container definitions.
- Every action is logged to an append-only audit table with operator identity, timestamp, customer, action, parameters, and result.
- The agent's actions are sandboxed to a fixed list of `occ` commands and `docker` commands, shell-escaped through a vetted library. No arbitrary shell.

### 9.4 Claude Code integration

`mgmt-ctl` is a CLI wrapper that the operator uses locally. It calls the management API over HTTPS with the operator's SSO token. Claude Code in CLAUDE.md knows the `mgmt-ctl` surface and can suggest `mgmt-ctl <subcommand>` invocations for the operator to run. Claude does not itself hold API credentials — the operator runs the command. This keeps the management server's auth surface entirely outside the LLM context.

---

## 10. Security and stability

A short checklist that every change must preserve:

- **Upstream security defaults.** The mastercontainer's read-only docker socket mount, the confined `NEXTCLOUD_MOUNT` default, seccomp for Collabora, non-root users in most containers, read-only root FS in many containers — all retained.
- **TLS.** Let's Encrypt via AIO on port 8443 for the web interface; Apache's valid cert on 443 for Nextcloud. Cloudflare Tunnel handles its own TLS termination on the Cloudflare side (operators must understand this).
- **Backups before upgrades.** The management server enforces "backup first" on upgrades. Operators cannot skip backups without `OVERRIDE:`, and the management-server action log records the override.
- **Update policy.** We pin a specific upstream tag, not `latest`. Upgrading is a deliberate act: pull upstream → PR → staging deploy → staging smoke → manual rollout.
- **Secrets.** All secrets encrypted at rest (age for repo secrets, Vault or Postgres pgcrypto for management-server secrets). Secrets never appear in image layers — only injected at runtime via `.env` or agent-fetched config.
- **Fail2ban.** Available as an AIO add-on and documented in upstream's README; enabled for all customers.
- **Audit trail.** Every operator change produces a git commit (via CLAUDE.md) and, for in-instance actions, a management-server audit row.

---

## 11. Open questions for the team

1. **Branded clients**: Do any customers need branded mobile/desktop clients? If so, we need a parallel workflow with Nextcloud Enterprise; the fork alone cannot produce them.
2. **Licensing**: Nextcloud AIO is AGPL-3.0. Running a modified version as a service to customers is permitted, but distributing our fork to customers requires offering the source under AGPL. Confirm the distribution model: are we SaaS-operating the instances (we run them, customers use them), or are we handing customers a VM to run themselves? The second case has compliance implications.
3. **Airgapped customers**: Upstream explicitly does not support airgapped installs ("No. This is not possible and will not be added"). If any customer needs airgapped operation, this is a hard stop and requires replacing the AIO mastercontainer with the `manual-install` Compose setup. Budget several weeks if so.
4. **Nextcloud version target**: Nextcloud 30+ unlocks the AI worker systemd service and some Assistant improvements. Is everyone on 30+ or do we need to support older versions?
5. **Management-server runtime**: Python/FastAPI is the sketch above, but if the team is Node/TS shop, swap accordingly. The agent is small enough to rewrite in either.
6. **Disaster recovery RPO/RTO**: AIO's borg backup is daily by default. Is daily RPO acceptable, or do we need a secondary replication path (e.g., continuous S3 sync of the data dir)?
7. **VM image format(s)**: Which hypervisors do customers use? Packer can build for VirtualBox, VMware ESXi, Hyper-V, Proxmox, AWS, Azure, GCP, and qcow2 simultaneously; we should enumerate which we commit to.

---

## 12. Next steps (recommended order)

1. **Create the repo** with the layout in §4; commit `upstream/` as a subtree pinned to the current latest AIO release tag.
2. **Write and test `scripts/merge-upstream.sh`** and `scripts/integration-test.sh` before writing anything else — this is the "is our strategy workable" test.
3. **Write `CLAUDE.md` and `README.md`** (provided in this deliverable bundle as sibling files).
4. **Build the bootstrap script** incrementally: start with theming + Cloudflare tunnel + SMB, add Exchange and AI/LLM once those are stable.
5. **Stand up the staging server** and wire `.github/workflows/staging-deploy.yml`.
6. **Onboard one friendly customer** end-to-end with the pipeline before building the management server.
7. **Build the management server** once the deployment story has been proven on at least one customer. Premature building here risks modeling the wrong abstractions.
8. **Scheduled upstream sync** once a month of real operator usage has exposed whatever sharp edges the allow-list has.

The total effort for a minimal viable version of this (no management server, one flavor, manual upgrades, Docker only) is approximately 4–6 engineering-weeks. The management server adds another 3–4. Packer VM builds add 1–2. Call it two months of focused work for the full scope, with a meaningful v1 available after week 6.
