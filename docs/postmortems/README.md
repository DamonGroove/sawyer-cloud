# Postmortems

Every customer-facing incident gets a postmortem filed here, regardless
of root cause or severity. The goal is learning, not blame — reading a
year's worth of these should teach a new engineer what tends to go
wrong in this system and why.

`docs/INCIDENT_PLAYBOOK.md` is the forward-facing tool that we use
during an incident. This directory is the archive of what actually
happened after the fact.

---

## When to write one

- Every SEV-1 or SEV-2 (customer-visible outage, data loss risk, or
  security event) — mandatory, within 5 business days of resolution.
- SEV-3 (degradation, no user impact) — optional unless the root cause
  is interesting or affected >1 customer.
- Near-misses (incident caught before impact) — optional but
  encouraged; near-miss data is cheap learning.
- Repeat offenders — mandatory regardless of sev if the same root
  cause fired twice in a quarter.

## Filename convention

```
YYYY-MM-DD-<slug>.md
```

where `<slug>` is a short kebab-case phrase naming the proximate cause
or affected feature. Examples:

- `2026-04-21-cloudflare-tunnel-http3.md`
- `2026-05-03-clamav-scan-backlog.md`
- `2026-06-12-acme-corp-failed-restore.md`

One file per incident. If two things happened on the same day,
disambiguate via suffix (`-a`, `-b`).

## Template

Copy this skeleton for a new postmortem. Omit sections that don't
apply; add sections if the incident needs them.

```markdown
# <date>: <one-line title>

**Severity:** SEV-1 | SEV-2 | SEV-3 | near-miss
**Affected customers:** <slug>, <slug>, … or "fleet"
**Duration:** <start UTC> to <end UTC> (<minutes> min)
**Detected by:** <alert | customer report | engineering noticed>
**Authors:** @you, @co-author

## Summary

One paragraph. What broke, how, for how long.

## Timeline

Times in UTC. Include who did what.

- 12:03 — …
- 12:05 — …
- 12:17 — service restored.

## Root cause

Why did this happen? Be specific enough that a new engineer would
understand the mechanism without having been there.

## What went well

- …

## What went poorly

- …

## Where we got lucky

- …  (skip if this was a simple event)

## Action items

Each item has an owner and a due date. Track them in the team's issue
tracker, linked here.

- [ ] <action> — @owner, due <date>, ticket #<n>

## Supporting material

- logs: s3://sawyer-cloud-audit/incidents/<date>/...
- grafana: <permalink>
- chat transcript: <permalink>
```

## Writing style

- **First-person plural.** "We didn't notice…" beats "engineering
  didn't notice…"; "the operator ran…" beats "<name> ran…". Name
  individual work only when crediting, never when assigning blame.
- **Mechanisms over outcomes.** "Cloudflared 2025.4 dropped HTTP/3
  UDP, which broke Talk for customers using the tunnel" beats
  "Cloudflared was broken."
- **Include the boring bits.** The non-dramatic steps are often where
  the real lesson lives. The on-call person sat waiting for a 10-min
  dns-prop? Say so — maybe we should shorten that TTL.
- **No heroics framing.** A good postmortem reads like an autopsy,
  not a war story.

## Review cadence

- The author drafts and opens a PR within 3 business days of the
  incident closing.
- Engineering reviews as part of the weekly sync. Two engineers must
  approve before merge.
- Every 6 months we re-read the last 6 months of postmortems at a
  team retro and pull out patterns. The output of that retro gets
  written up at `docs/postmortems/retros/YYYY-H{1,2}-retro.md` (a
  sibling to this README).

---

## Patterns worth noting

*(This section will populate itself over time as incidents accumulate.
For Phase 4 handoff, the directory is empty.)*

## Examples in other repos

If you've never written one of these before and want a north star:

- <https://github.com/danluu/post-mortems> collects external examples.
- Google SRE's *Postmortem Culture* chapter is the canonical reference.

Neither of these is a template — they're orientation. Use the template
above and resist the urge to be clever with structure.
