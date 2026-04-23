# mgmt-ctl

The thin operator CLI for the sawyer-cloud management server. Every
command maps 1:1 to a management-server API call.

**The spec is `management-server/CLI_SPEC.md`** (formerly `MGMT_CTL_CLI_SPEC.md`
at the repo root before Phase 0 archived it). This README covers how to
build, run, and navigate the CLI; the spec covers what each command
does, return shapes, and design principles.

---

## Build

```bash
cd management-server/cli
make build               # → bin/mgmt-ctl (host platform)
make release             # → bin/release/mgmt-ctl-{linux,darwin,windows}-{amd64,arm64}
```

The binary is statically linked (CGO_ENABLED=0), stripped, and stamps
its version from `git describe` at link time.

Requirements:
- Go 1.24+ (see `go.mod`).
- If the `sum.golang.org` fetcher is unreachable in your environment,
  set `GOSUMDB=off` before `make build`. The Makefile already exports
  that default.

## Run

```bash
./bin/mgmt-ctl --help
```

Global flags (MGMT_CTL_CLI_SPEC.md §Config file + env):

| Flag / env | Purpose |
|---|---|
| `--server`, `MGMT_CTL_SERVER` | management-server base URL |
| `--profile` | named profile from `~/.config/mgmt-ctl/config.yaml` (overrides `--server`) |
| `--json` | raw JSON output instead of the human summary |
| `-y`, `--yes` | skip interactive confirmation for destructive commands |

## Login

### OIDC device-code (production path)

```bash
./bin/mgmt-ctl login \
    --issuer https://auth.example.com \
    --client-id mgmt-ctl
```

`mgmt-ctl` fetches a user-code and verification URL from the issuer,
prints them, then polls until you complete auth in a browser. The
resulting tokens land at `~/.config/mgmt-ctl/session.json` (mode 0600).

### Dev login (local testing)

When the management server runs with `ENVIRONMENT=dev` it exposes
`POST /api/v1/auth/dev-login` which mints a JWT directly. Useful for
testing without a real IdP:

```bash
./bin/mgmt-ctl --server http://127.0.0.1:8080 \
    login --dev-email you@example.com --dev-roles engineering
./bin/mgmt-ctl --server http://127.0.0.1:8080 whoami
```

The server 404s the endpoint in any non-dev environment.

## What's implemented in Phase 3

Per BOOTSTRAP.md §4 Phase 3, the following commands are fully wired
end-to-end to the management-server API:

| Command | Server endpoint |
|---|---|
| `login` (device-code + `--dev-email` variant) | `POST /api/v1/auth/dev-login` or external IdP |
| `logout` | `POST /api/v1/auth/logout` (best-effort) + local session clear |
| `whoami` | `GET /api/v1/users/me` |
| `customers list [--flavor] [--state]` | `GET /api/v1/customers` |
| `customers show <slug>` | `GET /api/v1/customers/{slug}` |
| `customers create <slug> --display-name --domain --flavor [--site-mode]` | `POST /api/v1/customers` |
| `enroll <slug>` | `POST /api/v1/customers/{slug}/enroll` |
| `backup <slug> [--label]` | `POST /api/v1/customers/{slug}/backups` |
| `restore <slug> --archive` | `POST /api/v1/customers/{slug}/backups/{id}/restore` |
| `rollback <slug>` | `POST /api/v1/customers/{slug}/rollback` |
| `upgrade <slug> --to <tag>` | `POST /api/v1/customers/{slug}/upgrade` |

Everything else in MGMT_CTL_CLI_SPEC.md's command tree is a stub that
exits 1 with "not implemented in Phase 3". The shape of the tree is
intact so shell completion generates correctly and later sprints can
replace stubs without restructuring.

## Layout

```
cli/
├── main.go               tiny; delegates to cmd.Execute()
├── cmd/                  cobra command tree (root, session, customers, …)
├── pkg/
│   ├── client/           HTTP client (error mapping, X-Request-ID, idempotency-key)
│   ├── auth/             session.json management + OIDC device-code flow
│   └── output/           --json vs human formatter split
├── Makefile              build / release / test / lint
└── go.mod                deps: cobra, yaml.v3
```

## Exit codes

Per MGMT_CTL_CLI_SPEC.md §Exit codes:

- `0` — success
- `1` — user error (unknown cmd, bad args, validation)
- `2` — auth error (not logged in, token expired, permission denied)
- `3` — server error (5xx, including 501)
- `5` — timeout (408, 504)

## Completions

Cobra's built-in completion subcommand is included:

```bash
./bin/mgmt-ctl completion bash >/etc/bash_completion.d/mgmt-ctl
# or
./bin/mgmt-ctl completion zsh >"${fpath[1]}/_mgmt-ctl"
```

## Known Phase 3 caveats

- `restore <slug> --archive` does not yet send the `X-Confirm: restore-overwrites-state`
  header the server spec wants. The server route is itself 501-stubbed
  in Phase 2 so this is not observable today; the follow-up is to add
  `Client.DoWithHeaders` for per-call header injection.
- Silent token refresh is a no-op stub. When the access token expires,
  `mgmt-ctl` reports the 401 from the server and tells the user to run
  `mgmt-ctl login` again. The real refresh flow lands with the real OIDC
  IdP integration.
- `completion` is Cobra's default; no sawyer-specific custom completions
  beyond what cobra infers from the command tree.
