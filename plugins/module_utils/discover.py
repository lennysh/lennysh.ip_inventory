# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Subnet sweep: find responders in collected subnets that no source knows about."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.records import make_record, meta
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.subnets import (
    enrich_subnets,
    is_private_network,
    parse_ipv4_network,
)


def known_ips(hosts):
    return set(r["ip"] for r in hosts if r.get("ip") and r.get("record_type") != "vlan")


def sweep_candidates(subnets, known, max_hosts_per_subnet=512, private_only=True, record_filter=None):
    """Return ``[{'ip': ..., 'cidr': ...}]`` for unused addresses worth pinging."""
    known = set(known or [])
    seen = set()
    candidates = []
    for subnet in enrich_subnets(subnets):
        if record_filter is not None and not record_filter.include_subnet_for_discovery(subnet):
            continue
        network = parse_ipv4_network(meta(subnet).get("cidr"))
        if network is None or network.prefixlen >= 31:
            continue
        if private_only and not is_private_network(network):
            continue
        host_count = max(network.num_addresses - 2, 0)
        if host_count <= 0 or host_count > int(max_hosts_per_subnet):
            continue
        for host in network.hosts():
            ip = str(host)
            if (subnet.get("ip") and ip == subnet["ip"]) or ip in known or ip in seen:
                continue
            seen.add(ip)
            candidates.append({"ip": ip, "cidr": str(network)})
    return candidates


def discovered_records(candidates, results, subnets):
    """Turn ping-sweep responders into ``discovered`` records."""
    by_cidr = {}
    for subnet in enrich_subnets(subnets):
        cidr = meta(subnet).get("cidr")
        if cidr and cidr not in by_cidr:
            by_cidr[cidr] = subnet

    discovered = []
    for candidate in candidates:
        value = results.get(candidate["ip"])
        if not (value is True or value == "up"):
            continue
        cidr = candidate.get("cidr")
        subnet = by_cidr.get(cidr) or make_record("")
        smeta = meta(subnet)
        discovered.append(make_record(
            candidate["ip"],
            source="ping_sweep",
            record_type="discovered",
            vlan=subnet.get("vlan"),
            notes="Responds to ping but not in DHCP/DNS/ARP/Proxmox inventory (%s)" % cidr,
            ping_status="up",
            metadata={
                "subnet": cidr,
                "netmask": smeta.get("netmask"),
                "prefix_length": smeta.get("prefix_length"),
                "vlan_tag": subnet.get("vlan"),
                "vlan_name": smeta.get("vlan_name"),
                "interface": subnet.get("hostname"),
                "interface_description": subnet.get("notes"),
                "all_sources": ["ping_sweep"],
                "all_record_types": ["discovered"],
                "all_hostnames": [],
                "all_macs": [],
                "observation_count": 1,
            },
        ))
    return discovered
