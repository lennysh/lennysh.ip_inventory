# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Common record schema and helpers shared by every collector and processing step.

An *observation record* is a plain dict (JSON serialisable so it can travel
through Ansible facts) with these keys::

    ip            str   IPv4 address ('' for VLAN definitions)
    hostname      str|None
    source        str   collector name (opnsense, technitium, ...)
    record_type   str   arp, dhcp_lease, dns_a, subnet, vlan, ...
    mac           str|None
    vlan          str|None
    notes         str|None
    metadata      dict  source specific extras
    ping_status   str|None  up | down | skipped

New collectors only need to emit records in this shape (use ``make_record``)
for every downstream step (filter, reconcile, ping, issues, reports, inventory
plugin) to work with them.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import ipaddress
import re

RECORD_KEYS = ("ip", "hostname", "source", "record_type", "mac", "vlan", "notes", "metadata", "ping_status")

INFRA_RECORD_TYPES = frozenset(["subnet", "vlan"])

DNS_RECORD_TYPES = frozenset(["dns_a", "dns_aname", "dns_cname", "dns_ptr", "dns_override"])

# Observations that prove a device was recently live on the network.
ACTIVE_RECORD_TYPES = frozenset(["arp", "client_active", "vm_guest_agent", "lxc_runtime", "device", "discovered"])

# Live observations plus DHCP state (should carry a MAC address).
LIVE_RECORD_TYPES = ACTIVE_RECORD_TYPES | frozenset(["dhcp_lease", "dhcp_dynamic", "dhcp_reserved", "dhcp_static"])

# Lower number wins when choosing the primary record / MAC / hostname for an IP.
RECORD_PRIORITY = {
    "arp": 0,
    "dhcp_lease": 1,
    "dhcp_dynamic": 1,
    "dhcp_reserved": 2,
    "dhcp_static": 3,
    "vm_guest_agent": 4,
    "lxc_runtime": 4,
    "dns_override": 5,
    "dns_a": 6,
    "dns_aname": 6,
    "dns_ptr": 7,
    "dns_cname": 8,
    "qemu_config_static": 9,
    "lxc_config_static": 9,
}

_MAC_HEX_RE = re.compile(r"[^0-9a-fA-F]")
_IPV4_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")


def make_record(ip, hostname=None, source="", record_type="", mac=None, vlan=None, notes=None, metadata=None, ping_status=None):
    """Build an observation record dict with every key present."""
    return {
        "ip": ip or "",
        "hostname": hostname or None,
        "source": source or "",
        "record_type": record_type or "",
        "mac": mac or None,
        "vlan": vlan if vlan not in ("", None) else None,
        "notes": notes or None,
        "metadata": dict(metadata or {}),
        "ping_status": ping_status,
    }


def normalize_record(record):
    """Return a copy of ``record`` with every schema key present (hand-written records may omit some)."""
    new = dict(record)
    for key in RECORD_KEYS:
        new.setdefault(key, "" if key in ("ip", "source", "record_type") else None)
    new["metadata"] = dict(new.get("metadata") or {})
    return new


def copy_record(record, **changes):
    """Shallow copy a record (with its own metadata dict) applying ``changes``."""
    new = dict(record)
    new["metadata"] = dict(record.get("metadata") or {})
    new.update(changes)
    return new


def normalize_mac(mac):
    if not mac:
        return None
    hex_digits = _MAC_HEX_RE.sub("", str(mac))
    if len(hex_digits) != 12:
        return str(mac).strip().lower()
    return ":".join(hex_digits[i:i + 2].lower() for i in range(0, 12, 2))


def valid_ipv4(value):
    """Return the stripped IPv4 string if ``value`` is a dotted-quad address, else None."""
    if not value:
        return None
    value = str(value).strip()
    if not _IPV4_RE.match(value):
        return None
    try:
        ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        return None
    return value


def ip_sort_key(ip):
    try:
        return tuple(int(part) for part in str(ip).split("."))
    except ValueError:
        return (999, 999, 999, 999)


def record_priority(record_type):
    return RECORD_PRIORITY.get(record_type, 99)


def meta(record):
    return record.get("metadata") or {}


def all_sources(record):
    sources = meta(record).get("all_sources")
    if sources:
        return list(sources)
    return [record["source"]] if record.get("source") else []


def all_record_types(record):
    types = meta(record).get("all_record_types")
    if types:
        return list(types)
    return [record["record_type"]] if record.get("record_type") else []


def all_hostnames(record):
    names = meta(record).get("all_hostnames") or []
    if names:
        return [name for name in names if name]
    return [record["hostname"]] if record.get("hostname") else []


def all_macs(record):
    macs = meta(record).get("all_macs") or []
    if macs:
        return [mac for mac in macs if mac]
    mac = normalize_mac(record.get("mac"))
    return [mac] if mac else []
