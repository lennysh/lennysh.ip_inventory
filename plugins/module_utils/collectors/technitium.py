# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Technitium DNS: zone A/ANAME/CNAME/PTR records, DHCP leases and reservations."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import ipaddress

from ansible.module_utils.basic import env_fallback

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.collectors.base import Collector, connection_spec
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.api_client import ApiError
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.records import make_record

_A_RECORD_TYPES = ("A", "ANAME")
_SKIP_ZONE_TYPES = ("Forwarder", "Stub", "Secondary")


def _normalize_name(name):
    if not name:
        return None
    return str(name).strip().rstrip(".").lower() or None


def _fqdn(name, zone_name):
    name = (name or "").strip().rstrip(".")
    zone_name = zone_name.strip().rstrip(".")
    if not name or name == "@":
        return zone_name
    if name == zone_name or name.endswith("." + zone_name):
        return name
    return "%s.%s" % (name, zone_name)


def _rdata(entry):
    value = entry.get("rData") or entry.get("RData") or {}
    return value if isinstance(value, dict) else {}


def _record_ipv4(entry):
    rdata = _rdata(entry)
    candidates = [
        entry.get("ipAddress"),
        rdata.get("ipAddress"),
        rdata.get("ip"),
        entry.get("rData") if isinstance(entry.get("rData"), str) else None,
        entry.get("RData") if isinstance(entry.get("RData"), str) else None,
    ]
    for candidate in candidates:
        if not candidate:
            continue
        parts = str(candidate).split()
        if not parts:
            continue
        try:
            return str(ipaddress.IPv4Address(parts[0].strip()))
        except ipaddress.AddressValueError:
            continue
    return None


def _ptr_ipv4(name):
    """Convert ``10.1.168.192.in-addr.arpa`` to ``192.168.1.10``."""
    if not name:
        return None
    value = name.strip().rstrip(".").lower()
    suffix = ".in-addr.arpa"
    if not value.endswith(suffix):
        return None
    labels = value[:-len(suffix)].split(".")
    if len(labels) != 4:
        return None
    try:
        return str(ipaddress.IPv4Address(".".join(reversed(labels))))
    except ipaddress.AddressValueError:
        return None


class TechnitiumCollector(Collector):
    name = "technitium"
    argument_spec = dict(
        connection_spec("TECHNITIUM", validate_certs_default=True),
        token={"type": "str", "no_log": True, "fallback": (env_fallback, ["TECHNITIUM_TOKEN"])},
        user={"type": "str", "aliases": ["username"], "fallback": (env_fallback, ["TECHNITIUM_USER"])},
        password={"type": "str", "no_log": True, "fallback": (env_fallback, ["TECHNITIUM_PASSWORD"])},
        collect={
            "type": "dict",
            "default": {},
            "apply_defaults": True,
            "options": {
                "dns_records": {"type": "bool", "default": True},
                "dns_cnames": {"type": "bool", "default": True},
                "dns_ptrs": {"type": "bool", "default": True},
                "dhcp_leases": {"type": "bool", "default": True},
                "dhcp_scopes": {"type": "bool", "default": True},
            },
        },
    )

    def _login(self):
        if self.params.get("token"):
            return self.params["token"]
        user, password = self.params.get("user"), self.params.get("password")
        if not user or not password:
            raise ApiError("Technitium requires token or user/password")
        client = self.client()
        for path in ("/api/user/login", "/api/login"):
            status, payload = client.request("POST", path, params={"user": user, "pass": password}, allow_status=(404,))
            if status == 404:
                continue
            payload = payload or {}
            token = payload.get("token") or (payload.get("response") or {}).get("token")
            if token:
                return token
        raise ApiError("Technitium login failed")

    @staticmethod
    def _get_json(client, path, params=None):
        payload = client.get(path, params=params or {}) or {}
        if payload.get("status") == "error":
            raise ApiError(payload.get("errorMessage") or payload.get("error") or "Technitium API error")
        return payload.get("response", payload)

    def collect(self):
        token = self._login()
        client = self.client(headers={"Authorization": "Bearer %s" % token})
        opts = self.collect_opts
        records = []
        if opts.get("dns_records", True) or opts.get("dns_cnames", True) or opts.get("dns_ptrs", True):
            records.extend(self._collect_dns_records(client))
        if opts.get("dhcp_leases", True):
            records.extend(self._collect_dhcp_leases(client))
        if opts.get("dhcp_scopes", True):
            records.extend(self._collect_dhcp_scopes(client))
        return records

    def _iter_zone_entries(self, client):
        zones_payload = self._get_json(client, "/api/zones/list")
        zones = zones_payload.get("zones", zones_payload)
        if isinstance(zones, dict):
            zones = list(zones.values())

        entries = []
        for zone in zones or []:
            if not isinstance(zone, dict):
                continue
            zone_name = zone.get("name")
            if not zone_name or zone.get("internal"):
                continue
            if (zone.get("type") or zone.get("zoneType")) in _SKIP_ZONE_TYPES:
                continue
            zone_records = self._get_json(
                client, "/api/zones/records/get", {"zone": zone_name, "domain": zone_name, "listZone": "true"}
            )
            for entry in zone_records.get("records", []):
                if isinstance(entry, dict) and not entry.get("disabled"):
                    entries.append((zone_name, entry))
        return entries

    def _collect_dns_records(self, client):
        opts = self.collect_opts
        records, a_records, cname_pairs, name_to_ips = [], [], [], {}

        for zone_name, entry in self._iter_zone_entries(client):
            rtype = (entry.get("type") or entry.get("Type") or "").upper()
            if rtype in _A_RECORD_TYPES and opts.get("dns_records", True):
                record = self._a_record(zone_name, entry, rtype)
                if not record:
                    continue
                a_records.append(record)
                key = _normalize_name(record["hostname"])
                if key:
                    name_to_ips.setdefault(key, set()).add(record["ip"])
            elif rtype == "CNAME" and opts.get("dns_cnames", True):
                alias, target = self._cname_pair(zone_name, entry)
                if alias and target and not alias.lower().startswith("*."):
                    cname_pairs.append((alias, target, zone_name, entry))
            elif rtype == "PTR" and opts.get("dns_ptrs", True):
                record = self._ptr_record(zone_name, entry)
                if record:
                    records.append(record)

        records.extend(a_records)
        if opts.get("dns_cnames", True) and cname_pairs:
            records.extend(self._resolve_cnames(cname_pairs, name_to_ips))
        return records

    def _a_record(self, zone_name, entry, rtype):
        ip = _record_ipv4(entry)
        if not ip:
            return None
        return make_record(
            ip, hostname=_fqdn(entry.get("name") or entry.get("Name"), zone_name), source=self.name,
            record_type="dns_a" if rtype == "A" else "dns_aname",
            notes=entry.get("comments") or "zone=%s" % zone_name,
            metadata={"ttl": entry.get("ttl"), "zone": zone_name, "dns_type": rtype},
        )

    @staticmethod
    def _cname_pair(zone_name, entry):
        alias = _fqdn(entry.get("name") or entry.get("Name"), zone_name)
        target = _normalize_name(_rdata(entry).get("cname") or entry.get("cname"))
        return alias, target

    def _resolve_cnames(self, cname_pairs, name_to_ips):
        cname_map = {}
        for alias, target, _zone, _entry in cname_pairs:
            key = _normalize_name(alias)
            if key and target:
                cname_map[key] = target

        records = []
        for alias, target, zone_name, entry in cname_pairs:
            resolved_target, ips = self._follow_cname(_normalize_name(alias) or "", cname_map, name_to_ips)
            for ip in sorted(ips):
                chain = u"%s → %s" % (alias, target)
                if resolved_target and resolved_target != target:
                    chain = u"%s → %s → %s" % (alias, target, resolved_target)
                records.append(make_record(
                    ip, hostname=alias, source=self.name, record_type="dns_cname",
                    notes=entry.get("comments") or chain,
                    metadata={
                        "ttl": entry.get("ttl"),
                        "zone": zone_name,
                        "dns_type": "CNAME",
                        "cname_target": target,
                        "cname_resolved": resolved_target,
                        "dns_alias": True,
                    },
                ))
        return records

    @staticmethod
    def _follow_cname(start, cname_map, name_to_ips, max_depth=8):
        seen = set()
        current = start
        for _dummy in range(max_depth):
            if current in seen:
                return None, set()
            seen.add(current)
            target = cname_map.get(current)
            if not target:
                return current, set(name_to_ips.get(current, set()))
            if target in name_to_ips:
                return target, set(name_to_ips[target])
            current = target
        return None, set()

    def _ptr_record(self, zone_name, entry):
        name = entry.get("name") or entry.get("Name")
        ip = _ptr_ipv4(name)
        if not ip:
            return None
        return make_record(
            ip, hostname=_normalize_name(_rdata(entry).get("ptrName") or entry.get("ptrName")), source=self.name,
            record_type="dns_ptr", notes=entry.get("comments") or "zone=%s" % zone_name,
            metadata={"ttl": entry.get("ttl"), "zone": zone_name, "dns_type": "PTR", "ptr_name": name},
        )

    def _collect_dhcp_leases(self, client):
        records = []
        for lease in self._get_json(client, "/api/dhcp/leases/list").get("leases", []):
            if not lease.get("address"):
                continue
            records.append(make_record(
                lease["address"], hostname=lease.get("hostName"), source=self.name,
                record_type="dhcp_%s" % (lease.get("type") or "lease").lower(), mac=lease.get("hardwareAddress"),
                notes="scope=%s" % lease.get("scope"),
                metadata={"lease_obtained": lease.get("leaseObtained"), "lease_expires": lease.get("leaseExpires")},
            ))
        return records

    def _collect_dhcp_scopes(self, client):
        records = []
        for scope in self._get_json(client, "/api/dhcp/scopes/list").get("scopes", []):
            scope_name = scope.get("name", "Default")
            for reserved in scope.get("reservedLeases", []) or []:
                if isinstance(reserved, str):
                    parts = reserved.split("|")
                    if len(parts) < 3:
                        continue
                    hostname, mac, ip = parts[0], parts[1], parts[2]
                    comment = parts[3] if len(parts) > 3 else None
                elif isinstance(reserved, dict):
                    hostname = reserved.get("hostName") or reserved.get("hostname")
                    mac = reserved.get("hardwareAddress") or reserved.get("mac")
                    ip = reserved.get("ipAddress") or reserved.get("address")
                    comment = reserved.get("comments") or reserved.get("comment")
                else:
                    continue
                if not ip:
                    continue
                records.append(make_record(
                    ip, hostname=hostname, source=self.name, record_type="dhcp_reserved", mac=mac,
                    notes=comment or "scope=%s" % scope_name, metadata={"scope": scope_name},
                ))
        return records
