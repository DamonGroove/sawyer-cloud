# Operator Tasks — Quick Reference

A one-page-ish cheatsheet. For narrative / explanation, see `README.md`. For the rules Claude enforces, see `CLAUDE.md`.

---

## Prompt templates (copy, fill, send)

### Onboarding
```
Onboard customer <slug> on flavor <default|law-firm> with domain <domain>.
```

### Branding
```
For customer <slug>, set the primary color to <#hex>, slogan to "<text>",
and use logo at customization/customers/<slug>/logo.svg.
```

### CSS tweak
```
For <slug>, add CSS that <describe effect>. Scope: <customer|flavor>.
```

### JS tweak
```
Add JavaScript to the <flavor> flavor that <describes effect>. No framework.
```

### Cloudflare Tunnel
```
Add a Cloudflare Tunnel for customer <slug>. The token is in my clipboard.
```

### Enable/disable feature
```
Enable <talk|collabora|clamav|imaginary|whiteboard|fulltextsearch>
for customer <slug>.
```

### Community container
```
Enable the <fail2ban|local-ai|pi-hole|ollama|litellm|lldap> community
container for customer <slug>.
```

### Nextcloud app
```
Install the <app-id> app for customer <slug>.
```

### SMB mount
```
For customer <slug>, mount SMB share \\<host>\<path> at "<NC path>" as
<admin|group:finance-team|user:alice>. Service account <username>.
```

### Exchange
```
Enable Exchange EWS for customer <slug>. Exchange host: <mail.host>.
Self-signed cert path: </tmp/ca.pem>.
```

### AI
```
Enable AI Assistant for <slug> using <openai|ollama|litellm|localai>
with model <model-name>.
```

### Resource limits
```
For <slug>, set upload limit to <32G>, memory to <1024M>,
and max exec time to <7200> seconds.
```

### Backup / restore / upgrade (these are mgmt-ctl, not file edits)
```
Trigger backup for <slug>.
Restore <slug> from archive <id>.
Upgrade <slug> to image tag <staging-green|sha-...>.
```

### Pull upstream
```
Pull the latest upstream Nextcloud AIO.
```

---

## OVERRIDE: template

For anything on the deny-list:

```
OVERRIDE: <single sentence describing a legitimate reason>

<your actual request>
```

Examples:

```
OVERRIDE: Customer ACME needs tesseract-ocr-data-deu in addition to English
for their German document archive workflow.

Add the tesseract-ocr-data-deu Alpine package for customer acme-corp.
```

```
OVERRIDE: Customer request to install their internal-reviewed Nextcloud
app from their private git repo, not the public app store.

Install the "foo-internal" app for customer foo-corp from
git.foo.example.com/foo-internal, release tag v1.2.3.
```

---

## Diagnostic commands (run in terminal, not asked of Claude)

```
mgmt-ctl whoami                     # which customers you're allowed to touch
mgmt-ctl customers list              # fleet overview
mgmt-ctl status <slug>               # one-line health
mgmt-ctl health <slug> --full        # detailed
mgmt-ctl logs <slug> --container nextcloud-aio-apache --tail 100
mgmt-ctl audit list --customer <slug> --since "24 hours ago"
mgmt-ctl backups list <slug>
mgmt-ctl images list                 # what tags exist
mgmt-ctl features list --customer <slug>
```

Claude can print these for you if you ask — e.g., "give me the diagnostic for <slug>."

---

## What Claude will refuse (expected — not a bug)

If Claude refuses, its message says WHY. Three categories:

1. **"Requires override"** — prefix your next message with `OVERRIDE: <reason>`.
2. **"Locked — engineering only"** — open a ticket in `#nextcloud-ops`.
3. **"I need clarification"** — answer the one question, resend.

See README §6 for detail.

---

## Common pitfalls

- Forgetting to name the customer. Claude will ask; you'll save a round-trip by naming up front.
- Running the same `OVERRIDE:` request twice because the first one didn't work. Read the refusal — if it said "locked," `OVERRIDE:` doesn't help.
- Changing branding on a flavor when you meant a customer. Always say "for customer X" unless you actually want flavor-wide.
- Forgetting that Cloudflare Tunnel has known limitations (100MB upload cap on free plan, 100s request timeout, no TURN). Tell customers before enabling.
- Installing a Nextcloud app without `OVERRIDE:` when the app isn't on the public app store. Claude will refuse; `OVERRIDE:` with a link to the app source is the right move.

---

## When to escalate

Always:
- Customer is down and rollback + restore both failed.
- Data loss reported (missing files, wrong permissions on files).
- Suspected compromise (weird admin logins, unknown apps, audit log entries you didn't make).
- Encryption key rotation needed.
- Anything mentioning `upstream/`.

Page `#nextcloud-oncall` for P0. Open ticket in `#nextcloud-ops` for everything else.
