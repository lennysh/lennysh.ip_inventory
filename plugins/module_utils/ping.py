# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Concurrent ICMP reachability checks using the system ``ping`` binary."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import platform
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.records import INFRA_RECORD_TYPES, copy_record


def ping_once(ip, timeout_seconds=1.0, ping_command="ping"):
    if platform.system().lower() == "windows":
        cmd = [ping_command, "-n", "1", "-w", str(int(timeout_seconds * 1000)), ip]
    else:
        cmd = [ping_command, "-c", "1", "-W", str(max(1, int(timeout_seconds))), ip]
    return subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0


def ping_many(ips, timeout_seconds=1.0, concurrency=50, ping_command="ping"):
    """Return ``{ip: bool}`` for every unique IP in ``ips``."""
    unique_ips = sorted(set(ip for ip in ips if ip))
    results = {}
    if not unique_ips:
        return results
    with ThreadPoolExecutor(max_workers=max(1, int(concurrency))) as executor:
        futures = dict((executor.submit(ping_once, ip, timeout_seconds, ping_command), ip) for ip in unique_ips)
        for future in as_completed(futures):
            ip = futures[future]
            try:
                results[ip] = bool(future.result())
            except Exception:
                results[ip] = False
    return results


def pingable_ips(records):
    return sorted(set(r["ip"] for r in records if r.get("ip") and r.get("record_type") not in INFRA_RECORD_TYPES))


def apply_ping_results(records, results):
    """Set ``ping_status`` on each record from a ``{ip: bool}`` (or ``{ip: 'up'|'down'}``) mapping."""
    updated = []
    for record in records:
        if not record.get("ip") or record.get("record_type") in INFRA_RECORD_TYPES:
            updated.append(copy_record(record, ping_status="skipped"))
            continue
        value = results.get(record["ip"])
        if isinstance(value, bool):
            status = "up" if value else "down"
        else:
            status = value if value in ("up", "down") else "down"
        updated.append(copy_record(record, ping_status=status))
    return updated
