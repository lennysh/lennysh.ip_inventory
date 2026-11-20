# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Reconcile raw observations into one row per IP, enriched with subnet/VLAN data."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import re
from collections import defaultdict

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.records import (
    DNS_RECORD_TYPES,
    INFRA_RECORD_TYPES,
    copy_record,
    ip_sort_key,
    meta,
    normalize_mac,
    record_priority,
)
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.subnets import (
    enrich_subnets_with_vlans,
    parse_ipv4_network,
    unmatched_vlans,
    vlan_key,
)

_PROXMOX_NOTE_PREFIX = re.compile(r"^vmid=\d+ node=\S+\s*")


def reconcile(records):
    """Merge host observations by IP and fold VLAN definitions into subnets.

    Returns a dict with ``hosts`` (merged, enriched, sorted), ``subnets``
    (enriched with VLAN names) and ``orphan_vlans`` (VLAN defs with no subnet).
    """
    host_records = [r for r in records if r.get("record_type") not in INFRA_RECORD_TYPES]
    vlan_records = [r for r in records if r.get("record_type") == "vlan"]
    raw_subnets = [r for r in records if r.get("record_type") == "subnet"]

    subnets = enrich_subnets_with_vlans(raw_subnets, vlan_records)
    orphan_vlans = unmatched_vlans(vlan_records, subnets)
    hosts = enrich_with_subnets(merge_hosts(host_records), subnets)
    return {"hosts": sort_records(hosts), "subnets": subnets, "orphan_vlans": orphan_vlans}


def enrich_with_subnets(hosts, subnets):
    networks = []
    for subnet in subnets:
        network = parse_ipv4_network(meta(subnet).get("cidr"))
        if network is not None:
            networks.append((network, subnet))
    # Prefer more-specific (longer prefix) matches first.
    networks.sort(key=lambda item: item[0].prefixlen, reverse=True)

    enriched = []
    for host in hosts:
        net = parse_ipv4_network(host.get("ip") + "/32") if host.get("ip") else None
        matched = None
        if net is not None:
            address = net.network_address
            for network, subnet in networks:
                if address in network:
                    matched = subnet
                    break
        if not matched:
            enriched.append(host)
            continue

        # Prefer the subnet's VLAN tag; ignore ARP interface names in the vlan field.
        host_vlan = host.get("vlan") if vlan_key(host.get("vlan")) else None
        smeta = meta(matched)
        new = copy_record(host, vlan=matched.get("vlan") or host_vlan)
        new["metadata"].update({
            "subnet": smeta.get("cidr"),
            "netmask": smeta.get("netmask"),
            "prefix_length": smeta.get("prefix_length"),
            "vlan_tag": matched.get("vlan"),
            "vlan_name": smeta.get("vlan_name") or matched.get("notes"),
            "interface": matched.get("hostname"),
            "interface_description": matched.get("notes"),
        })
        enriched.append(new)
    return enriched


def merge_hosts(records):
    by_ip = defaultdict(list)
    for record in records:
        if record.get("ip"):
            by_ip[record["ip"]].append(record)

    merged = []
    for ip in sorted(by_ip, key=ip_sort_key):
        group = by_ip[ip]
        hostnames = sorted(set(r["hostname"] for r in group if r.get("hostname")))
        sources = sorted(set(r["source"] for r in group if r.get("source")))
        record_types = sorted(set(r["record_type"] for r in group if r.get("record_type")))
        macs = sorted(set(m for m in (normalize_mac(r.get("mac")) for r in group) if m))
        vlans = sorted(set(str(r["vlan"]) for r in group if r.get("vlan")))
        dns_names = sorted(set(r["hostname"] for r in group if r.get("hostname") and r.get("record_type") in DNS_RECORD_TYPES))
        cname_aliases = sorted(set(r["hostname"] for r in group if r.get("hostname") and r.get("record_type") == "dns_cname"))

        primary = _pick_primary(group)
        mac = macs[0] if len(macs) == 1 else (_pick_mac(group) if macs else None)
        new = copy_record(
            primary,
            ip=ip,
            hostname=_pick_hostname(group, hostnames),
            mac=mac,
            vlan=vlans[0] if len(vlans) == 1 else None,
            notes=_merge_notes(group),
        )
        new["metadata"].update({
            "all_hostnames": hostnames,
            "dns_names": dns_names,
            "cname_aliases": cname_aliases,
            "all_sources": sources,
            "all_record_types": record_types,
            "all_macs": macs,
            "observation_count": len(group),
            "dns_only": bool(record_types) and set(record_types) <= DNS_RECORD_TYPES,
            "source_metadata": _source_metadata(group),
        })
        merged.append(new)
    return merged


def _source_metadata(group):
    """Per-source metadata (highest priority record wins per key), e.g. Proxmox vmid/node."""
    by_source = {}
    for record in sorted(group, key=lambda r: (record_priority(r.get("record_type")), r.get("source") or "")):
        bucket = by_source.setdefault(record.get("source") or "unknown", {})
        for key, value in meta(record).items():
            if value is not None and key not in bucket:
                bucket[key] = value
        bucket.setdefault("record_types", [])
        if record.get("record_type") and record["record_type"] not in bucket["record_types"]:
            bucket["record_types"].append(record["record_type"])
    return by_source


def _pick_hostname(group, hostnames):
    if not hostnames:
        return None
    # Prefer a non-CNAME name as the primary label when available.
    for record in sorted(group, key=lambda r: record_priority(r.get("record_type"))):
        if record.get("hostname") and record.get("record_type") != "dns_cname":
            return record["hostname"]
    return hostnames[0]


def _merge_notes(group):
    unique_notes = []
    for record in group:
        note = record.get("notes")
        if note and note not in unique_notes:
            unique_notes.append(note)
    if not unique_notes:
        return None
    if len(unique_notes) == 1:
        return unique_notes[0]

    prefixes = []
    for note in unique_notes:
        match = _PROXMOX_NOTE_PREFIX.match(note)
        if match:
            prefixes.append(match.group(0).strip())
    if len(prefixes) == len(unique_notes) and len(set(prefixes)) == 1:
        prefix = prefixes[0]
        details = []
        for note in unique_notes:
            detail = _PROXMOX_NOTE_PREFIX.sub("", note).strip(" ;")
            if detail and detail not in details:
                details.append(detail)
        if details:
            return "%s %s" % (prefix, "; ".join(details[:3]))
        return prefix

    return "; ".join(unique_notes[:3])


def sort_records(records):
    """Hosts by IP, then ping-sweep discoveries, then VLAN reference rows."""
    type_order = {"discovered": 1, "vlan": 2}
    return sorted(
        records,
        key=lambda r: (
            type_order.get(r.get("record_type"), 0),
            ip_sort_key(r["ip"]) if r.get("ip") else (999, 999, 999, 999),
            r.get("hostname") or "",
        ),
    )


def _pick_mac(group):
    for record in sorted(group, key=lambda r: record_priority(r.get("record_type"))):
        mac = normalize_mac(record.get("mac"))
        if mac:
            return mac
    return None


def _pick_primary(group):
    return sorted(group, key=lambda r: (record_priority(r.get("record_type")), r.get("source") or ""))[0]
