# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
"""End-to-end pipeline (collect -> filter -> reconcile -> ping -> sweep -> issues).

The roles run these same steps individually as Ansible tasks; the inventory
plugin (which cannot run tasks) calls ``run_pipeline`` directly.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible.module_utils.common.arg_spec import ArgumentSpecValidator

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.collectors import get_collector
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.discover import (
    discovered_records,
    known_ips,
    sweep_candidates,
)
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.filters import RecordFilter
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.issues import analyze_issues
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.merge import reconcile, sort_records
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.ping import apply_ping_results, ping_many, pingable_ips
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.subnets import enrich_subnets

# Keys allowed in a source config block that are not collector options.
PIPELINE_SOURCE_KEYS = ("enabled", "filters")

PING_DEFAULTS = {
    "enabled": False,
    "timeout_seconds": 1.0,
    "concurrency": 50,
    "discover_unknown": False,
    "discover_private_only": True,
    "discover_max_hosts_per_subnet": 512,
}


class PipelineError(Exception):
    pass


def validate_source_params(name, params):
    """Validate/default a source's options using the collector's argument_spec."""
    cls = get_collector(name)
    clean = dict((k, v) for k, v in (params or {}).items() if k not in PIPELINE_SOURCE_KEYS)
    result = ArgumentSpecValidator(cls.argument_spec).validate(clean)
    if result.error_messages:
        raise PipelineError("Invalid options for source '%s': %s" % (name, "; ".join(result.error_messages)))
    return result.validated_parameters


def enabled_sources(sources_cfg, only=None):
    names = []
    for name, cfg in (sources_cfg or {}).items():
        cfg = cfg or {}
        if not cfg.get("enabled", True):
            continue
        if only and name not in only:
            continue
        names.append(name)
    return names


def collect_sources(sources_cfg, global_filters=None, only=None, client_factory=None, ignore_errors=False):
    """Collect from every enabled source and apply include/exclude rules.

    Returns ``(records, stats, warnings)``; stats is ``{source: {collected, kept, failed}}``.
    With ``ignore_errors`` a failing source is recorded in stats/warnings instead of raising.
    """
    source_filters = dict((name, (cfg or {}).get("filters")) for name, cfg in (sources_cfg or {}).items())
    record_filter = RecordFilter(global_filters, source_filters)
    records, stats, warnings = [], {}, []
    for name in enabled_sources(sources_cfg, only):
        try:
            params = validate_source_params(name, sources_cfg[name])
            collector = get_collector(name)(params, client_factory=client_factory)
            found = collector.collect()
        except Exception as exc:
            message = "%s collection failed: %s" % (name, exc)
            if not ignore_errors:
                raise PipelineError(message)
            stats[name] = {"collected": 0, "kept": 0, "failed": True, "msg": str(exc)}
            warnings.append(message)
            continue
        kept = record_filter.filter_records(found)
        stats[name] = {"collected": len(found), "kept": len(kept), "failed": False}
        warnings.extend(collector.warnings)
        records.extend(kept)
    return records, stats, warnings


def run_pipeline(config, client_factory=None, ping_func=None):
    """Run every step.  ``config`` mirrors the inventory plugin options.

    Returns ``{hosts, subnets, orphan_vlans, findings, stats, warnings}``.
    """
    ping_cfg = dict(PING_DEFAULTS)
    ping_cfg.update(dict((k, v) for k, v in (config.get("ping") or {}).items() if v is not None))
    ping_func = ping_func or ping_many

    records, stats, warnings = collect_sources(
        config.get("sources"),
        config.get("filters"),
        only=config.get("only_sources"),
        client_factory=client_factory,
        ignore_errors=config.get("ignore_source_errors", False),
    )

    if config.get("raw"):
        hosts = records
        subnets = enrich_subnets([r for r in records if r.get("record_type") == "subnet"])
        orphan_vlans = []
    else:
        merged = reconcile(records)
        hosts, subnets, orphan_vlans = merged["hosts"], merged["subnets"], merged["orphan_vlans"]

    ping_kwargs = {"timeout_seconds": float(ping_cfg["timeout_seconds"]), "concurrency": int(ping_cfg["concurrency"])}
    if ping_cfg["enabled"]:
        hosts = apply_ping_results(hosts, ping_func(pingable_ips(hosts), **ping_kwargs))

    if ping_cfg["discover_unknown"] and not config.get("raw"):
        candidates = sweep_candidates(
            subnets,
            known_ips(hosts),
            max_hosts_per_subnet=int(ping_cfg["discover_max_hosts_per_subnet"]),
            private_only=bool(ping_cfg["discover_private_only"]),
        )
        results = ping_func([c["ip"] for c in candidates], **ping_kwargs) if candidates else {}
        hosts = sort_records(hosts + discovered_records(candidates, results, subnets))

    findings = []
    issues_cfg = config.get("issues") or {}
    if issues_cfg.get("enabled", True) and not config.get("raw"):
        findings = analyze_issues(
            hosts,
            subnets,
            checks=issues_cfg.get("checks"),
            skip_checks=issues_cfg.get("skip_checks"),
            cname_alias_threshold=issues_cfg.get("cname_alias_threshold", 10),
        )

    return {
        "hosts": hosts,
        "subnets": subnets,
        "orphan_vlans": orphan_vlans,
        "findings": findings,
        "stats": stats,
        "warnings": warnings,
    }
