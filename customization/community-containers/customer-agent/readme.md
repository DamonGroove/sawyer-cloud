# customer-agent

The sawyer-cloud management-server agent. One instance per customer
deployment. Always-on; enabled by default by the compose overlay.

## What it does

- Registers with the management server using a **one-time** token
  (`MGMT_REGISTRATION_TOKEN`) at first boot. The token is consumed on the
  first `POST /agents/register` and becomes invalid immediately. The
  server returns an mTLS cert + key which the agent persists to
  `/var/lib/customer-agent/` (the `customer_agent_state` volume).
- Long-polls the management server's `POST /agents/tick` endpoint
  (MANAGEMENT_SERVER.md §4.2) for commands to execute.
- Executes commands against the local AIO stack by calling the
  mastercontainer's HTTP API — the agent explicitly does NOT mount the
  docker socket and cannot run arbitrary shell (MANAGEMENT_SERVER.md
  §4.5).
- Reports command results and heartbeat back via `POST
  /agents/commands/{id}/result` and `POST /agents/log`.

## Env vars

| Var | Default | Notes |
|---|---|---|
| `MGMT_SERVER_URL` | — | Required. HTTPS URL of the management server. |
| `CUSTOMER_NAME` | — | Required. Matches `customization/customers/<n>/`. |
| `AGENT_STATE_DIR` | `/var/lib/customer-agent` | mTLS cert + last-seen command ID live here. |
| `AGENT_TICK_INTERVAL_SECONDS` | `20` | Backoff between long-polls. |

## Secrets

| Name | Purpose |
|---|---|
| `MGMT_REGISTRATION_TOKEN` | One-time token issued by `mgmt-ctl enroll <slug>`. Must be placed in `customization/customers/<n>/customer.env.secret.age` before first deploy. |

After first registration, the token is consumed and this secret can be
removed (the agent uses its mTLS cert thereafter). Rotating the cert is
done with `mgmt-ctl agents rotate <slug>` which triggers an in-place
cert swap without re-enrollment.

## Registration failure modes

- **"token already consumed"** — the customer has registered previously.
  Use `mgmt-ctl enroll <slug>` to issue a fresh token (invalidates the
  old one) and re-deploy.
- **"revoked"** — someone ran `mgmt-ctl agents revoke <slug>`. The
  customer is deliberately offline. Re-enroll via `mgmt-ctl enroll`.
- **"mTLS handshake failed"** — the cert expired or the management
  server's CA rotated. `mgmt-ctl agents rotate <slug>` issues a new cert.

See INCIDENT_PLAYBOOK.md §"Agent offline" for the operator-facing runbook.
