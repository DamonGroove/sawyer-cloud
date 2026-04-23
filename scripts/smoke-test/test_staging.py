#!/usr/bin/env python3
"""
scripts/smoke-test/test_staging.py

Runs on the staging host after scripts/deploy-staging.sh brings the
stack up. Verifies the minimum set of things that must work before we
promote the image tag to `:staging-green` and offer it to customers.

Designed to be fast (<30s) and self-contained: hits the staging NC
through HTTP, runs a handful of occ commands via `docker exec`, and
exits non-zero on the first failure.

Exit codes (align with mgmt-ctl's):
    0  all smoke tests pass.
    4  a test failed (agent-side failure in mgmt-ctl parlance).
    5  setup failure (could not reach the host at all).

Usage:
    scripts/smoke-test/test_staging.py --host staging.sawyer-cloud.internal \
        --customer staging-customer

See docs/STAGING_SETUP.md for the staging host setup these tests assume.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from typing import List, Tuple
from urllib.parse import urljoin

try:
    import requests
except ImportError:
    print("smoke-test: `requests` is required (see requirements.txt)", file=sys.stderr)
    sys.exit(5)


# ---------------------------------------------------------------------------

RC_PASS = 0
RC_TEST_FAIL = 4
RC_SETUP_FAIL = 5


def run_docker_occ(args: List[str]) -> Tuple[int, str, str]:
    full = [
        "docker", "exec", "--user", "www-data",
        "nextcloud-aio-nextcloud", "php", "/var/www/html/occ", *args,
    ]
    r = subprocess.run(full, capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout, r.stderr


def t_http_reachable(host: str, scheme: str = "https") -> None:
    url = f"{scheme}://{host}/status.php"
    r = requests.get(url, timeout=10, verify=False)
    r.raise_for_status()
    body = r.json()
    assert body.get("installed") is True, f"status.php says not installed: {body}"
    assert body.get("maintenance") is False, f"NC is in maintenance mode: {body}"


def t_login_page_renders(host: str, scheme: str = "https") -> None:
    url = f"{scheme}://{host}/login"
    r = requests.get(url, timeout=10, verify=False, allow_redirects=True)
    r.raise_for_status()
    # Be tolerant about the exact html; just check a well-known token exists.
    assert "Nextcloud" in r.text or "login" in r.text.lower(), \
        "login page does not look like a Nextcloud login"


def t_occ_status(customer: str) -> None:
    rc, out, err = run_docker_occ(["status", "--output=json"])
    assert rc == 0, f"occ status failed rc={rc}, stderr={err}"
    data = json.loads(out)
    assert data.get("installed") is True, f"occ status says not installed: {data}"
    # Version sanity
    assert data.get("versionstring"), f"no versionstring in occ status: {data}"


def t_occ_app_list_includes_core(customer: str) -> None:
    rc, out, err = run_docker_occ(["app:list", "--output=json"])
    assert rc == 0, f"occ app:list failed rc={rc}, stderr={err}"
    data = json.loads(out)
    enabled = set(data.get("enabled", {}))
    # Core apps that must always be enabled.
    for must_have in ("files", "activity", "settings"):
        assert must_have in enabled, f"core app missing from enabled: {must_have}"


def t_branding_app_enabled(customer: str) -> None:
    rc, out, err = run_docker_occ(["app:list", "--output=json"])
    assert rc == 0
    data = json.loads(out)
    enabled = set(data.get("enabled", {}))
    assert "branding_default" in enabled, \
        "branding_default app not enabled; bootstrap-aio apply step did not run"


def t_theming_customcss_applied(customer: str) -> None:
    rc, out, err = run_docker_occ([
        "config:app:get", "theming_customcss", "customcss",
    ])
    assert rc == 0, f"config:app:get failed rc={rc}, stderr={err}"
    # Any non-empty content counts — we don't want to tie this test to
    # the exact CSS so it survives theme tweaks.
    assert out.strip(), "theming_customcss.customcss is empty"


# ---------------------------------------------------------------------------

TESTS = [
    ("http_reachable", t_http_reachable),
    ("login_page_renders", t_login_page_renders),
    ("occ_status", t_occ_status),
    ("occ_app_list_includes_core", t_occ_app_list_includes_core),
    ("branding_app_enabled", t_branding_app_enabled),
    ("theming_customcss_applied", t_theming_customcss_applied),
]


def main() -> int:
    p = argparse.ArgumentParser(description="Staging smoke tests.")
    p.add_argument("--host", required=True, help="staging hostname or IP")
    p.add_argument("--customer", default="staging-customer")
    p.add_argument("--scheme", default="https", choices=["http", "https"])
    p.add_argument("--wait", type=int, default=30,
                   help="seconds to wait for NC to be ready before starting")
    args = p.parse_args()

    print(f"smoke-test: host={args.host} customer={args.customer}")

    # Give NC a moment in case the caller just started it.
    for _ in range(args.wait):
        try:
            r = requests.get(
                f"{args.scheme}://{args.host}/status.php", timeout=2, verify=False
            )
            if r.ok:
                break
        except requests.RequestException:
            pass
        time.sleep(1)
    else:
        print(f"smoke-test: host {args.host} never became reachable within {args.wait}s",
              file=sys.stderr)
        return RC_SETUP_FAIL

    failed: List[str] = []
    for name, fn in TESTS:
        try:
            if fn.__code__.co_argcount == 1:
                fn(args.customer)
            else:
                fn(args.host, args.scheme)
            print(f"  PASS  {name}")
        except (AssertionError, requests.RequestException, subprocess.SubprocessError,
                subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            print(f"  FAIL  {name}: {e}")
            failed.append(name)

    if failed:
        print(f"\nsmoke-test: {len(failed)} failure(s): {', '.join(failed)}", file=sys.stderr)
        return RC_TEST_FAIL
    print("\nsmoke-test: all green")
    return RC_PASS


if __name__ == "__main__":
    sys.exit(main())
