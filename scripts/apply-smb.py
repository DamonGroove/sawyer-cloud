#!/usr/bin/env python3
"""
apply-smb.py — translate customer smb-mounts.yaml into idempotent
`occ files_external:*` calls.

Invoked by scripts/bootstrap.sh for CLAUDE.md §3.8. Kept out of
bootstrap.sh because the YAML parsing and diffing against the current
mount list is cleaner in Python.

YAML schema:

    mounts:
      - name: customer-fileshare
        share_host: fileserver.example.com
        share_path: /Shared
        mount_point_in_nc: /CustomerFiles
        auth_mechanism: password::sessioncredentials  # or password::password,
                                                       # kerberos
        scope: admin                                   # admin | user | group
        scope_target: (optional)                       # required for user|group
        options:                                       # optional
          encrypt: true

Credentials come from the process environment (bootstrap.sh decrypts the
customer's .age secret bundle before invoking us):

    SMB_<NAME>_USER
    SMB_<NAME>_PASS
    SMB_<NAME>_KEYTAB_PATH   (if auth_mechanism is kerberos)

<NAME> is the mount name uppercased with non-alphanumerics replaced by
underscores.

Idempotency: we list current mounts (`occ files_external:list
--output=json`) and only call create/update when a field differs. We never
call `files_external:delete` from here — removing a mount is an operator
decision made via `mgmt-ctl`, not a side effect of re-running bootstrap.

occ subcommands used:
    files_external:list       (read)
    files_external:create     (when mount is missing)
    files_external:option     (when an existing mount's options differ)
    files_external:update     (future-reserved)

Never called from here (per CLAUDE.md §4, §3.8 post-reconciliation):
    files_external:config     (not a real subcommand)
    files_external:delete     (operator-driven only)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from typing import Any, Dict, List, Optional

try:
    import yaml  # PyYAML, pinned in scripts/smoke-test/requirements.txt too
except ImportError:
    print("apply-smb: PyYAML is required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)


def env_key(name: str, suffix: str) -> str:
    norm = re.sub(r"[^A-Z0-9]", "_", name.upper())
    return f"SMB_{norm}_{suffix}"


def run_occ(occ_cmd: List[str], args: List[str], capture: bool = False) -> subprocess.CompletedProcess:
    full = [*occ_cmd, *args]
    return subprocess.run(
        full,
        check=False,
        capture_output=capture,
        text=True,
    )


def list_current_mounts(occ_cmd: List[str]) -> List[Dict[str, Any]]:
    res = run_occ(occ_cmd, ["files_external:list", "--output=json"], capture=True)
    if res.returncode != 0:
        print(
            f"apply-smb: files_external:list failed (rc={res.returncode}): "
            f"{res.stderr.strip()}",
            file=sys.stderr,
        )
        return []
    try:
        return json.loads(res.stdout or "[]")
    except json.JSONDecodeError as e:
        print(f"apply-smb: could not parse files_external:list output: {e}", file=sys.stderr)
        return []


def find_mount_by_mountpoint(current: List[Dict[str, Any]], mp: str) -> Optional[Dict[str, Any]]:
    # occ output normalizes mount_point to a leading-slash string.
    target = "/" + mp.lstrip("/")
    for m in current:
        if m.get("mount_point") == target:
            return m
    return None


def apply_one_mount(occ_cmd: List[str], mount: Dict[str, Any], current: List[Dict[str, Any]]) -> None:
    name = mount["name"]
    share_host = mount["share_host"]
    share_path = mount["share_path"]
    mp = mount["mount_point_in_nc"]
    auth = mount.get("auth_mechanism", "password::password")
    scope = mount.get("scope", "admin")
    scope_target = mount.get("scope_target")
    options: Dict[str, Any] = mount.get("options") or {}

    user = os.environ.get(env_key(name, "USER"))
    pw = os.environ.get(env_key(name, "PASS"))
    keytab = os.environ.get(env_key(name, "KEYTAB_PATH"))

    existing = find_mount_by_mountpoint(current, mp)
    if existing is None:
        print(f"apply-smb: creating mount at {mp} (host={share_host}, share={share_path})")
        create_args = [
            "files_external:create",
            mp,
            "smb",
            auth,
            "--config", f"host={share_host}",
            "--config", f"share={share_path}",
        ]
        if user:
            create_args += ["--config", f"user={user}"]
        if pw:
            create_args += ["--config", f"password={pw}"]
        if keytab:
            create_args += ["--config", f"keytab={keytab}"]
        if scope == "user" and scope_target:
            create_args += ["--user", scope_target]
        elif scope == "group" and scope_target:
            create_args += ["--group", scope_target]
        res = run_occ(occ_cmd, create_args, capture=True)
        if res.returncode != 0:
            print(f"apply-smb: create failed for {mp}: {res.stderr.strip()}", file=sys.stderr)
            return
        # re-list so option updates below see the new ID
        current[:] = list_current_mounts(occ_cmd)
        existing = find_mount_by_mountpoint(current, mp)

    if existing is None:
        # Create reported non-zero but we continue; nothing more to do.
        return

    # Option-level diff.
    mount_id = existing.get("mount_id") or existing.get("id")
    if mount_id is None:
        print(f"apply-smb: no id for existing mount at {mp}; skipping option diff", file=sys.stderr)
        return

    cur_options = existing.get("options") or {}
    for k, v in options.items():
        # occ stores option values as strings; normalize for comparison.
        cur = cur_options.get(k)
        if str(cur) != str(v):
            print(f"apply-smb: setting option {k}={v} on mount id={mount_id}")
            res = run_occ(
                occ_cmd, ["files_external:option", str(mount_id), k, str(v)], capture=True
            )
            if res.returncode != 0:
                print(f"apply-smb: option set failed: {res.stderr.strip()}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply smb-mounts.yaml via occ files_external:*.")
    parser.add_argument("--yaml", required=True, help="path to smb-mounts.yaml")
    parser.add_argument(
        "--occ-runner",
        default="occ",
        help="shell command prefix that invokes occ (e.g. 'occ' inside the "
             "NC container, or 'docker exec --user www-data nextcloud-aio-nextcloud "
             "php /var/www/html/occ' from the host). Parsed via shlex.",
    )
    args = parser.parse_args()

    occ_cmd = shlex.split(args.occ_runner)
    if not occ_cmd:
        print("apply-smb: --occ-runner cannot be empty", file=sys.stderr)
        return 2

    with open(args.yaml, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}

    mounts = doc.get("mounts") or []
    if not isinstance(mounts, list):
        print("apply-smb: top-level `mounts:` must be a list", file=sys.stderr)
        return 2

    required = {"name", "share_host", "share_path", "mount_point_in_nc"}
    for i, m in enumerate(mounts):
        missing = required - set(m or {})
        if missing:
            print(
                f"apply-smb: mount[{i}] missing required keys: {sorted(missing)}",
                file=sys.stderr,
            )
            return 2

    current = list_current_mounts(occ_cmd)
    for m in mounts:
        apply_one_mount(occ_cmd, m, current)

    return 0


if __name__ == "__main__":
    sys.exit(main())
