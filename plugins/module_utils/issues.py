# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Anomaly checks on the reconciled inventory.

Each check is a function ``(hosts, context) -> [finding, ...]`` registered in
``CHECKS``.  To add a new check, write the function and add it to ``CHECKS``
(and describe the category in ``CATEGORY_DESCRIPTIONS`` so reports explain it).

A finding is a dict::

    severity   high | medium | low | info
    category   short slug, e.g. mac_conflict
    summary    one line
    detail     longer explanation
    ips / macs / hostnames   lists
    evidence   free text
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from collections import defaultdict

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.records import (
    ACTIVE_RECORD_TYPES,
    LIVE_RECORD_TYPES,
    all_hostnames,
    all_macs,
    all_record_types,
    all_sources,
    meta,
)
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.subnets import parse_ipv4_network

SEVERITIES = ("high", "medium", "low", "info")
SEVERITY_ORDER = dict((name, index) for index, name in enumerate(SEVERITIES))

CATEGORY_DESCRIPTIONS = {
    "mac_shared": "Same MAC seen on multiple IPs",
    "mac_conflict": "Same IP associated with multiple MACs",
    "hostname_shared": "Same hostname maps to multiple IPs",
    "dns_only": "DNS/PTR present but no DHCP/ARP/UniFi/Proxmox observation",
    "dns_unreachable": "DNS name exists but ICMP is down",
    "active_unreachable": "Seen live recently (ARP/UniFi/VM) but ICMP is down",
    "missing_mac": "Live/DHCP observation without a MAC",
    "discovered": "Responded to ping sweep but missing from DHCP/DNS/ARP/etc.",
    "cname_aliases": "Many CNAME aliases pointing at one host (informational)",
}


def finding(severity, category, summary, detail="", ips=None, macs=None, hostnames=None, evidence=""):
    return {
        "severity": severity,
        "category": category,
        "summary": summary,
        "detail": detail,
        "ips": list(ips or []),
        "macs": list(macs or []),
        "hostnames": list(hostnames or []),
        "evidence": evidence or "",
    }


def _label(record):
    return record.get("hostname") or record.get("ip")


def gateway_ips(subnets):
    gateways = set()
    for subnet in subnets or []:
        if subnet.get("ip"):
            gateways.add(subnet["ip"])
        network = parse_ipv4_network(meta(subnet).get("cidr"))
        if network is not None and network.num_addresses > 2:
            gateways.add(str(network.network_address + 1))
    return gateways


def check_mac_shared(hosts, ctx):
    by_mac = defaultdict(list)
    for record in hosts:
        for mac in all_macs(record):
            by_mac[mac].append(record)

    findings = []
    for mac, group in sorted(by_mac.items()):
        ips = sorted(set(r["ip"] for r in group))
        if len(ips) < 2:
            continue
        hostnames = sorted(set(name for r in group for name in all_hostnames(r)))
        gateway_hits = [ip for ip in ips if ip in ctx["gateway_ips"]]
        if len(gateway_hits) >= 3 and len(gateway_hits) == len(ips):
            findings.append(finding(
                "info", "mac_shared",
                "Router/gateway MAC %s appears on %d subnet gateways" % (mac, len(ips)),
                "Expected for a multi-homed firewall/router. Listed for completeness.",
                ips=ips, macs=[mac], hostnames=hostnames[:8], evidence="all IPs are subnet gateways",
            ))
            continue
        findings.append(finding(
            "high" if len(ips) <= 6 else "medium", "mac_shared",
            "MAC %s used by %d IPs" % (mac, len(ips)),
            "One hardware address claiming multiple IPs can mean dual-homed NICs, MAC reuse, or stale ARP/DHCP.",
            ips=ips, macs=[mac], hostnames=hostnames[:12],
            evidence="; ".join("%s (%s)" % (r["ip"], ",".join(all_sources(r))) for r in group[:8]),
        ))
    return findings


def check_mac_conflict(hosts, ctx):
    findings = []
    for record in hosts:
        macs = all_macs(record)
        if len(macs) < 2:
            continue
        findings.append(finding(
            "high", "mac_conflict",
            "%s (%s) has %d MACs" % (_label(record), record["ip"], len(macs)),
            "Sources disagree on the MAC for this IP — possible IP conflict or dual NICs merged onto one address.",
            ips=[record["ip"]], macs=macs, hostnames=all_hostnames(record)[:8], evidence=", ".join(all_sources(record)),
        ))
    return findings


def check_hostname_shared(hosts, ctx):
    by_name = defaultdict(list)
    display = {}
    for record in hosts:
        for name in all_hostnames(record):
            key = name.lower().rstrip(".")
            by_name[key].append(record)
            display.setdefault(key, name)

    findings = []
    for key, group in sorted(by_name.items()):
        unique = {}
        for record in group:
            unique.setdefault(record["ip"], record)
        ips = sorted(unique)
        if len(ips) < 2:
            continue
        name = display[key]
        octets = [ip.split(".")[-1] for ip in ips]
        same_host_octet = len(set(octets)) == 1 and len(ips) >= 3
        mostly_gateways = sum(1 for ip in ips if ip in ctx["gateway_ips"]) >= max(3, len(ips) - 1)
        if same_host_octet or mostly_gateways:
            findings.append(finding(
                "info", "hostname_shared",
                "%s resolves/appears on %d IPs (likely multi-homed)" % (name, len(ips)),
                "Same last octet or gateway role across many subnets — typical for DNS/DHCP helpers or routers.",
                ips=ips, hostnames=[name], evidence="shared host octet" if same_host_octet else "gateway IPs",
            ))
            continue
        findings.append(finding(
            "medium", "hostname_shared",
            "%s appears on %d IPs" % (name, len(ips)),
            "Duplicate hostnames can be stale DNS/DHCP reservations, renumbered devices, "
            "or intentional aliases that should be cleaned up.",
            ips=ips, hostnames=[name],
            evidence="; ".join("%s [%s]" % (ip, ",".join(all_record_types(unique[ip]))) for ip in ips[:8]),
        ))
    return findings


def check_dns_only(hosts, ctx):
    findings = []
    for record in hosts:
        if not meta(record).get("dns_only"):
            continue
        names = meta(record).get("dns_names") or all_hostnames(record)
        findings.append(finding(
            "medium", "dns_only",
            "DNS-only: %s (%s)" % (_label(record), record["ip"]),
            "Present in DNS zones/PTRs but not seen in DHCP, ARP, UniFi, or Proxmox — candidate for stale DNS cleanup.",
            ips=[record["ip"]], hostnames=names[:12], evidence=", ".join(all_record_types(record)),
        ))
    return findings


def check_dns_unreachable(hosts, ctx):
    findings = []
    for record in hosts:
        dns_names = meta(record).get("dns_names") or []
        if not dns_names or record.get("ping_status") != "down" or meta(record).get("dns_only"):
            continue
        findings.append(finding(
            "low", "dns_unreachable",
            "DNS present but ping down: %s (%s)" % (_label(record), record["ip"]),
            "Has DNS names and other inventory sources, but no ICMP reply. May be firewalled, asleep, or stale.",
            ips=[record["ip"]], hostnames=dns_names[:12], macs=all_macs(record),
            evidence="sources=%s; types=%s" % (",".join(all_sources(record)), ",".join(sorted(all_record_types(record)))),
        ))
    return findings


def check_active_unreachable(hosts, ctx):
    findings = []
    for record in hosts:
        if record.get("ping_status") != "down":
            continue
        active = sorted(set(all_record_types(record)) & ACTIVE_RECORD_TYPES)
        if not active:
            continue
        findings.append(finding(
            "low", "active_unreachable",
            "Seen live but ping down: %s (%s)" % (_label(record), record["ip"]),
            "ARP/UniFi/VM evidence exists, but ICMP failed. Common for phones, IoT, or hosts that block ping.",
            ips=[record["ip"]], hostnames=all_hostnames(record)[:8], macs=all_macs(record), evidence=", ".join(active),
        ))
    return findings


def check_missing_mac(hosts, ctx):
    findings = []
    for record in hosts:
        if all_macs(record):
            continue
        types = set(all_record_types(record))
        if not types & LIVE_RECORD_TYPES:
            continue
        findings.append(finding(
            "low", "missing_mac",
            "No MAC for live host %s (%s)" % (_label(record), record["ip"]),
            "DHCP/ARP/UniFi/VM evidence without a MAC address — unusual and worth a quick look.",
            ips=[record["ip"]], hostnames=all_hostnames(record)[:8], evidence=", ".join(sorted(types)),
        ))
    return findings


def check_discovered(hosts, ctx):
    findings = []
    for record in hosts:
        if "discovered" not in all_record_types(record):
            continue
        findings.append(finding(
            "medium", "discovered",
            "Unknown active IP %s" % record["ip"],
            "Responded to subnet ping sweep but has no DHCP/DNS/ARP/Proxmox/UniFi inventory entry.",
            ips=[record["ip"]], hostnames=all_hostnames(record)[:4], evidence=record.get("notes") or "ping_sweep",
        ))
    return findings


def check_cname_aliases(hosts, ctx):
    threshold = int(ctx.get("cname_alias_threshold", 10))
    findings = []
    for record in hosts:
        aliases = meta(record).get("cname_aliases") or []
        if len(aliases) < threshold:
            continue
        findings.append(finding(
            "info", "cname_aliases",
            "%s (%s) has %d CNAME aliases" % (_label(record), record["ip"], len(aliases)),
            "Not necessarily a problem — useful when auditing reverse-proxy / app hostnames.",
            ips=[record["ip"]], hostnames=aliases[:20], evidence="%d aliases" % len(aliases),
        ))
    return findings


CHECKS = {
    "mac_shared": check_mac_shared,
    "mac_conflict": check_mac_conflict,
    "hostname_shared": check_hostname_shared,
    "dns_only": check_dns_only,
    "dns_unreachable": check_dns_unreachable,
    "active_unreachable": check_active_unreachable,
    "missing_mac": check_missing_mac,
    "discovered": check_discovered,
    "cname_aliases": check_cname_aliases,
}


def analyze_issues(records, subnets=None, checks=None, skip_checks=None, cname_alias_threshold=10):
    """Run the enabled checks and return findings sorted by severity/category/summary."""
    hosts = [r for r in records if r.get("ip") and r.get("record_type") not in ("vlan", "subnet")]
    ctx = {"gateway_ips": gateway_ips(subnets), "cname_alias_threshold": cname_alias_threshold}
    selected = list(checks) if checks else list(CHECKS)
    skip = set(skip_checks or [])
    unknown = [name for name in selected if name not in CHECKS]
    if unknown:
        raise ValueError("Unknown issue check(s): %s (available: %s)" % (", ".join(unknown), ", ".join(sorted(CHECKS))))

    findings = []
    for name in selected:
        if name not in skip:
            findings.extend(CHECKS[name](hosts, ctx))
    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 99), f["category"], f["summary"]))
    return findings


def summarize_findings(findings):
    by_severity = dict((name, 0) for name in SEVERITIES)
    by_category = {}
    for item in findings:
        by_severity[item["severity"]] = by_severity.get(item["severity"], 0) + 1
        by_category[item["category"]] = by_category.get(item["category"], 0) + 1
    return {
        "total": len(findings),
        "by_severity": by_severity,
        "by_category": dict(sorted(by_category.items(), key=lambda kv: (-kv[1], kv[0]))),
        "categories": sorted(by_category),
        "severities": list(SEVERITIES),
        "descriptions": dict(CATEGORY_DESCRIPTIONS),
    }


def findings_by_ip(findings):
    """``{ip: [category, ...]}`` used to tag inventory hosts with their issues."""
    result = {}
    for item in findings:
        for ip in item.get("ips") or []:
            cats = result.setdefault(ip, [])
            if item["category"] not in cats:
                cats.append(item["category"])
    return result
