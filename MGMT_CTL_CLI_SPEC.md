# mgmt-ctl — Operator CLI Specification

`mgmt-ctl` is the thin command-line wrapper operators use to talk to the management server. It is the **only** way an operator acts on a running customer instance. Claude Code suggests `mgmt-ctl` commands; the operator runs them.

This document specifies the command surface. The implementation is in `management-server/cli/` (Go, single static binary).

---

## Design principles

1. **Every command maps 1:1 to a management-server API call.** No client-side logic beyond formatting. This keeps authz enforcement on the server where it belongs.
2. **Every destructive command requires confirmation.** `--yes` skips it; without it, the CLI prints the resolved action and waits for `y`.
3. **Output is human by default, `--json` for scripts.** Human output is a summary; JSON is the full API response.
4. **Errors map API error codes to actionable messages.** "403 Forbidden" prints as "You don't have permission for this action on customer <slug>. Your current roles: ... Required role: ...".
5. **Auth via SSO once per laptop.** `mgmt-ctl login` opens a browser, completes OIDC, stashes a refresh token. Commands silently refresh. No API keys on developer laptops.

---

## Command tree

```
mgmt-ctl
├── login                       Start an SSO session.
├── logout                      Revoke the current session.
├── whoami                      Print current user, roles, and assigned customers.
│
├── customers
│   ├── list                    List all customers (filterable).
│   ├── show <slug>             Show one customer's full state.
│   ├── create <slug>           Onboard a new customer.
│   ├── decommission <slug>     Mark customer decommissioned. Irreversible.
│   └── diff <slug-a> <slug-b>  Compare feature bindings and versions.
│
├── enroll <slug>               Generate a one-time registration token for the agent.
├── agents
│   ├── list [--customer <slug>]
│   ├── rotate <slug>           Rotate the agent mTLS cert.
│   └── revoke <slug>           Revoke the agent cert (customer goes offline).
│
├── features
│   ├── list [--customer <slug>]
│   ├── enable <slug> <feature-key> [--config '<json>']
│   └── disable <slug> <feature-key>
│
├── apply                       Re-run bootstrap against a running instance.
│   └── --customer <slug> [--section theming|apps|ai|smb|exchange]
│
├── apply-branding <slug>       Upload + apply a branding bundle.
│   └── [--css <file>] [--logo <file>] [--background <file>] [--dry-run]
│
├── backup <slug> [--label <name>]
├── restore <slug> --archive <id>
├── rollback <slug>             Revert to the previous image tag for this customer.
├── upgrade <slug> --to <tag> [--no-backup-override]
│
├── backups                     Backup configuration & schedule (not "run one now" — that is `backup`).
│   ├── list <slug>             List stored backup archives with IDs, timestamps, sizes, states.
│   ├── pause <slug>            Pause scheduled backups for this customer (server-side flag).
│   ├── resume <slug>           Resume scheduled backups.
│   └── set-target <slug> --type local|s3 --path <path> [--s3-bucket <b>]
│
├── restart <slug> [--container <name>] [--force]
│                                Restart containers. With no `--container`, restarts all AIO
│                                containers except the mastercontainer. With `--container
│                                nextcloud-aio-mastercontainer --force`, performs the rarer
│                                mastercontainer restart (requires `OVERRIDE:` in operator mode).
├── start <slug> --container <name>
├── stop <slug> --container <name>
│
├── logs <slug>                 Tail container logs.
│   └── --container <n> [--tail <N>] [--follow]
│
├── status <slug>               One-liner per customer: state, version, last-seen.
├── health <slug> [--full]      Detailed health report.
│
├── occ <slug> <...subcommand>  Run an allow-listed occ command.
│                                Must be on the server's occ allow-list.
│
├── ollama                      Operations against a customer's Ollama container (requires the
│   │                            `ollama` community container to be enabled on the customer).
│   ├── pull <slug> <model>     Pull a model image into the customer's Ollama cache.
│   └── list <slug>             List models currently pulled.
│
├── litellm                     Operations against a customer's LiteLLM proxy container
│   │                            (requires the `litellm` community container).
│   ├── rotate <slug> --provider <openai|anthropic|bedrock|vertex>
│   │                            Rotate the named provider's API key from the encrypted secret store.
│   └── reload <slug>           Re-read `config.yaml` without restarting.
│
├── images
│   ├── list
│   ├── show <tag>
│   └── promote <tag> --to staging-green|production   (engineering-only)
│
├── audit
│   ├── list [--since <ts>] [--actor <id>] [--customer <slug>] [--action <prefix>]
│   └── export [--since <ts>] [--format csv|ndjson]
│
└── break-glass
    ├── request --role <role> --duration 4h --reason "<text>"
    └── approve <request-id>                           (second engineer only)
```

---

## Command details (the ones operators use most)

### `login`

```
mgmt-ctl login [--server https://mgmt.internal.example.com]
```

Opens a local HTTP listener on 127.0.0.1 for the OIDC redirect, launches the browser, completes auth, writes a refresh token to `~/.config/mgmt-ctl/session.json` with 0600 permissions. Prints: `Logged in as alice@example.com (role: operator, 12 customers).`

### `customers list`

```
mgmt-ctl customers list [--flavor <f>] [--state <s>] [--has-feature <k>]
```

Human output:

```
SLUG              FLAVOR      STATE      LAST SEEN   VERSION       FEATURES
acme-corp         default     healthy    2m ago      sha-7f8c1a2b  talk, collabora, ews
bigcorp           law-firm    degraded   14m ago     sha-6e2b9f1d  talk, collabora
riverside-law     law-firm    healthy    1m ago      sha-7f8c1a2b  collabora, ews, litellm
...
```

### `customers create`

```
mgmt-ctl customers create acme-corp \
  --display-name "ACME Corporation Cloud" \
  --domain cloud.acme.example.com \
  --flavor default \
  --site-mode docker
```

Server creates the customer row in `pending` state, generates the registration token, prints the token (once — it is not stored in plaintext anywhere after). Operator stashes the token in the customer's `customer.env.secret.age`.

### `apply --customer <slug> [--section <s>]`

```
mgmt-ctl apply --customer acme-corp                # re-run the whole bootstrap
mgmt-ctl apply --customer acme-corp --section theming  # just re-apply theming
```

Enqueues a `custom.branding.apply` or `custom.bootstrap.reapply` command with the named section. Useful after changing `customer.env` or `custom.css`.

### `upgrade <slug> --to <tag>`

```
mgmt-ctl upgrade acme-corp --to staging-green
```

The sequence:

1. CLI prompts: "Upgrade acme-corp from sha-6e2b9f1d (deployed 2w ago) to staging-green (built 1h ago)? [y/N]"
2. Server verifies: target tag is ≥ current, a backup exists within the last 24h (else 409 unless `--no-backup-override` which is overridable), customer is healthy.
3. Server enqueues `aio.backup.now` followed by `aio.image.upgrade`.
4. CLI polls for completion and tails the agent's progress stream.
5. Post-upgrade smoke test runs; result printed.

### `rollback <slug>`

```
mgmt-ctl rollback acme-corp
```

The inverse of upgrade. Rolls to the prior `deployed_image_tag` recorded in the DB. Refuses if more than one image has been deployed since the one being rolled to (to prevent going too far back without intent). For longer rollbacks, `upgrade --to <older-tag>` with a justified `OVERRIDE:` is the path.

### `logs <slug> --container <c> [--tail N] [--follow]`

```
mgmt-ctl logs acme-corp --container nextcloud-aio-apache --tail 200
mgmt-ctl logs acme-corp --container nextcloud-aio-nextcloud --follow
```

Under the hood: enqueues `custom.logs.tail`, waits for the result, prints. `--follow` polls every 5s for a fresh tail until the user Ctrl-Cs. Size-capped at 2MB per chunk to prevent OOM in the agent.

### `occ <slug> <subcommand...>`

```
mgmt-ctl occ acme-corp files:scan --all
mgmt-ctl occ acme-corp user:list
mgmt-ctl occ acme-corp config:system:get trusted_domains
```

The server's allow-list of `occ` subcommands:

- **Read-only (always allowed):** `status`, `version`, `user:list`, `group:list`, `app:list`, `files_external:list`, `config:system:get`, `config:app:get`, `theming:config` (without value).
- **Mutating (require operator role):** `user:*` (except `user:delete`), `files:scan`, `files_external:option`, `theming:config <key> <value>`, `app:enable|disable`.
- **Admin-only:** `app:install|remove`, `user:delete`, `files_external:create|update|delete`.
- **Never allowed** (always refused): `db:*`, `maintenance:repair`, `maintenance:data-fingerprint`, `files:cleanup`, `integrity:check-*`, any unrecognized command.

### `apply-branding <slug>`

```
mgmt-ctl apply-branding acme-corp \
  --css customization/customers/acme-corp/custom.css \
  --logo customization/customers/acme-corp/logo.svg \
  --background customization/customers/acme-corp/background.jpg \
  --dry-run    # prints the diff vs. current, doesn't apply
```

Uploads the named files to the object store, returns a bundle ID, enqueues `custom.branding.apply` with that bundle ID. Agent downloads and applies in one atomic step.

---

## Config file

`~/.config/mgmt-ctl/config.yaml`:

```yaml
server: https://mgmt.internal.example.com
default_output: human
# refresh tokens go in session.json, not here

# Optional per-profile server targets
profiles:
  staging:
    server: https://mgmt-staging.internal.example.com
```

Use profiles via `mgmt-ctl --profile staging <cmd>`.

---

## Exit codes

- `0` — success.
- `1` — user error (unknown command, bad arg, validation failure).
- `2` — auth error (not logged in, token expired, permission denied).
- `3` — server error (5xx).
- `4` — agent-side error (command executed but failed inside the customer).
- `5` — timeout (command stayed queued longer than `--timeout` allows).

Non-zero exits print to stderr; stdout is reserved for the command's own output (so `--json` output is always pipe-safe).

---

## Environment variable overrides

- `MGMT_CTL_SERVER` — override default server.
- `MGMT_CTL_TOKEN` — skip interactive login (for CI/scripts). Must be a service API key, not a user SSO token.
- `MGMT_CTL_CONFIG` — alternate config file path.
- `NO_COLOR=1` — disable ANSI output.

---

## Implementation notes

- Single static Go binary. Cross-compiled for Linux, macOS (intel + arm), Windows.
- Ships with `completion` subcommand generating bash/zsh/fish completion scripts.
- Updates distributed via the same GitHub Action that builds the base image; `mgmt-ctl self-update` pulls the latest.
- Every command sends `X-Request-ID` (uuid v7) so operator and server logs can be correlated during incidents.
- Timeouts default to 60s; commands with a known-long tail (`upgrade`, `restore`) default to 30min.
