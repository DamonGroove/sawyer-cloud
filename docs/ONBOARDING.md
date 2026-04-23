# Onboarding a new customer

End-to-end checklist for an engineer onboarding a new customer to the
sawyer-cloud fleet. Goes from "we have a signed contract" to "customer
is healthy on production image and mgmt-ctl sees them."

Assumes:
- The staging and management servers are already up (see
  `docs/STAGING_SETUP.md` if not).
- A `default` flavor (or whatever flavor the customer is subscribing
  to) exists in `customization/flavors/`.
- `mgmt-ctl` is installed on your laptop (`make -C management-server/cli
  build` then `cp bin/mgmt-ctl ~/bin/`).
- You have the `admin` role on the management server.

---

## 1. Create the customer folder in git

Pick a slug. Must be lowercase alphanumeric with hyphens, 1–63 chars,
no leading/trailing hyphen. This is the URL-safe identifier used in
every `mgmt-ctl` command and the folder name under
`customization/customers/`.

```bash
cd <repo-root>
git switch -c customer/<slug>/bootstrap

# Copy from the flavor. Gets you the default flavor.env + custom.css.
cp -r customization/flavors/<flavor>/ customization/customers/<slug>/

# Rename the entry file and edit it.
mv customization/customers/<slug>/flavor.env customization/customers/<slug>/customer.env
$EDITOR customization/customers/<slug>/customer.env
```

Required edits in `customer.env`:

| Key | Value |
|---|---|
| `CUSTOMER_NAME` | the slug, again |
| `CUSTOMER_FLAVOR` | the flavor slug |
| `CUSTOMER_DOMAIN` | the public FQDN (e.g. `cloud.acme.example.com`) |
| `CUSTOMER_DISPLAY_NAME` | human name for branding |
| `CUSTOMER_PRIMARY_COLOR` | hex with `#` prefix |
| `MGMT_SERVER_URL` | the management-server endpoint |

See `customization/customers/example-customer/customer.env` for the
complete shape, including optional sections (Cloudflare Tunnel, EWS,
AI, SMB mounts).

## 2. Register the customer on the management server

```bash
mgmt-ctl customers create <slug> \
    --display-name "Customer Display Name" \
    --domain "cloud.customer.example.com" \
    --flavor <flavor-slug> \
    --site-mode docker
```

This returns a one-time **registration token** of the form
`<opaque>.<customer-uuid>`. You need it in step 3.

## 3. Seal the registration token into the customer secret bundle

```bash
# Get the team's age recipient list; the customer's decrypt key is
# distributed separately to the host that will run the container.
printf 'MGMT_REGISTRATION_TOKEN=<token>\n' \
    | age --encrypt -R engineering.age.pubkeys \
    > customization/customers/<slug>/customer.env.secret.age

# Double-check:
age --decrypt -i ~/.ssh/age.key \
    < customization/customers/<slug>/customer.env.secret.age \
    | grep MGMT_REGISTRATION_TOKEN
```

NEVER commit the plaintext token. `.gitignore` already excludes
`*.secret` / `*.secret.decrypted` but the `*.secret.age` file IS
tracked — age-encrypted artifacts are safe as long as the private key
doesn't leak.

## 4. Commit the customer folder

```bash
git add customization/customers/<slug>/
git commit -m "customer/<slug>: bootstrap"
git push -u origin customer/<slug>/bootstrap
```

Open a PR and request an engineering review. The PR triggers the
`base-image-build` and (on merge to main) `staging-deploy` workflows;
neither of these needs to run for the per-customer deploy below — a
customer deploy consumes whatever `:production` tag is currently
promoted.

## 5. Deploy

Pick the deployment path based on the customer's site mode:

### 5a. Docker deployment (default)

On the customer's host:

```bash
# One-time: install docker, age, and clone the repo. Or pull the Packer
# VM image and skip this box entirely — see 5b.
git clone https://github.com/sawyer-cloud/sawyer-cloud /srv/sawyer-cloud
cd /srv/sawyer-cloud
# Install the customer's decrypt key (distributed securely to the host).
install -m 0600 /dev/stdin /etc/sawyer-cloud/age.key <<< "$AGE_PRIVATE_KEY"

# Decrypt the customer secret bundle into a process-env file.
age --decrypt -i /etc/sawyer-cloud/age.key \
    < customization/customers/<slug>/customer.env.secret.age \
    > /run/secrets/<slug>.env
chmod 0600 /run/secrets/<slug>.env

# Source both env files and bring the stack up.
set -a
. customization/flavors/<flavor>/flavor.env
. customization/customers/<slug>/customer.env
. /run/secrets/<slug>.env
set +a
docker compose \
    -f compose.yaml \
    -f customization/overlays/docker-compose.override.yaml \
    up -d
```

### 5b. VM deployment

Packer produces qcow2/vmdk/raw images (`scripts/packer/`). The
customer's hypervisor provisioner drops a config drive (or 9p share)
at `/mnt/sawyer-config/` containing `customer.env` and
`customer.env.secret.age` plus the age decrypt key. The baked
`first-boot.service` picks everything up on first boot.

## 6. Verify registration

On your laptop:

```bash
mgmt-ctl customers show <slug>
# state=pending → first agent tick will flip it to healthy.

# After ~1 minute:
mgmt-ctl customers show <slug>
# state=healthy, last_seen_at recent.
```

If state stays `pending` after 5 minutes, check:

```bash
# On the customer host:
docker logs nextcloud-aio-customer-agent --tail 100
```

Common issues:
- `registration token already consumed` — re-issue via
  `mgmt-ctl enroll <slug>`, re-seal, re-deploy.
- `registration rejected` — slug in `customer.env` doesn't match the
  server record; compare both.
- `mtls handshake failed` — the server's CA bundle isn't trusted by
  the agent container. Usually a clock skew issue or a stale image.

## 7. Smoke test

```bash
mgmt-ctl health <slug> --full    # (501 in Phase 2; once implemented, you'll see cron status, job queue depth, DB size)
mgmt-ctl occ <slug> status       # (501 in Phase 2)
```

Until those routes land, log in to the customer's Nextcloud and
confirm: branding applied, customer's expected apps enabled, any
configured external storage mounts visible.

## 8. Put the customer in the rotation

Add the customer to the team's monitoring, oncall doc, and backup
retention policy. The management server doesn't own these yet; it's
currently doc-only in `docs/INCIDENT_PLAYBOOK.md`.

---

## Decommissioning

For the inverse flow — same docs, different direction:

```bash
mgmt-ctl --yes customers decommission <slug>   # irreversible
# Manually tear down the customer's host afterward; the management
# server doesn't orchestrate host deletion (yet).
```

`decommission` flips the customer's state, revokes the agent cert, and
purges future command history for that customer. Past audit entries
are NEVER deleted — that's the whole point of the audit table.
