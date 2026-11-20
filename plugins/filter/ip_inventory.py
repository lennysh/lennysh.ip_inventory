# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Jinja2 filters exposing the IP inventory processing steps to playbooks and roles.

Every filter is documented in its own sidecar YAML file next to this module.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import csv
import io

from ansible.errors import AnsibleFilterError

from ansible_collections.lennysh.ip_inventory.plugins.module_utils import discover as _discover
from ansible_collections.lennysh.ip_inventory.plugins.module_utils import issues as _issues
from ansible_collections.lennysh.ip_inventory.plugins.module_utils import merge as _merge
from ansible_collections.lennysh.ip_inventory.plugins.module_utils import ping as _ping
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.filters import RecordFilter
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.records import meta, normalize_record
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.subnets import enrich_subnets as _enrich_subnets


def _records(value, name):
    if value is None:
        return []
    if isinstance(value, (dict, str)):
        raise AnsibleFilterError("%s expects a list of records, got %s" % (name, type(value).__name__))
    return [normalize_record(item) for item in value]


def filter_records(records, filters=None, source_filters=None):
    """Apply global (and per-source) include/exclude rules."""
    return RecordFilter(filters, source_filters).filter_records(_records(records, "filter_records"))


def reconcile(records):
    """Merge observations into one row per IP: ``{hosts, subnets, orphan_vlans}``."""
    return _merge.reconcile(_records(records, "reconcile"))


def sort_records(records):
    return _merge.sort_records(_records(records, "sort_records"))


def enrich_subnets(records):
    return _enrich_subnets([r for r in _records(records, "enrich_subnets") if r.get("record_type") == "subnet"])


def pingable_ips(records):
    return _ping.pingable_ips(_records(records, "pingable_ips"))


def apply_ping(records, results):
    """Set ``ping_status`` from an ``icmp_ping`` ``reachable`` mapping."""
    return _ping.apply_ping_results(_records(records, "apply_ping"), dict(results or {}))


def sweep_candidates(subnets, hosts, max_hosts_per_subnet=512, private_only=True, filters=None, source_filters=None):
    """Unused addresses in ``subnets`` that are not already in ``hosts``."""
    record_filter = RecordFilter(filters, source_filters) if (filters or source_filters) else None
    return _discover.sweep_candidates(
        _records(subnets, "sweep_candidates"),
        _discover.known_ips(_records(hosts, "sweep_candidates")),
        max_hosts_per_subnet=max_hosts_per_subnet,
        private_only=private_only,
        record_filter=record_filter,
    )


def discovered(candidates, results, subnets):
    """Responding sweep candidates as ``discovered`` records."""
    return _discover.discovered_records(_records(candidates, "discovered"), dict(results or {}), _records(subnets, "discovered"))


def analyze_issues(hosts, subnets=None, checks=None, skip_checks=None, cname_alias_threshold=10):
    try:
        return _issues.analyze_issues(
            _records(hosts, "analyze_issues"),
            _records(subnets, "analyze_issues"),
            checks=checks,
            skip_checks=skip_checks,
            cname_alias_threshold=cname_alias_threshold,
        )
    except ValueError as exc:
        raise AnsibleFilterError(str(exc))


def issue_summary(findings):
    return _issues.summarize_findings(_records(findings, "issue_summary"))


def issues_by_ip(findings):
    return _issues.findings_by_ip(_records(findings, "issues_by_ip"))


def dns_summary(hosts, limit=10):
    """Counts and samples used to spot stale DNS records."""
    hosts = _records(hosts, "dns_summary")
    with_aliases = [h for h in hosts if meta(h).get("cname_aliases")]
    multi_dns = [h for h in hosts if len(meta(h).get("dns_names") or []) > 1]
    dns_only = [h for h in hosts if meta(h).get("dns_only")]
    dns_down = [h for h in hosts if meta(h).get("dns_names") and h.get("ping_status") == "down"]

    def sample(items):
        return [{"ip": h["ip"], "names": meta(h).get("dns_names") or [h.get("hostname") or ""]} for h in items[:limit]]

    return {
        "with_cname_aliases": len(with_aliases),
        "multiple_dns_names": len(multi_dns),
        "dns_only": len(dns_only),
        "dns_ping_down": len(dns_down),
        "dns_only_sample": sample(dns_only),
        "dns_ping_down_sample": sample([h for h in dns_down if not meta(h).get("dns_only")]),
    }


def csv_row(values, delimiter=","):
    """Render one CSV line with every field quoted (QUOTE_ALL), no trailing newline."""
    buf = io.StringIO()
    csv.writer(buf, quoting=csv.QUOTE_ALL, delimiter=delimiter, lineterminator="").writerow(
        ["" if v is None else v for v in values]
    )
    return buf.getvalue()


class FilterModule(object):
    def filters(self):
        return {
            "filter_records": filter_records,
            "reconcile": reconcile,
            "sort_records": sort_records,
            "enrich_subnets": enrich_subnets,
            "pingable_ips": pingable_ips,
            "apply_ping": apply_ping,
            "sweep_candidates": sweep_candidates,
            "discovered": discovered,
            "analyze_issues": analyze_issues,
            "issue_summary": issue_summary,
            "issues_by_ip": issues_by_ip,
            "dns_summary": dns_summary,
            "csv_row": csv_row,
        }
