# Management Server — Architecture

**Audience:** engineers building and extending the management server.
**Scope:** the control plane for the fleet of customer Nextcloud AIO instances. Not the instances themselves.

---

## 1. What this server is for

One server, one database, one web UI, and one thin agent running inside each customer instance. The server exists so that an operator — or a scheduled job — can do fleet-wide operations (enable a feature, push an image, take a backup, apply a new CSS bundle, tail a log) without logging into any customer's server directly. Equally, customer instances are the only place where production data lives; the management server holds metadata and ephemeral command queues, never data.

The design priorities, in order:

1. **Customer instances never accept inbound connections from the management server.** All traffic is agent-initiated (outbound from the customer's network). This keeps customer firewalls and security reviews simple.
2. **The blast radius of a compromised management-server credential is bounded.** No credential grants arbitrary shell on a customer. Every action is one of a fixed set of typed operations.
3. **Every action is audited.** Who did what, when, to which customer, with what parameters, with what result.
4. **The server is stateless enough to rebuild.** Postgres holds the truth; the API server itself can be redeployed from CI in minutes.

---

## 2. Topology

```
┌─────────────────┐         ┌──────────────────────────┐
│ Operator laptop │         │ Scheduled jobs / cron    │
│  (mgmt-ctl CLI) │         │  (upstream-sync etc.)    │
└────────┬────────┘         └──────────┬───────────────┘
         │  HTTPS + SSO JWT             │  HTTPS + service JWT
         ▼                              ▼
  ┌───────────────────────────────────────────────┐
  │         Management API (FastAPI)              │
  │   - Auth: SSO (Entra / Keycloak / Okta)       │
  │   - Authz: RBAC on (role × action × customer) │
  │   - Audit: append-only table, every call      │
  └──────────────┬───────────────┬────────────────┘
                 │               │
                 ▼               ▼
          ┌───────────┐    ┌──────────────┐
          │ Postgres  │    │  Object store │
          │ (fleet,   │    │  (S3-compat)  │
          │  queue,   │    │  logs, bundles│
          │  audit)   │    │  branding     │
          └───────────┘    └──────────────┘
                 ▲
                 │  HTTPS + mTLS (outbound only from customer)
                 │  long-poll for pending commands
                 │
  ┌──────────────┴──────────────────────────────────┐
  │  Customer site A         Customer site B   ...  │
  │  ┌─────────────────┐    ┌─────────────────┐     │
  │  │ AIO mastercont. │    │ AIO mastercont. │     │
  │  │ + nextcloud-aio │    │ + nextcloud-aio │     │
  │  │ + customer-agent│    │ + customer-agent│     │
  │  └─────────────────┘    └─────────────────┘     │
  └─────────────────────────────────────────────────┘
```

The agent is the only component that crosses the customer boundary, and it only reaches out. It never listens.

---

## 3. Data model (Postgres)

Tables, elided to the columns that matter. All tables have `id uuid`, `created_at`, `updated_at`.

### `customers`
- `slug` (e.g., `acme-corp`), unique
- `display_name`
- `domain`
- `flavor` (foreign key to `flavors.slug`)
- `site_mode` (`docker` | `vm`)
- `deployed_image_tag`
- `state` (`pending` | `healthy` | `degraded` | `offline` | `decommissioned`)
- `last_seen_at`
- `deployed_at`
- `managed_by_team` (for multi-tenant org structures)

### `flavors`
- `slug`
- `description`
- `nextcloud_version_pin`
- `default_apps` (text[])
- `default_community_containers` (text[])

### `features`
A catalog of what can be enabled. Separate from `feature_bindings` because the catalog evolves as upstream does.
- `key` (e.g., `talk`, `collabora`, `clamav`, `fulltextsearch`, `imaginary`, `whiteboard`)
- `provides` (`upstream-optional` | `community-container` | `nc-app` | `custom`)
- `default_on_flavors` (text[])
- `conflicts_with` (text[])
- `min_base_image_tag` (first tag that supports this feature)

### `feature_bindings`
- `customer_id`
- `feature_key`
- `enabled`
- `config_json` (provider-specific, JSONB)
- `enabled_by` (user or `system`)
- `enabled_at`

### `commands`
The agent's work queue. Commands are immutable once enqueued; the agent picks them up, executes, and writes a result. No mutable state on the agent itself.
- `customer_id`
- `kind` (see §5 for the enumerated set)
- `payload_json` (JSONB)
- `state` (`queued` | `leased` | `done` | `failed` | `canceled`)
- `enqueued_by` (user or `system`)
- `leased_by_agent_id`
- `leased_at`
- `lease_deadline` (agent must check in by this time or lease expires and command re-queues)
- `result_json`
- `completed_at`

### `audits`
Append-only. Never updated, never deleted (archive policy is a separate process).
- `actor_kind` (`user` | `service` | `agent` | `system`)
- `actor_id`
- `customer_id` (nullable — some actions are fleet-wide)
- `action` (human-readable, e.g., `feature.enable`, `command.enqueue`, `image.promote`)
- `parameters_json`
- `result` (`success` | `failure`)
- `error_detail` (nullable)
- `source_ip`
- `request_id` (for cross-service tracing)

### `agents`
One row per customer instance.
- `customer_id`
- `agent_version`
- `mtls_cert_fingerprint`
- `registered_at`
- `last_heartbeat_at`
- `reported_state_json` (container states, NC version, app versions, disk usage)

### `base_images`
- `tag` (e.g., `sha-7f8c1a2b`, `staging-green`, `v2026.04.21-rc1`)
- `git_sha`
- `built_at`
- `promoted_to` (`staging-green` | `production` | null)
- `promoted_at`
- `release_notes` (markdown)
- `rollback_safe_from_tags` (text[]) — tags that can be rolled back from this one

### `users`, `roles`, `role_assignments`
- RBAC substrate; see §6.

---

## 4. Agent protocol

### 4.1 Connection

The agent runs inside the customer instance as a community container. On startup:

1. Reads the one-time registration token from its env (seeded at bootstrap via `customization/customers/<n>/customer.env.secret.age`).
2. Generates a local ECDSA keypair. The private key lives only on the customer host in a Docker volume never touched by backups.
3. Calls `POST /api/v1/agents/register` with the token and the CSR. The management server verifies the token (one-time, expires after 24h), signs the CSR with the per-customer CA, and returns the signed cert. The registration token is burned.
4. Deletes the token from its env. All subsequent calls use mTLS with the signed cert.

### 4.2 Long-poll loop

The agent does one thing in a loop, forever:

```
loop {
  resp = POST /api/v1/agents/tick {
    heartbeat: { container_states, nc_version, app_versions, disk_usage, last_error },
    ready_for_commands: true,
  }
  for cmd in resp.commands:
    result = execute(cmd)
    POST /api/v1/agents/commands/{cmd.id}/result { result }
}
```

Tick interval: 15s when idle, immediate retick after any command completes. The server caps command lease time at 5 minutes; if the agent hasn't reported completion by then, the command re-queues.

### 4.3 What `execute(cmd)` can do

The agent has a **hard-coded allow-list of command kinds**. Each kind maps to a function with validated arguments. The command payload cannot name arbitrary shell; it names a kind and typed parameters.

| Kind | What it does inside the customer |
|---|---|
| `occ.run` | Runs `occ <subcommand>` where `<subcommand>` is on an allow-list (no `db:*`, no `maintenance:repair`, no `files:cleanup`). |
| `occ.app.install` | `occ app:install <id>` where `<id>` is on the app-store allow-list. |
| `occ.app.remove` | `occ app:remove <id>`. |
| `occ.app.enable` / `disable` | As named. |
| `occ.config.app.set` | For a bounded set of app configs (theming, integration_openai, integration_ews). Values bounded in size. |
| `occ.theming.config` | `occ theming:config <key> <value>`. |
| `occ.files_external.create` / `update` / `delete` | SMB mount operations, typed. |
| `aio.container.start` / `stop` / `restart` | Named container only, no raw docker. |
| `aio.backup.now` | Triggers AIO's built-in borg backup. |
| `aio.image.upgrade` | Given a base image tag, stops containers, pulls, runs bootstrap in `update` mode, starts. Refuses tags older than current. |
| `custom.branding.apply` | Downloads an S3-hosted branding bundle (logo, CSS, background) and re-runs the theming section of bootstrap. |
| `custom.community_containers.set` | Sets `AIO_COMMUNITY_CONTAINERS` and signals mastercontainer to restart. Validates container names against the allow-list. |
| `custom.logs.tail` | Runs `docker logs --tail=N <container>` against a named AIO container. Returns the tail in the result payload. Size-capped. |
| `custom.health.report` | Runs a fuller health check than heartbeat — cron status, background job queue depth, DB size. |
| `custom.backup.set_target` | Sets the borg backup target (local path or S3 bucket) and runs a probe write. Does not trigger a backup. |
| `custom.ollama.pull` | Pulls a named model into the customer's Ollama container cache. Arg `model` validated against a server-side allow-list of model names. Refuses if the Ollama community container is not enabled. |
| `custom.ollama.list` | Lists models currently pulled into the customer's Ollama cache. |
| `custom.litellm.rotate_key` | Rotates a named provider's key in the LiteLLM container's env from the customer's age-encrypted secret store. Arg `provider` restricted to `openai\|anthropic\|bedrock\|vertex`. |
| `custom.litellm.reload` | Signals the LiteLLM container to re-read its `config.yaml` without restarting. |
| `noop` | For testing connectivity. |

Everything outside this list is a 501 from the agent. If the management server sends an unknown kind, the agent records it in its local log and reports `kind_not_supported`.

### 4.4 Idempotency

Every command has a `customer_scoped_idempotency_key`. If the agent sees a key it has processed in the last 24h, it returns the prior result instead of re-executing. This matters because network retries would otherwise double-apply operations like "install app."

### 4.5 What the agent explicitly cannot do

- Arbitrary shell. No `exec`, no `eval`. The command-kind enumeration is the only API.
- Read or write Nextcloud user data files. The agent has no access to `/mnt/ncdata/` beyond what `occ` exposes.
- Fetch or decrypt the customer's age-encrypted secrets. Secrets decrypt at bootstrap, in a volume the agent does not mount.
- Install software on the host. The agent runs inside a container; the Docker socket mount is read-only (upstream's default) and the agent does not use it.
- Open inbound ports. Enforced by not listening on any port.

---

## 5. API surface

All endpoints are under `/api/v1/`. All responses are JSON. All write endpoints require a `X-Idempotency-Key` header; the server records the key and returns the prior response on retry.

### 5.1 Auth endpoints

- `POST /auth/login` — initiates SSO flow (OIDC). Server acts as OIDC client to the team's IdP.
- `GET /auth/callback` — receives the IdP callback, issues a session JWT.
- `POST /auth/refresh` — rotates the session JWT.
- `POST /auth/logout` — invalidates the session.
- `GET /users/me` — returns the current identity: user id, email, roles, assigned customers. Backs `mgmt-ctl whoami`.

Service accounts (for scheduled jobs, CI) use a long-lived API key issued by engineering, stored as a bcrypt hash in `users`.

### 5.2 Customers

- `GET /customers` — list. Supports filters by flavor, state, has-feature.
- `POST /customers` — onboard. Body: `{ slug, display_name, domain, flavor, site_mode }`. Returns a registration token. Also backs `mgmt-ctl enroll <slug>` which re-issues a new one-time registration token for an existing customer.
- `POST /customers/{slug}/enroll` — issue a fresh one-time registration token for an already-existing customer (e.g., re-enrolling after agent cert revocation).
- `GET /customers/{slug}` — detailed view, including current feature bindings and recent commands.
- `PATCH /customers/{slug}` — update display name, domain, etc. Cannot change `slug`.
- `GET /customers/compare?a=<slug>&b=<slug>` — diff two customers' feature bindings, versions, and flavor. Backs `mgmt-ctl customers diff`.
- `POST /customers/{slug}/apply` — re-run bootstrap against a running instance. Body: `{ section?: "theming"|"apps"|"ai"|"smb"|"exchange"|"cloudflared" }` (omit for full). Enqueues `custom.bootstrap.reapply` or a section-scoped variant.
- `POST /customers/{slug}/rollback` — revert to the previous `deployed_image_tag`. Refuses if more than one image has been deployed since the target (requires `--to` with justification).
- `POST /customers/{slug}/occ` — passthrough for `mgmt-ctl occ`. Body: `{ subcommand: "...", args: [...] }`. Enforces the `occ` allow-list server-side before enqueueing `occ.run`.
- `POST /customers/{slug}/decommission` — irreversible; marks state=decommissioned, revokes agent cert, purges commands.

### 5.3 Features

- `GET /features` — the catalog.
- `GET /customers/{slug}/features` — bindings for one customer.
- `POST /customers/{slug}/features/{key}/enable` — enqueues the underlying commands, returns the command IDs.
- `POST /customers/{slug}/features/{key}/disable` — same.

### 5.4 Commands

- `GET /commands?customer=<slug>&since=<ts>&kind=<k>` — list.
- `GET /commands/{id}` — single command with result.
- `POST /commands/{id}/cancel` — only if state=queued.
- `POST /commands/bulk-enqueue` — for fleet operations. Body describes the kind and a selector (`{flavor: "law-firm"}` or `{slugs: [...]}`). Server expands to individual commands.

### 5.5 Agents

Agent-facing (the customer-side agent is the caller; authenticates via mTLS):

- `POST /agents/register` — one-time, via registration token.
- `POST /agents/tick` — long-poll, heartbeat + command fetch.
- `POST /agents/commands/{id}/result` — report completion.
- `POST /agents/log` — structured agent-side log entry. Rate-limited per agent.

Operator-facing (authenticated as user/service account):

- `GET /agents?customer=<slug>` — list agents with their last-seen timestamps and cert expiries. Backs `mgmt-ctl agents list`.
- `POST /agents/{slug}/rotate` — issue a fresh mTLS cert and signal the agent to pick it up on next tick. Backs `mgmt-ctl agents rotate`.
- `POST /agents/{slug}/revoke` — revoke the agent cert; customer goes offline until re-enrolled. Backs `mgmt-ctl agents revoke`.

### 5.6 Images, upgrades, backups

- `GET /images` — list of `base_images`.
- `GET /images/{tag}` — single image metadata: build timestamp, commit SHA, dependency SBOM pointer, promotion history. Backs `mgmt-ctl images show`.
- `POST /images/{tag}/promote` — mark tag as `staging-green` or `production`. Engineering-role only.
- `POST /customers/{slug}/upgrade` — enqueue `aio.image.upgrade` to a named tag. Enforces "target ≥ current" and "backup within last 24h exists."
- `GET /customers/{slug}/backups` — list stored borg archives with IDs, timestamps, sizes, states. Backs `mgmt-ctl backups list`.
- `POST /customers/{slug}/backups` — enqueue `aio.backup.now`. Body: `{ label?: string }`. Backs `mgmt-ctl backup`.
- `POST /customers/{slug}/backups/{id}/restore` — enqueue a restore from the named archive. Irreversible — server requires an `X-Confirm: restore-overwrites-state` header. Backs `mgmt-ctl restore`.
- `POST /customers/{slug}/backups/pause` / `/resume` — flip the scheduled-backups flag (server-side state, no agent command enqueued). Backs `mgmt-ctl backups pause|resume`.
- `PUT /customers/{slug}/backups/target` — set the backup target. Body `{ type: "local"|"s3", path?: string, s3_bucket?: string }`. Enqueues `custom.backup.set_target`. Backs `mgmt-ctl backups set-target`.

### 5.7 Branding

- `PUT /customers/{slug}/branding` — multipart upload: logo, background, css. Stored in object store, manifest referenced from `feature_bindings[key='branding']`. Enqueues `custom.branding.apply`.

### 5.8 Logs & health

- `GET /customers/{slug}/logs?container=<n>&tail=<n>` — synchronously enqueues `custom.logs.tail` and waits up to 30s for the agent result. Useful in incidents.
- `GET /customers/{slug}/health` — latest heartbeat.
- `GET /customers/{slug}/health/history?since=<ts>` — from the `agents` table's historical snapshots.

### 5.9 Audit

- `GET /audits?actor=<id>&customer=<slug>&action=<prefix>&since=<ts>` — read-only query on the audit table. All operators can read, none can delete.
- `GET /audits/export?since=<ts>&format=csv|ndjson` — streaming export, same filters as `GET /audits`. Backs `mgmt-ctl audit export`. Content-Disposition headers set appropriately.

### 5.10 Break-glass

Temporary privilege elevation. Two-person rule: one requests, a different engineer approves.

- `POST /break-glass/request` — body `{ role: "admin"|"engineering", duration_seconds: int, reason: string }`. Creates a pending request and notifies the engineering Slack channel. Backs `mgmt-ctl break-glass request`.
- `POST /break-glass/{id}/approve` — approves a pending request. Refuses if the approver is the requester. Backs `mgmt-ctl break-glass approve`.
- `GET /break-glass?state=pending|active|expired` — list requests (own + any the caller can approve).

### 5.11 Provider ops (Ollama, LiteLLM)

- `POST /customers/{slug}/ollama/pull` — body `{ model: string }`. Enqueues `custom.ollama.pull`. Validates the model against a server-side allow-list. Backs `mgmt-ctl ollama pull`.
- `GET /customers/{slug}/ollama/models` — enqueues `custom.ollama.list` synchronously (30s timeout) and returns the result. Backs `mgmt-ctl ollama list`.
- `POST /customers/{slug}/litellm/rotate` — body `{ provider: "openai"|"anthropic"|"bedrock"|"vertex" }`. Enqueues `custom.litellm.rotate_key`. Backs `mgmt-ctl litellm rotate`.
- `POST /customers/{slug}/litellm/reload` — enqueues `custom.litellm.reload`. Backs `mgmt-ctl litellm reload`.

Each of these refuses with 409 if the corresponding community container (`ollama`, `litellm`) is not enabled on the customer.

### 5.12 Containers (operator ops)

- `POST /customers/{slug}/containers/{name}/restart` — enqueue `aio.container.restart`. Backs `mgmt-ctl restart <slug> --container <name>`.
- `POST /customers/{slug}/containers/{name}/start` — enqueue `aio.container.start`.
- `POST /customers/{slug}/containers/{name}/stop` — enqueue `aio.container.stop`.
- `POST /customers/{slug}/restart` — batch: restarts all AIO containers except the mastercontainer. Backs bare `mgmt-ctl restart <slug>`.

All four require the target container name (when specified) to be on the server's container-name allow-list. The mastercontainer is deliberately off the allow-list for plain `restart`; restarting it requires the `?force=true` query flag and is audited as a privileged action.

---

## 6. RBAC

Three roles, clearly nested.

### Operator
- Can read everything about customers they are assigned to.
- Can enqueue all command kinds **except**: `aio.image.upgrade`, `custom.community_containers.set`, any `occ.app.install` for non-default flavor apps.
- Can trigger backups, apply branding, enable/disable upstream-optional features (Talk, Collabora, ClamAV, Imaginary, Whiteboard).
- Cannot onboard customers.
- Cannot promote image tags.
- Cannot change another operator's assignments.

### Admin
- Everything Operator can do.
- Can onboard and decommission customers.
- Can enqueue `aio.image.upgrade` and `custom.community_containers.set`.
- Can assign customers to operators.
- Can rotate agent certs.
- Cannot promote to `production` or change RBAC itself.

### Engineering
- Everything Admin can do.
- Can promote `staging-green` to `production`.
- Can edit the feature catalog.
- Can edit RBAC and role assignments.
- Can see and read (but not decrypt) per-customer secret metadata.
- Cannot decrypt secrets — those live in the customer instance's age vault; no server-side decryption path exists.

### Enforcement

RBAC check runs twice: once in the HTTP middleware (fast-fail for obvious denies) and once in the service layer with full context (customer assignments, current feature state, command kind rules). Both checks log to the audit table on deny; failed authz is a common attack indicator.

### Break-glass

For production incidents where the engineer on call needs a permission they don't normally have, there's a break-glass flow: `POST /break-glass/request` → Slack notification to all engineering → second engineer approves → 4-hour elevated role assignment, auto-expiring. Every break-glass use generates a post-incident review task.

---

## 7. Security posture

### 7.1 Trust boundaries

- **Operator ↔ management API**: SSO-issued JWT, 1h TTL. JWT carries user ID and current roles; authz always re-checks against the DB in case roles changed.
- **Service (CI/cron) ↔ management API**: long-lived API keys hashed at rest. Scoped to the minimum role needed (typically a dedicated `service-ci` role that can only promote tags and enqueue fleet-wide syncs).
- **Agent ↔ management API**: mTLS with a per-customer cert, rotated every 90 days. Cert rotation is agent-initiated (CSR) and server-approved. Compromised cert → revoke + re-enroll.
- **Management API ↔ object store**: short-lived STS creds, scoped to a single customer's prefix when relevant (e.g., branding upload goes to `s3://.../branding/acme-corp/`).
- **Management API ↔ Postgres**: IAM-authenticated connection if on AWS/GCP, otherwise certificate auth. Connection pool configured for graceful degradation (reads can serve from a replica).

### 7.2 Secret handling

- Secrets visible to the server: JWT signing key, service API key hashes, per-customer CA signing key, object-store STS base creds. All in a Hashicorp Vault or cloud KMS; the server reads on boot and keeps in memory, never writes to disk.
- Secrets NOT visible to the server: Nextcloud admin passwords, customer Exchange credentials, customer OpenAI API keys, customer Cloudflare tunnel tokens. Those live in age-encrypted files in the customer's overlay dir; bootstrap decrypts locally on the customer host using an age key baked into the VM image or Docker volume.
- Audit payloads are filtered: no API keys, no passwords, no personal file paths. The filter is allow-list based — only known-safe keys pass through.

### 7.3 Input validation

- Every endpoint uses Pydantic models (FastAPI). Unknown fields rejected. String length caps on every field. UUID format enforced. Enum values enforced.
- `occ.run` command has a nested allow-list: the `subcommand` must match a regex AND be on a hardcoded set of OCC commands, AND each arg is validated.
- File uploads (branding): max 10 MB per file, MIME sniff (SVG, JPEG, PNG, CSS only), image dimensions checked.
- SQL: parameterized queries only; no ORM escape hatches for operator-provided input.

### 7.4 Rate limiting

- Per-user: 60 req/min default, 600 req/min for burst actions (log tails during incidents).
- Per-agent: 6 ticks/min default (matches the 15s cadence). Agents exceeding this are throttled, not blocked — we want to see them even if misbehaving.
- Global: 10k req/min on the whole API. Exceeded → 503 with Retry-After.

### 7.5 Defense in depth

- The server runs behind a reverse proxy (Traefik or Caddy) that handles TLS termination with our own cert, not a passthrough. This lets us do WAF rules.
- The customer-agent cert CA is separate from the operator TLS cert CA. A compromise of one does not imply the other.
- Postgres is on a private subnet; only the API server can reach it.
- Object store buckets are private; all access is via short-lived presigned URLs generated by the API server.

---

## 8. Deployment

The management server is a single container (`ghcr.io/<org>/mgmt-server:<tag>`) + Postgres + object store. Deployed via a small Compose file on a VM inside the team's network. For HA you run two API replicas behind a load balancer and one Postgres primary with one replica — overkill until the fleet is > 50 customers.

Upgrades are blue/green: spin up new version next to old, run migrations in a forward-compatible way (no destructive column drops in the same release that adds them), switch the LB, keep the old instance running for 30 minutes in case of rollback.

---

## 9. What we explicitly do not do

To keep the scope tight and the attack surface small:

- No per-user file access on customer instances. An operator cannot see a user's files via this server.
- No write access to the Nextcloud database from the management server (only via the agent's bounded `occ` commands).
- No multi-tenancy in the sense of SaaS — customers don't see this server; only our team does.
- No webhook ingress. If we need to integrate with external systems (PagerDuty, Statuspage), they poll our API.
- No plugin system. New command kinds require engineering-reviewed PRs that add to the agent's enumerated list.
- No UI for raw command construction. Operators always go through the typed actions; if they need a command the UI doesn't expose, engineering adds it properly.

---

## 10. Build phasing

If you're building this from scratch, the bare minimum to unblock customer rollouts is small:

**Phase 1 (a week of focused work):** `customers`, `agents`, `commands`, `audits` tables. Agent registration + long-poll. Three command kinds: `noop`, `aio.backup.now`, `aio.image.upgrade`. Operator CLI login + enqueue + read results. No web UI.

**Phase 2 (another week):** `features`, `feature_bindings`. `occ.app.*`, `occ.theming.config`, `custom.branding.apply`. Basic web UI listing customers.

**Phase 3 (2-3 weeks):** RBAC with three roles. Full command-kind list. SSO integration. Image catalog + promotion flow. Audit log search UI.

**Phase 4 (ongoing):** Break-glass flow, cert rotation automation, health history, bulk enqueue, object-store branding bundles.

Do not build Phase 3 before Phase 1 has been exercised in production for two weeks. The interface lessons from real use are the ones that matter; everything else is premature design.

---

## 11. Running locally

Zero-to-running checklist for an engineer iterating on this service.

### Option A — pytest only (no Docker)

```bash
cd management-server
make dev-install         # creates .venv, installs runtime + dev deps + aiosqlite
make test                # 12 tests, SQLite in-memory, ~1 second
```

This is the fastest loop. Tests use `sqlite+aiosqlite:///:memory:` with
a `StaticPool`; Postgres-specific types (`JSONB`, native `ENUM`) are
shimmed to SQLite's `JSON` via `tests/_sqlite_compat.py`. The shape of
the app is the same; cross-DB SQL semantics are not, so anything that
depends on Postgres-only behavior (`ON CONFLICT`, `JSONB ?` operators)
needs a real Postgres.

### Option B — full stack with Postgres + MinIO

```bash
cd management-server
docker compose up --build -d
# wait ~5s for postgres to accept connections
./.venv/bin/alembic upgrade head     # apply initial migration
curl http://localhost:8080/health     # {"status":"ok","version":"0.1.0"}
```

Ports:
- `8080`  FastAPI (`/health`, `/docs`, `/api/v1/*`)
- `5432`  Postgres
- `9000`  MinIO API
- `9001`  MinIO console

### Dev login (no real OIDC required)

`ENVIRONMENT=dev` enables a `POST /api/v1/auth/dev-login` endpoint that
mints a session JWT with arbitrary roles:

```bash
token=$(curl -s -X POST http://localhost:8080/api/v1/auth/dev-login \
    -H 'content-type: application/json' \
    -d '{"email":"me@example.com","roles":["engineering"]}' \
    | jq -r .access_token)

curl -H "Authorization: Bearer $token" http://localhost:8080/api/v1/users/me
```

The endpoint 404s when `ENVIRONMENT` is anything other than `dev`.

### Known Phase 2 caveats

- Routes fully implemented: auth/users/me + dev-login, customers
  list/show/create/enroll/decommission, agents register/tick/log/command
  result, commands list/get. Everything else in §5 is a 501 stub with
  the correct response shape for client development.
- OIDC is stubbed; there's no real IdP integration yet.
- Break-glass flow (§5.10) is skeleton-only.
- Object-store branding bundles (§5.7) are skeleton-only.
- `ARRAY(String)` columns from §3 were converted to `JSON` in both the
  ORM and the alembic migration to keep the test path portable. We lose
  Postgres array operators; nothing currently queries into these lists
  so the tradeoff is acceptable for Phase 2. Reverting is a single
  migration when the query need arrives.
