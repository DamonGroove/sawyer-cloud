# Staging server setup

One-time setup for the staging Linux host that
`.github/workflows/staging-deploy.yml` deploys to. Engineer-operated,
runs once; after that the workflow re-syncs the repo on every push to
`main`.

## 1. Provision the host

Minimum viable machine:

- Ubuntu 24.04 LTS (matches `scripts/packer/aio-base.pkr.hcl`'s base).
- 4 vCPU, 8 GB RAM, 80 GB disk.
- Public DNS name — call it `staging.sawyer-cloud.internal` in the
  examples below. Must resolve from wherever GitHub Actions runners
  live.
- SSH accessible on port 22 with a dedicated key; the workflow uses
  it as `$STAGING_USER`.

## 2. Install docker + age

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg age rsync
curl -fsSL https://get.docker.com | sudo sh
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"   # log out and back in for group to apply
```

Verify:

```bash
docker ps          # should work without sudo
age --version      # 1.x, not the Rust fork
rsync --version    # 3.x
```

## 3. Create the deploy user + directory

```bash
sudo useradd --create-home --shell /bin/bash --groups docker sawyer
sudo install -d -o sawyer -g sawyer -m 0755 /srv/sawyer-cloud-staging
sudo -u sawyer mkdir -p /srv/sawyer-cloud-staging/{customization,secrets}
```

Install the workflow's public SSH key:

```bash
sudo -u sawyer install -d -m 0700 /home/sawyer/.ssh
# paste the STAGING_SSH_KEY's public half into the next line.
echo "ssh-ed25519 AAAA… sawyer-cloud-ci" \
    | sudo -u sawyer tee /home/sawyer/.ssh/authorized_keys
sudo -u sawyer chmod 600 /home/sawyer/.ssh/authorized_keys
```

Test from your laptop:

```bash
ssh -i ~/.ssh/sawyer-cloud-staging.key sawyer@staging.sawyer-cloud.internal true
```

## 4. Seed the staging-customer folder

```bash
sudo -u sawyer git clone \
    https://github.com/DamonGroove/sawyer-cloud \
    /srv/sawyer-cloud-staging
cd /srv/sawyer-cloud-staging

# Create a dedicated "staging-customer" so the real customers are never
# exposed to staging deploys.
sudo -u sawyer cp -r \
    customization/flavors/default \
    customization/customers/staging-customer
sudo -u sawyer mv \
    customization/customers/staging-customer/flavor.env \
    customization/customers/staging-customer/customer.env

# Edit staging-customer/customer.env. At minimum:
#   CUSTOMER_NAME=staging-customer
#   CUSTOMER_DOMAIN=staging.sawyer-cloud.internal
#   MGMT_SERVER_URL=https://mgmt-staging.sawyer-cloud.internal
```

## 5. Enroll staging-customer with the management server

From your laptop, against the staging management server:

```bash
mgmt-ctl --server https://mgmt-staging.sawyer-cloud.internal \
    customers create staging-customer \
    --display-name "Staging" \
    --domain staging.sawyer-cloud.internal \
    --flavor default

# Copy the returned token. On the staging host:
echo "MGMT_REGISTRATION_TOKEN=<token>" \
    | age --encrypt -R /home/sawyer/age.pubkeys \
    > /srv/sawyer-cloud-staging/customization/customers/staging-customer/customer.env.secret.age
```

The decrypt key for `staging.age.key` lives on the host only —
engineering rotates it yearly and does NOT commit it.

## 6. Register GitHub Actions secrets

In the repo's Settings → Environments → `staging`:

| Secret | Value |
|---|---|
| `STAGING_HOST` | `staging.sawyer-cloud.internal` |
| `STAGING_USER` | `sawyer` |
| `STAGING_SSH_KEY` | private half of the key from step 3 |

`GITHUB_TOKEN` is auto-provisioned; don't add one manually.

## 7. First deploy

Trigger the workflow manually the first time:

```
Actions → Staging deploy → Run workflow → main
```

Watch the run. It runs `scripts/deploy-staging.sh` on the host which:

1. Pulls `ghcr.io/sawyer-cloud/aio-base:<git-sha>`.
2. Rsyncs the repo to `/srv/sawyer-cloud-staging/`.
3. `docker compose up -d` against compose.yaml + overlay.
4. Waits for Nextcloud to be ready (up to 10 minutes).
5. Runs `bootstrap-aio` in `update` mode to apply theming / apps.
6. Runs `scripts/smoke-test/test_staging.py` against `/status.php` +
   six occ checks.
7. Writes `.staging-green-marker` on success.

## 8. Firewall & TLS

For the bare-minimum private deploy, the AIO Apache binds to
`127.0.0.1:11000` via the overlay's `APACHE_IP_BINDING` default.
Front it with either:

- **Caddy** (we ship `customization/overlays/Caddyfile` as a starter)
  on the host, terminating Let's Encrypt TLS. Add to the staging
  firewall rules: 80/tcp and 443/tcp open to the world; 22/tcp open
  to your VPN egress only.
- **Cloudflare Tunnel** (the §3.1 path). No inbound firewall rules
  needed.

Staging typically uses Caddy so the team can reach it from office
networks without a cloudflared keybundle.

## 9. Monitoring

The management server itself emits structured JSON logs to stdout.
Fanout to Loki / Datadog / whatever the team uses is wired at the
orchestration layer, not here — document the destination in the
runbook.

`mgmt-ctl health staging-customer --full` will eventually be the
one-stop health check; until it's implemented (Phase 4+ feature work),
check `docker ps` + the AIO web UI at `https://staging.sawyer-cloud.internal:8080/`.

## Rolling forward

When a new base image lands (`base-image-build.yml` has pushed a tag
of the form `sha-<shortsha>`), the `staging-deploy.yml` workflow
automatically re-runs against it. No human intervention required on
the staging host. If a deploy goes red, the `.staging-green-marker`
doesn't get written, and engineering manually investigates via `ssh
sawyer@staging`.

Production customers continue to run the previous `:production` tag
until engineering manually promotes the new tag via
`mgmt-ctl images promote <tag> --to production` (eventually — that
route is 501 in Phase 2; use the SQL escape hatch until it lands).
