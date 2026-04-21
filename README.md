# Nextcloud AIO — Operator Runbook

This is the day-to-day playbook for the IT operator running our private Nextcloud fork. If you're here to figure out how to do X for customer Y, find X below, copy the example prompt into Claude Code, adjust the customer name, and run it.

**You don't need to know how to code.** Claude Code knows the repo and follows a guardrail file (`CLAUDE.md`) that stops it from doing anything dangerous without an explicit override. Your job is to describe what the customer needs; Claude's job is to translate it into safe edits.

**If Claude refuses a request**, the refusal message will tell you whether it is (a) out of scope and needs `OVERRIDE:`, (b) locked and needs engineering help, or (c) just unclear. Re-read §"If Claude refuses" near the end of this document before escalating.

---

## 0. Setup (one-time, per operator)

1. Install Claude Code per the internal IT guide.
2. Clone this repo: `git clone <repo-url> nextcloud-aio && cd nextcloud-aio`.
3. Install the pre-commit hook: `./scripts/install-hooks.sh`. This prevents accidental commits to protected paths.
4. Request your `mgmt-ctl` SSO token from engineering and save it per the instructions they give you.
5. Open the repo in Claude Code and say hello. Claude will read `CLAUDE.md` and greet you.

That's it. You won't run `git` or `docker` by hand — Claude does that. You will copy-paste `mgmt-ctl` commands Claude prints and run them in your terminal.

---

## 1. How to ask Claude for things

### 1.1 Good prompts

Good prompts are specific and name the customer. Examples:

- "For customer **acme-corp**, change the primary color to #1A4F8B and replace the logo with the new SVG I just put in `customization/customers/acme-corp/logo.svg`."
- "Add a Cloudflare Tunnel for customer **northwind**. The token is in my clipboard — where should I paste it?"
- "Onboard a new customer called **riverside-law** using the **law-firm** flavor. Domain is cloud.riverside-law.example.com."
- "Enable Exchange calendar/contacts sync for customer **foo-inc**. Their Exchange server is mail.foo.example.com with a self-signed cert; I have the CA here: `/tmp/foo-ca.pem`."
- "Pull the latest upstream Nextcloud AIO and open a PR."

### 1.2 What Claude will do in response

Claude will:

1. Confirm what task it thinks you're asking for.
2. If relevant, ask one clarifying question (e.g., "Customer or flavor scope?").
3. Propose a plan as a short numbered list, naming which files it will change.
4. Wait for you to say "go ahead" (or edit the plan).
5. Make the changes and run the pre-commit check.
6. Commit on a branch named something like `customer/<n>/<task>`.
7. Tell you what, if anything, you need to run next (usually a `mgmt-ctl` command).

If Claude jumps straight to editing without showing a plan, interrupt and ask for the plan. That's a Claude mistake, not a you mistake.

### 1.3 Bad prompts (and how to fix them)

- **Too vague**: "fix the colors." → Better: "For **acme-corp**, the primary blue is too dark; change it to #3E7AB8."
- **Missing customer**: "install the calendar integration." → Better: "Install the Exchange EWS calendar integration for **foo-inc**."
- **Asking for two things at once**: "Rebrand **acme** and **widget-co** at the same time." → Do them one at a time. Same branch is fine; separate commits make rollback easier.
- **Claude-like instructions**: "Write Python to parse the log." → You shouldn't need to. Ask for what you want: "Show me the last 100 lines of the Nextcloud container log for **acme-corp**, filtered for errors." Claude will produce the right `mgmt-ctl` command.

---

## 2. Tasks you can do freely (no override needed)

Each section below shows an example prompt. Copy, adapt, send.

### 2.1 Add a Cloudflare Tunnel

> For customer **<n>**, add a Cloudflare Tunnel using this token: I'll paste the encrypted token file shortly. The customer's domain is `<domain>`.

You'll then be asked to place the Cloudflare token in a secret file — Claude will tell you exactly where and how.

**What Claude does:** updates `customer.env`, writes a `cloudflared.yml`, adjusts the Compose overlay, reminds you to disable Rocket Loader and set any Collabora WOPI allowlists in Cloudflare's dashboard.

**After:** you run `mgmt-ctl apply --customer <n>` when the branch is merged.

### 2.2 Rebrand a customer

> For customer **<n>**, set the name to "**<Company> Cloud**", the primary color to **#XXYYZZ**, and use the logo at `customization/customers/<n>/logo.svg` (which I just copied in).

**Optional extras to include:** slogan, web URL, imprint URL, privacy URL, background image path.

**After:** `mgmt-ctl apply-branding --customer <n>` to push the change to a running instance without a full restart.

### 2.3 Tweak the CSS (just for this customer, or for a whole flavor)

> For **<n>**, add CSS that hides the breadcrumb bar on the Files page and makes folder names bold. Scope: just this customer.

or

> For the **law-firm** flavor, add CSS that sets the login page background to a soft grey and changes the heading font to Inter.

**Note:** if your change is for all customers on a flavor, say so — Claude defaults to per-customer scope if you don't.

### 2.4 Add some JavaScript

> Add JavaScript to the **default** flavor that shows a dismissible banner saying "Backup completed at 3:00 UTC" on login pages. Don't use a framework.

**What Claude will do:** edit `customization/apps/branding-default/js/main.js` and the app manifest.

**If your request sounds like it needs a framework** (React, Vue, a build step, a CDN-loaded library): Claude will push back. Those changes go through engineering.

### 2.5 Enable or disable a community container

> Enable the **local-ai** and **fail2ban** community containers for customer **<n>**.

**Allowed community containers** (from upstream): `caddy`, `fail2ban`, `local-ai`, `libretranslate`, `plex`, `pi-hole`, `vaultwarden`, `stalwart`, `borgbackup-viewer`, `container-management`, `facerecognition`, `memories`, `llama-cpp`, `lldap`.

**Our custom containers:** `litellm`, `ollama`, `customer-agent`.

Anything else → Claude will tell you it needs to be added by engineering first.

### 2.6 Install / remove a Nextcloud app

> Install the **polls** and **forms** apps for customer **<n>**.

> Uninstall the **recommendations** app for customer **<n>**.

Claude verifies the app is on the Nextcloud app store before doing anything. Non-store apps need `OVERRIDE:`.

### 2.7 SMB / Windows file share

> For customer **<n>**, mount their SMB share `\\fileserver01\company-shared` at `/Company Shared` in Nextcloud as an admin-wide external storage. The service account is `svc_nextcloud`; password is in my clipboard.

Claude will tell you where to put the password (an age-encrypted secret file), and will generate the `smb-mounts.yaml` that bootstrap reads.

**Gotchas** Claude will remind you about:
- SMBv1 is not supported — the customer needs ≥ SMBv2.
- The share host must be reachable from the Nextcloud container; if it's behind a firewall only the customer's LAN can see, tell Claude and it'll configure the route.
- Don't use SMB as the *primary* data directory unless the customer insists — performance is bad.

### 2.8 Microsoft Exchange (calendars & contacts)

> Enable Exchange EWS integration for customer **<n>**. Their Exchange server is **mail.<domain>.example.com**. They have a self-signed cert — here's the CA PEM: `/tmp/ca.pem`.

Each user will then connect their own Exchange account in Personal Settings. Claude will tell you how to guide them.

**For Exchange Mail** (as opposed to calendars/contacts): ask instead for "the Nextcloud Mail app" plus SMTP/IMAP settings — that's a different (simpler) path.

### 2.9 AI / LLM features

> Enable AI Assistant for customer **<n>** using **<provider>** with model **<model>**.

**Supported providers:**

- `localai` — runs in a container on the same host. Needs 8+GB free RAM; recommended only for customers with GPUs. Models: whatever LocalAI ships (Phi-3 Mini, Llama 3, etc.).
- `ollama` — same story as LocalAI, different runtime. Often easier to get working.
- `openai` — talks to OpenAI's API. You'll provide the API key (Claude will tell you where to put it). Model: `gpt-4o-mini`, `gpt-4o`, etc.
- `litellm` — middleman that lets us route to Anthropic Claude, Amazon Bedrock, Google Vertex, or any other provider. Slightly more setup; Claude will walk you through.

**For customers whose hosts are small** (< 16 GB RAM, no GPU), prefer `openai` or `litellm`-with-a-hosted-backend.

### 2.10 Raise upload limit / PHP memory / timeout

> For customer **<n>**, raise the upload limit to 32 GB and max execution time to 2 hours.

**Allowed values** Claude will set:

- `NEXTCLOUD_UPLOAD_LIMIT`: e.g., `32G`. Must end with `G`.
- `NEXTCLOUD_MAX_TIME`: seconds. `3600` is the default.
- `NEXTCLOUD_MEMORY_LIMIT`: e.g., `1024M`. Must end with `M`.

**Don't** ask Claude to change the data directory path (`NEXTCLOUD_DATADIR`) after the initial install. That's `OVERRIDE:` territory and usually a mistake.

### 2.11 Add extra Alpine packages or PHP extensions

> For customer **<n>**, add the `tesseract-ocr` package and the `tesseract-ocr-data-eng` language data for their OCR workflow.

**Allow-listed packages**: `imagemagick`, `ghostscript`, `libreoffice`, `poppler-utils`, `tesseract-ocr`, `tesseract-ocr-data-eng`.

**Allow-listed PHP extensions**: `imagick`, `redis`, `apcu`, `intl`.

Anything else → needs `OVERRIDE:` with a real reason.

### 2.12 Backups, restores, upgrades

These go through `mgmt-ctl`, not through file edits. Ask Claude:

> Trigger a backup for customer **<n>** now.

Claude prints the command: `mgmt-ctl backup <n>`. You run it.

> Upgrade customer **<n>** to image tag **staging-green**.

Claude prints: `mgmt-ctl upgrade <n> --to staging-green`. You run it.

**Always back up before upgrading.** The management server enforces this, but get in the habit of saying "back up then upgrade" as a single request so Claude does both.

### 2.13 Onboard a new customer

> Onboard a new customer **<n>** on the **<flavor>** flavor. Their domain is **<domain>**.

**What Claude does:** creates `customization/customers/<n>/` from the flavor template, sets the env file, generates a registration token, commits on a new branch, and tells you the next steps (create DNS, enroll in mgmt-ctl, merge the PR).

### 2.14 Pull upstream updates

> Pull the latest upstream Nextcloud AIO.

**What Claude does:** runs `scripts/merge-upstream.sh` only. If there are conflicts, it stops and pings engineering. If it succeeds, it opens a PR against `main` and the staging deploy kicks off automatically.

**Schedule:** this happens weekly on its own via the scheduled GitHub Action. You only need to trigger manually if a security advisory drops.

---

## 3. Tasks that need `OVERRIDE:` first

Prefix your message with `OVERRIDE: <one-sentence reason>`. Claude will still confirm the plan and walk you through — override just unlocks the possibility of doing the thing.

Examples of overridable tasks:

- Installing a Nextcloud app that's not on the official app store.
- Adding an Alpine package or PHP extension that's not on the allow-list.
- Disabling backups temporarily (e.g., during a maintenance window).
- Adding a community container that isn't on the allow-list.
- Running an `occ db:*` or `occ files:cleanup` command.
- Running a one-off shell command inside a customer container.
- Changing a Compose-file top-level setting.

**Example overridden prompt:**

```
OVERRIDE: We're onboarding a customer that has their own internal Nextcloud app at git.foo.example.com/internal-app — it's not on the public app store. The app is reviewed by their CISO.

Install the "internal-app" Nextcloud app for customer foo-corp from https://git.foo.example.com/internal-app.git, release v1.4.2.
```

Claude will still propose a plan, and the action will be logged in `.override-log.md`.

---

## 4. Tasks that are LOCKED (engineering-only)

Even with `OVERRIDE:`, these are refused. They require engineering — specifically, they require a second session-specific keyword that engineering provisions. If you think you need one of these, open a ticket in #nextcloud-ops.

- Editing anything in `upstream/` (the vendored upstream code).
- Changing the CI workflow's secrets, permissions, or deploy targets.
- Modifying security settings: SELinux, seccomp, docker socket mount, privileged flags.
- Rotating encryption keys or deploy keys.
- Changing `NEXTCLOUD_DATADIR` or `NEXTCLOUD_MOUNT` after a customer's initial deploy.
- Editing `CLAUDE.md` or `README.md`.

---

## 5. Common diagnostic requests

### 5.1 "A customer is down"

1. First message: **"Customer <n> is reporting their Nextcloud is unreachable. Give me a quick diagnostic."**
2. Claude will tell you to run: `mgmt-ctl status <n>`, `mgmt-ctl logs <n> --container nextcloud-aio-apache --tail 100`, etc.
3. If the last upgrade is suspicious: **"Roll back customer <n> to the previous image tag."** → `mgmt-ctl rollback <n>`.
4. If you can't restore quickly: escalate in #nextcloud-ops. Do NOT start editing files.

### 5.2 "Where is this configured?"

**"For customer <n>, where is the primary color set?"** → Claude looks at the relevant files and explains which one is active (customer override? flavor default? env default?).

### 5.3 "What's in this customer's instance right now?"

**"Show me the current branding, enabled apps, community containers, and feature flags for customer <n>."** → Claude runs `mgmt-ctl describe <n>` and summarizes.

### 5.4 "Compare two customers"

**"Diff the configs for <n-a> vs <n-b>."** → Claude runs `mgmt-ctl diff <n-a> <n-b>` and explains the meaningful differences.

---

## 6. If Claude refuses

Refusal messages come in three flavors:

### 6.1 "This requires an override"

The task is on the deny-list. If it's a real business need, retry with `OVERRIDE: <reason>` as the first line.

If you're not sure whether it's a real need — ask Claude first: **"Is <task> something I can do with OVERRIDE, or does it need engineering?"** Claude will tell you the category.

### 6.2 "This is locked"

Even override won't unlock it. Open a ticket in #nextcloud-ops. Engineering will either tell you (a) we don't do that, here's an alternative, or (b) here's a session keyword that unlocks it once.

### 6.3 "I need clarification"

Claude doesn't have enough info. Answer the question and resend.

---

## 7. Safety habits

- **One customer at a time.** Even if the same change applies to ten customers, do them as ten separate commits (on the same branch is fine). Makes rollback trivial.
- **Staging is safe; production is not.** The base image is automatically deployed to the staging server on every merge to `main`. If you're experimenting, test on staging first: **"Deploy this to staging and give me a URL to try."**
- **Backups first.** Before any upgrade, the management server requires a recent backup. Do not ask Claude to disable that check.
- **Secrets never in chat.** If a token needs to be added, Claude will tell you where to save it (age-encrypted file) rather than asking you to paste it into the conversation.
- **Commit messages are an audit trail.** Claude writes them in the right format; don't edit them unless you have a reason.
- **Read the diff.** Before you say "go ahead," skim the diff Claude shows you. Even if you can't judge the code, you can usually tell if the file paths and the number of lines changed are roughly what you expected.

---

## 8. Getting help

| Situation | Where to go |
|---|---|
| Claude refused something overridable and you're not sure if the reason is legitimate | #nextcloud-ops |
| Claude refused something locked | Ticket in #nextcloud-ops with the full refusal message |
| Upstream merge conflict | `scripts/merge-upstream.sh` output → engineering |
| Customer outage | #nextcloud-oncall (paging channel) |
| Management server is the problem | #platform-infra |
| You think the allow-list should include a new task | PR against `CLAUDE.md` (engineering reviews) |

---

## 9. What's in this repo

Minimal map for orientation:

```
.
├── CLAUDE.md               Claude's guardrails — don't edit.
├── README.md               You are here.
├── compose.yaml            Top-level Compose file. Imports upstream + overlays.
├── upstream/               Read-only copy of nextcloud/all-in-one.
├── customization/
│   ├── customers/<n>/      Per-customer config. 80% of your edits live here.
│   ├── flavors/<flavor>/   Per-flavor defaults. Shared across customers.
│   ├── community-containers/  Our custom container JSONs.
│   ├── apps/               Small Nextcloud apps we maintain (branding JS).
│   └── overlays/           Compose overrides that apply across customers.
├── scripts/                Automation. Mostly called via mgmt-ctl or Claude.
├── management-server/      The fleet mgmt server + agent.
├── .github/workflows/      CI. You don't edit these.
└── docs/                   Background. Start with RESEARCH_REPORT.md.
```

When in doubt, ask Claude: **"Where should I look to change X for customer Y?"**
