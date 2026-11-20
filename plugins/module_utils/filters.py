# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Include/exclude rules applied to observation records.

Rule dict shape (all keys optional)::

    include_networks:      [10.0.*, 192.168.1.0/24]   # allow-list; empty = allow all
    exclude_networks:      [127.*, 172.17.*]
    exclude_interfaces:    [lo0, wan]                  # fnmatch, case sensitive
    exclude_name_patterns: ["*docker*"]                # fnmatch, case insensitive
    exclude_record_types:  [dns_ptr]

Global rules apply to every source.  Per-source rules stack their excludes on
top of the global ones; a per-source ``include_networks`` replaces the global
allow-list for that source.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import fnmatch
import ipaddress

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.records import meta
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.subnets import parse_ipv4_network

RULE_KEYS = ("include_networks", "exclude_networks", "exclude_interfaces", "exclude_name_patterns", "exclude_record_types")


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(item) for item in value if str(item).strip()]


def normalize_rules(cfg):
    cfg = cfg or {}
    return dict((key, _as_list(cfg.get(key))) for key in RULE_KEYS)


def wildcard_to_network(pattern):
    pattern = pattern.strip()
    if not pattern:
        return None
    if "/" in pattern and "*" not in pattern:
        return parse_ipv4_network(pattern)
    if "*" not in pattern:
        try:
            return ipaddress.ip_network("%s/32" % pattern, strict=False)
        except ValueError:
            return None

    fixed = []
    for part in pattern.split("."):
        if part in ("*", ""):
            break
        try:
            fixed.append(int(part))
        except ValueError:
            return None
    if not fixed:
        return None
    prefix = len(fixed) * 8
    octets = fixed + [0] * (4 - len(fixed))
    try:
        return ipaddress.ip_network("%s/%d" % (".".join(str(o) for o in octets), prefix), strict=False)
    except ValueError:
        return None


def ip_matches_pattern(ip, pattern):
    pattern = pattern.strip()
    if not pattern:
        return False
    network = wildcard_to_network(pattern)
    if network is not None and ("*" in pattern or "/" in pattern):
        try:
            return ipaddress.ip_address(ip) in network
        except ValueError:
            return False
    expanded = pattern if pattern.count(".") >= 3 else ".".join((pattern.split(".") + ["*", "*", "*"])[:4])
    while expanded.count(".") < 3:
        expanded += ".*"
    return fnmatch.fnmatchcase(ip, expanded)


def network_matches_pattern(network, pattern):
    implied = wildcard_to_network(pattern)
    if implied is not None:
        return network.subnet_of(implied) or network.overlaps(implied)
    try:
        return ip_matches_pattern(str(network.network_address), pattern)
    except ValueError:
        return False


class RecordFilter:
    def __init__(self, global_rules=None, source_rules=None):
        self.global_rules = normalize_rules(global_rules)
        self.source_rules = dict((name, normalize_rules(rules)) for name, rules in (source_rules or {}).items())

    def _rules_for(self, source):
        return self.source_rules.get(source) or normalize_rules(None)

    def effective_includes(self, source):
        return self._rules_for(source)["include_networks"] or self.global_rules["include_networks"]

    def effective_excludes(self, source):
        source_rules = self._rules_for(source)
        return dict((key, self.global_rules[key] + source_rules[key]) for key in RULE_KEYS if key != "include_networks")

    def include_record(self, record):
        source = record.get("source") or ""
        excludes = self.effective_excludes(source)
        includes = self.effective_includes(source)
        ip = record.get("ip")

        if record.get("record_type") in excludes["exclude_record_types"]:
            return False
        if not self._passes_name_filters(record, excludes["exclude_name_patterns"]):
            return False
        if not self._passes_interface_filters(record, excludes["exclude_interfaces"]):
            return False

        if ip:
            if includes and not any(ip_matches_pattern(ip, p) for p in includes):
                return False
            if any(ip_matches_pattern(ip, p) for p in excludes["exclude_networks"]):
                return False

        cidr = meta(record).get("cidr") or meta(record).get("subnet")
        if cidr and record.get("record_type") in ("subnet", "vlan"):
            network = parse_ipv4_network(str(cidr))
            if network is not None:
                if includes and not any(network_matches_pattern(network, p) for p in includes):
                    return False
                if any(network_matches_pattern(network, p) for p in excludes["exclude_networks"]):
                    return False
        return True

    def include_subnet_for_discovery(self, subnet):
        if subnet.get("record_type") != "subnet" or not self.include_record(subnet):
            return False
        network = parse_ipv4_network(meta(subnet).get("cidr"))
        if network is None:
            return False
        includes = self.effective_includes(subnet.get("source") or "")
        if includes:
            return any(network_matches_pattern(network, p) for p in includes)
        return True

    def filter_records(self, records):
        return [record for record in records if self.include_record(record)]

    @staticmethod
    def _passes_name_filters(record, patterns):
        if not patterns:
            return True
        md = meta(record)
        haystacks = [
            record.get("hostname") or "",
            record.get("notes") or "",
            md.get("description") or "",
            md.get("interface_description") or "",
        ]
        haystacks.extend(md.get("all_hostnames") or [])
        for pattern in patterns:
            for value in haystacks:
                if value and fnmatch.fnmatchcase(str(value).lower(), pattern.lower()):
                    return False
        return True

    @staticmethod
    def _passes_interface_filters(record, patterns):
        if not patterns:
            return True
        md = meta(record)
        candidates = [record.get("hostname") or "", md.get("identifier") or "", md.get("interface") or "", record.get("vlan") or ""]
        for pattern in patterns:
            for value in candidates:
                if value and fnmatch.fnmatchcase(str(value), pattern):
                    return False
        return True
