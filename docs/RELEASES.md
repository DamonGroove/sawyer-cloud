# Releases — how to ship artifacts

Operator-facing notes on the release flows sawyer-cloud currently has.
Short; the implementation detail lives in the linked workflows.

---

## VM artifacts (qcow2 / vmdk) via GitHub Release

For customers whose deploy target is a VM (Proxmox, VMware, bare metal
via hypervisor). The Docker path is separate — see §"Docker base image"
below.

### One-command release

```bash
scripts/release-vm.sh <tag>
```

Example: `scripts/release-vm.sh v0.1.1`.

What happens:

1. The script validates the working tree is clean and the tag is
   shaped right (`v<major>.<minor>.<patch>[-qual]-vm`; the `-vm`
   suffix is auto-appended if you leave it off).
2. It creates an annotated tag at `HEAD` and pushes it to `origin`.
3. Pushing the tag triggers
   [`.github/workflows/release-vm.yml`](../.github/workflows/release-vm.yml),
   which installs qemu + Packer (via
   [`scripts/install-packer.sh`](../scripts/install-packer.sh)), runs
   `packer build scripts/packer/aio-base.pkr.hcl`, and uploads the
   artifacts as assets on the GitHub Release for the tag.
4. ~30 minutes later the Release page has `*.qcow2` and `*.vmdk`
   files ready for customer download.

The script prints the exact Release URL and the Actions-tab URL so you
can watch progress.

### When to cut a VM release

- When `base-image-build.yml` has published a new `:latest` aio-base
  image that you want customers on VM infrastructure to receive.
- After a security fix that affects the host layer, not just the
  mastercontainer.
- **Not** on every push to `main`. VM builds are slow (~30 min) and the
  artifacts are GB-scale; customer hypervisors don't benefit from
  churn the way Docker hosts do.

### Picking a tag

Follow the convention `v<base-image-tag>-vm`. If the base image you
want to bake is `sha-7f8c1a2b`, tag the VM release
`v2026.04.21-sha-7f8c1a2b-vm` (date-stamped so sort order reflects
release recency). For a stable cut, `v0.2.0-vm` and so on.

### If the workflow fails

- Check the Actions tab; the most common failure is a packer-install
  checksum mismatch (HashiCorp rotated signing keys) or the runner
  running out of disk. Both are re-runnable without code changes.
- If the Packer template itself fails on a new upstream base image,
  the failure surfaces as `packer validate` reporting a schema
  mismatch. See [docs/MERGE_PROCEDURE.md §4.3](MERGE_PROCEDURE.md#43-json-validation-failed-or-docker-compose-config-failed)
  for the pattern — fix happens in `scripts/packer/aio-base.pkr.hcl`,
  not in the workflow.

## Docker base image via ghcr.io

No operator action required per release —
[`.github/workflows/base-image-build.yml`](../.github/workflows/base-image-build.yml)
publishes `ghcr.io/sawyer-cloud/aio-base:<short-sha>` on every push to
`main` that touches files baked into the image (Dockerfile.base, the
bootstrap scripts, `customization/community-containers/**`, etc). The
`:latest` tag moves along with it on main.

Customers on Docker pull by tag via their customer-env `AIO_IMAGE_TAG`;
operators manage promotions with `mgmt-ctl images promote <tag> --to
staging-green|production` (once that route graduates from its Phase 2
501 stub).

## Scaffold + feature releases

Source-code tags without artifacts — used to mark significant repo
states (e.g., `v0.1.0-scaffold` for the end-of-bootstrap commit). Pushed
by engineering, never by operators.

---

Audit note: this doc + `scripts/release-vm.sh` landed via
`OVERRIDE:` per CLAUDE.md §1.1; see `.override-log.md`.
