# Incident Playbook

**Purpose:** concrete, ordered steps for the most common customer-down scenarios. Optimized for the operator, not engineering — these assume you can run `mgmt-ctl`, read logs Claude retrieves for you, and make rollback decisions under pressure.

**Prime directive during an incident: restore service first, diagnose after.** Do not make code changes on the hot path. Do not edit files under pressure. Use `mgmt-ctl` rollback and restart actions, and escalate if the rollback path is not obvious.

---

## Incident priority ladder

1. **P0 — customer totally down** (Nextcloud returns 5xx on every request, can't log in). Page `#nextcloud-oncall` immediately AND start diagnosis.
2. **P1 — critical feature broken** (can't upload files, can't send shares, AI Assistant failing, Exchange sync stopped). Fix within business hours; page if after hours and customer is large.
3. **P2 — degraded but usable** (slow, some containers crash-looping but Nextcloud still serves). Open a ticket, fix next business day.

Err toward paging. Operators don't get in trouble for paging engineering; they get in trouble for silently wrestling a P0 alone.

---

## First five minutes (every incident)

Run these three commands at the top of any incident, regardless of symptom. They gather the context engineering will ask for.

```
mgmt-ctl status <slug>
mgmt-ctl health <slug> --full
mgmt-ctl audit list --customer <slug> --since "24 hours ago"
```

Capture the output in the Slack thread. This alone answers half the questions an on-call engineer would ask.

---

## Playbook 1: Customer can't reach Nextcloud at all (P0)

**Symptoms:** `curl https://cloud.<customer>.example.com` returns connection refused, timeout, or TLS handshake failure.

### Step 1: Is the instance online from our side?

```
mgmt-ctl status <slug>
```

- If `state=offline` and `last_seen > 5 minutes`: the customer-agent is not reporting. Either the whole host is down, or the agent container crashed, or the customer's egress to our management server is broken.
- If `state=healthy` but customer says down: the agent is up but Apache isn't serving. Different problem. Jump to Step 3.

### Step 2: If the agent is offline

The most likely cause is the customer's host is down or networking is broken. You probably need the customer's ops team, not us. Ask the operator to:

- Confirm the VM/host is running.
- Confirm outbound HTTPS to `mgmt.internal.example.com:443` is allowed.
- If cloudflared is involved, confirm the Cloudflare tunnel status in the Cloudflare dashboard.

If the host is up but the agent is down, engineering can SSH in via the break-glass process. Do not do that as an operator.

### Step 3: Apache/containers broken

```
mgmt-ctl logs <slug> --container nextcloud-aio-apache --tail 200
mgmt-ctl logs <slug> --container nextcloud-aio-mastercontainer --tail 200
```

Common patterns:

- **"certificate expired"** or **"Let's Encrypt rate limit"** — cert renewal failed. Nudge AIO to retry:
  ```
  mgmt-ctl occ <slug> config:system:delete installed_version
  mgmt-ctl restart <slug> --container nextcloud-aio-apache
  ```
- **"connection refused to database"** — Postgres crashed. Rare but possible. Restart the Postgres container:
  ```
  mgmt-ctl restart <slug> --container nextcloud-aio-database
  mgmt-ctl restart <slug> --container nextcloud-aio-nextcloud
  ```
- **"no route to host"** between containers — the Docker network is broken. Escalate to engineering; the fix usually involves restarting the mastercontainer, which is an OVERRIDE action.
- **"out of disk space"** — Nextcloud's data dir filled up. This is urgent but not fixable by an operator. Engineering, now.

### Step 4: If the last change was an upgrade in the last 24 hours

```
mgmt-ctl audit list --customer <slug> --action "aio.image.upgrade" --since "24 hours ago"
```

If there was one, roll back:

```
mgmt-ctl rollback <slug>
```

This is the first thing to try and it's usually the right answer. Rollback takes ~90 seconds. If it works, the incident is over; open a post-incident ticket to investigate the failed upgrade on staging.

### Step 5: If rollback doesn't help

Restore from the latest backup:

```
mgmt-ctl backups list <slug>            # find the most recent pre-incident backup
mgmt-ctl restore <slug> --archive <id>
```

**This is destructive** — it overwrites current state. Confirm with the customer first: data since the backup will be lost. Usually the latest backup is < 24h old so the loss is minor.

### Step 6: Nothing worked

Page `#nextcloud-oncall` with:

- Customer slug and timeline of symptoms
- Output from Step 1's three commands
- What you've already tried
- Whether rollback and restore were attempted

Engineering will likely SSH in via break-glass.

---

## Playbook 2: AI Assistant errors (P1)

**Symptoms:** users see "Assistant error," "model not found," or long timeouts when using AI features.

### Provider first

```
mgmt-ctl occ <slug> config:app:get integration_openai url
mgmt-ctl occ <slug> config:app:get integration_openai default_completion_model_id
```

Confirm URL points to what you expect (`http://nextcloud-aio-ollama:11434/v1`, `http://nextcloud-aio-litellm:4000/v1`, or `https://api.openai.com/v1`). If not, re-apply AI config:

```
mgmt-ctl apply --customer <slug> --section ai
```

### Provider-specific diagnosis

**Ollama:**
```
mgmt-ctl logs <slug> --container nextcloud-aio-ollama --tail 100
```
Common: `model not found` → model not pulled. Run `mgmt-ctl ollama pull <slug> <model>`. Common: `out of memory` → model too large for host RAM; pick smaller model or rightsize the host.

**LiteLLM:**
```
mgmt-ctl logs <slug> --container nextcloud-aio-litellm --tail 100
```
Common: `401 from provider` → the provider's API key (ANTHROPIC_API_KEY, etc.) is wrong in LiteLLM's env. Rotate via `mgmt-ctl litellm:rotate <slug>` (if operator role) or engineering. Common: `rate limit` from upstream provider → fallback routing kicked in; check LiteLLM's `config.yaml` fallback chain.

**OpenAI direct:**
```
mgmt-ctl occ <slug> config:app:get integration_openai api_key
```
(Redacted in the output by the audit filter.) If the customer rotated their OpenAI key, update via `mgmt-ctl apply --customer <slug> --section ai` after fixing the secret.

### If the whole Assistant app is broken

```
mgmt-ctl occ <slug> app:disable assistant
mgmt-ctl occ <slug> app:enable assistant
```

A quick bounce is often enough for stuck background jobs.

---

## Playbook 3: Exchange sync stopped (P1)

**Symptoms:** calendar events from Exchange aren't appearing, contacts out of sync, user says "it was working yesterday."

### Per-user or fleet-wide?

Exchange sync is per-user. Ask the customer: "one user or multiple users affected?"

- **One user:** almost certainly their credentials expired, or Exchange-side MFA kicked in. The user re-auths via Personal Settings → Connected Accounts. This is self-service; nothing for us to do.
- **Multiple users simultaneously:** the Exchange server itself is blocking us, or the CA cert chain broke.

### Multi-user case diagnosis

```
mgmt-ctl logs <slug> --container nextcloud-aio-nextcloud --tail 200 | grep -i ews
```

Common patterns:

- **"SSL certificate verification failed"** — Exchange renewed their cert with a chain we don't trust. If they use a private CA, refresh the CA bundle:
  ```
  # Engineering task: replace customization/customers/<slug>/cacerts/*.pem with new PEMs
  # Then:
  mgmt-ctl apply --customer <slug> --section exchange
  mgmt-ctl restart <slug> --container nextcloud-aio-nextcloud
  ```
- **"429 too many requests"** — Exchange is rate-limiting us. Reduce the sync frequency:
  ```
  mgmt-ctl occ <slug> config:app:set integration_ews sync_interval --value 900
  ```
  (15 minutes instead of the default 5.) Customer should also check their Exchange-side throttling policy.
- **"401 unauthorized"** — EWS was disabled on the Exchange server, or service account locked out. Exchange-side issue, not ours. Escalate to the customer's Exchange admin.

---

## Playbook 4: Backups failing (P1)

**Symptoms:** `mgmt-ctl backups list <slug>` shows no recent backup, or the last backup's status is `failed`.

### Diagnose

```
mgmt-ctl logs <slug> --container nextcloud-aio-borgbackup --tail 200
```

Common patterns:

- **"no space left on device"** — backup target (local or remote) is full. Operator can't fix the target; escalate to the customer's ops. If local, `mgmt-ctl occ <slug> backup:prune` can free space by applying retention (operator role has this).
- **"connection timed out"** to remote borg — network to the remote repo broke. Check with the customer's network team. Meanwhile, a local backup is still better than no backup: switch the target temporarily:
  ```
  mgmt-ctl backups set-target <slug> --type local --path /mnt/backup
  mgmt-ctl backup <slug>
  ```
- **"borg repository locked"** — a previous backup crashed without releasing its lock. Force-unlock (OVERRIDE: action — the lock exists for good reason):
  ```
  OVERRIDE: Previous borg backup crashed leaving repository lock; no concurrent backup is running.
  mgmt-ctl occ <slug> borg:break-lock
  ```

### Manual backup right now

If automated backups are flaky, take a manual backup to establish a known-good restore point:

```
mgmt-ctl backup <slug> --label "pre-upgrade-$(date +%Y-%m-%d)"
```

This unblocks upgrades even while the scheduled backup is being fixed.

---

## Playbook 5: Cloudflare Tunnel disconnected (P1)

**Symptoms:** Cloudflare dashboard shows the tunnel as offline; users get Cloudflare's "522" error page or "tunnel unavailable."

### Check the cloudflared container

```
mgmt-ctl logs <slug> --container nextcloud-aio-cloudflared --tail 100
```

Common patterns:

- **"invalid token"** — the tunnel token was rotated in the Cloudflare dashboard but not updated in our env. Update `CLOUDFLARE_TUNNEL_TOKEN` in `customer.env.secret.age` and redeploy:
  ```
  mgmt-ctl apply --customer <slug> --section cloudflared
  ```
- **"connection reset"** on the tunnel dial — Cloudflare's edge is having trouble, usually transient. Check Cloudflare's status page. If it's an outage on their side, no action; tunnel reconnects when they recover.
- **"origin unreachable"** — the tunnel is up but can't reach Apache inside the customer's network. Usually means `APACHE_PORT` and `APACHE_IP_BINDING` don't match between the tunnel config and the mastercontainer. Verify:
  ```
  mgmt-ctl occ <slug> config:system:get overwrite.cli.url
  ```
  Should match the customer's domain. If not:
  ```
  mgmt-ctl apply --customer <slug> --section cloudflared
  ```

### Emergency: bypass the tunnel

If the tunnel is totally broken and the customer needs access NOW, they can add a direct DNS A-record pointing to their server's public IP and update `overwrite.cli.url` accordingly. **This disables Cloudflare's DDoS protection and exposes the instance to the internet directly.** Operator needs `OVERRIDE:` for the `overwrite.cli.url` change, and the change must be reverted within 24h. Engineering-coordinated.

---

## Playbook 6: Disk full (P0 in effect)

**Symptoms:** users can't upload; `mgmt-ctl health <slug>` shows >95% disk used.

### Immediate relief (minutes)

1. **Check backup retention** — old borg backups are the usual culprit:
   ```
   mgmt-ctl occ <slug> borg:list
   ```
2. **Prune backups** to the retention policy (usually keeps most recent ~30):
   ```
   mgmt-ctl occ <slug> borg:prune
   ```
3. **Clear Nextcloud's trashbin fleet-wide** for all users (destructive but not catastrophic — users know trash isn't forever):
   ```
   OVERRIDE: Customer disk at 97%, blocking uploads. Clearing trashbin to restore service.
   mgmt-ctl occ <slug> trashbin:cleanup
   ```
4. **Check for runaway logs**:
   ```
   mgmt-ctl occ <slug> log:file --size
   ```
   If multi-GB, rotate:
   ```
   mgmt-ctl occ <slug> log:rotate
   ```

### Medium term (hours)

Disk growth is almost always backups or user file growth. Look at `mgmt-ctl health <slug> --full` for the breakdown, and work with the customer on a permanent fix: increase disk, move backups off-host, tune retention, add per-user quotas.

---

## Playbook 7: Post-incident

Every P0 or P1 incident requires a post-incident writeup within 3 business days. Template:

- **What happened** — 1 paragraph, timeline-free summary.
- **Timeline** — UTC timestamps from Slack + audit log.
- **Root cause** — the actual thing that failed, not "the symptom."
- **What fixed it** — the specific action (rollback, restore, config change) that returned service.
- **What we'd do differently** — actionable. Not "we should communicate better" — "we'll add an alert at 80% disk."

Writeups go in `docs/postmortems/YYYY-MM-DD-<slug>-<short>.md` and are read at the next engineering meeting.

---

## When to escalate (not tough-it-out)

- Anything involving `upstream/` edits, even if it looks harmless.
- Anything touching `management-server/auth/`.
- Anything touching secrets (rotation, leak, suspected exposure).
- Rollbacks that fail AND restores that fail AND customer is down.
- Suspected compromise: unexpected admin logins, new NC apps you didn't install, config changes in the audit log you didn't make, unusual traffic in logs.
- Data loss — actual customer files missing. Stop all automated jobs (`mgmt-ctl backups pause <slug>`) before anything else so you don't overwrite a good backup with a bad one.
