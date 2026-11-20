# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Subnet / VLAN helpers: CIDR math, VLAN tag matching, subnet enrichment."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import ipaddress
import re

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.records import copy_record, meta

_VLAN_DIGITS = re.compile(r"\d+")


def vlan_key(value):
    if not value:
        return None
    match = _VLAN_DIGITS.search(str(value))
    if not match:
        return None
    digits = match.group(0).lstrip("0")
    return digits or "0"


def parse_ipv4_network(cidr):
    if not cidr:
        return None
    try:
        network = ipaddress.ip_network(str(cidr), strict=False)
    except ValueError:
        return None
    if network.version != 4:
        return None
    return network


def is_private_network(network):
    return network.is_private or network.is_link_local


def enrich_subnet_record(record):
    """Add netmask / prefix_length / broadcast / total_hosts to a subnet record."""
    network = parse_ipv4_network(meta(record).get("cidr"))
    if network is None:
        return record
    new = copy_record(record)
    new["metadata"].update({
        "cidr": str(network),
        "netmask": str(network.netmask),
        "prefix_length": network.prefixlen,
        "broadcast": str(network.broadcast_address),
        "total_hosts": network.num_addresses - 2 if network.num_addresses > 2 else 0,
    })
    return new


def enrich_subnets(records):
    return [enrich_subnet_record(record) for record in records]


def _clean_vlan_name(hostname):
    return (hostname or "").rsplit(" (vlan ", 1)[0].strip() or hostname


def enrich_subnets_with_vlans(subnet_records, vlan_records):
    """Attach VLAN name/parent from VLAN definitions onto matching subnet rows."""
    vlans_by_tag = {}
    for vlan in vlan_records:
        key = vlan_key(vlan.get("vlan"))
        if key and key not in vlans_by_tag:
            vlans_by_tag[key] = vlan

    enriched = []
    for subnet in enrich_subnets(subnet_records):
        matched = vlans_by_tag.get(vlan_key(subnet.get("vlan")) or "")
        if not matched:
            enriched.append(subnet)
            continue
        vlan_name = matched.get("hostname")
        # Prefer the clean description without the "(vlan N)" suffix when present.
        if (matched.get("notes") or "").startswith("parent="):
            vlan_name = _clean_vlan_name(matched.get("hostname"))
        new = copy_record(subnet)
        new["metadata"].update({
            "vlan_name": vlan_name,
            "vlan_parent": meta(matched).get("parent"),
            "vlan_uuid": meta(matched).get("uuid"),
        })
        enriched.append(new)
    return enriched


def unmatched_vlans(vlan_records, subnet_records):
    """VLAN definitions with no matching interface subnet (still useful for subnet reports)."""
    subnet_tags = set(vlan_key(s.get("vlan")) for s in subnet_records if vlan_key(s.get("vlan")))
    leftover = []
    for vlan in vlan_records:
        key = vlan_key(vlan.get("vlan"))
        if not key or key in subnet_tags:
            continue
        name = _clean_vlan_name(vlan.get("hostname"))
        new = copy_record(vlan, hostname=name)
        new["metadata"].update({"vlan_name": name, "vlan_parent": meta(vlan).get("parent")})
        leftover.append(new)
    return leftover
