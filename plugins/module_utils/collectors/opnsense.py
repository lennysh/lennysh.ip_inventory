# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
"""OPNsense: interface subnets, VLAN definitions, ARP table, optional DHCP/Unbound."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import ipaddress

from ansible.module_utils.basic import env_fallback

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.collectors.base import Collector, connection_spec
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.api_client import ApiError
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.records import make_record, valid_ipv4

_SEARCH_PAYLOAD = {"current": 1, "rowCount": -1, "sort": {}, "searchPhrase": ""}


def _fqdn(hostname, domain):
    hostname = (hostname or "").strip(".")
    domain = (domain or "").strip(".")
    if hostname and domain:
        if hostname.endswith("." + domain):
            return hostname
        return "%s.%s" % (hostname, domain)
    return hostname or domain or None


def _api_rows(data):
    """Normalize OPNsense payloads that may be a grid dict or a bare list."""
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        return [row for row in data["rows"] if isinstance(row, dict)]
    return []


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


class OpnsenseCollector(Collector):
    name = "opnsense"
    argument_spec = dict(
        connection_spec("OPNSENSE"),
        api_key={"type": "str", "required": True, "no_log": True, "fallback": (env_fallback, ["OPNSENSE_API_KEY"])},
        api_secret={"type": "str", "required": True, "no_log": True, "fallback": (env_fallback, ["OPNSENSE_API_SECRET"])},
        dhcp_backend={"type": "str", "default": "auto", "choices": ["auto", "kea", "isc"]},
        collect={
            "type": "dict",
            "default": {},
            "apply_defaults": True,
            "options": {
                "arp_table": {"type": "bool", "default": True},
                "interfaces": {"type": "bool", "default": True},
                "vlans": {"type": "bool", "default": True},
                "dhcp_leases": {"type": "bool", "default": False},
                "dhcp_static": {"type": "bool", "default": False},
                "unbound_overrides": {"type": "bool", "default": False},
            },
        },
    )

    def _check(self, data):
        if isinstance(data, dict) and data.get("errorMessage"):
            raise ApiError(data["errorMessage"])
        return data

    def _post(self, client, path, payload=None):
        return self._check(client.post(path, json_body=payload or _SEARCH_PAYLOAD))

    def _get(self, client, path):
        return self._check(client.get(path))

    def collect(self):
        client = self.client(url_username=self.params["api_key"], url_password=self.params["api_secret"], force_basic_auth=True)
        opts = self.collect_opts
        records = []
        if opts.get("dhcp_leases"):
            records.extend(self._collect_dhcp_leases(client))
        if opts.get("dhcp_static"):
            records.extend(self._collect_dhcp_static(client))
        if opts.get("unbound_overrides"):
            records.extend(self._collect_unbound(client))
        if opts.get("arp_table", True):
            records.extend(self._collect_arp(client))
        if opts.get("interfaces", True):
            records.extend(self._collect_interfaces(client))
        if opts.get("vlans", True):
            records.extend(self._collect_vlans(client))
        return records

    def _collect_dhcp_leases(self, client):
        records = []
        backend = self.params.get("dhcp_backend", "auto")
        if backend in ("auto", "kea"):
            try:
                for row in _api_rows(self._post(client, "/api/kea/leases4/search")):
                    ip = valid_ipv4(row.get("address") or row.get("ip_address"))
                    if not ip:
                        continue
                    records.append(make_record(
                        ip, hostname=row.get("hostname") or row.get("client_id"), source=self.name,
                        record_type="dhcp_lease", mac=row.get("hwaddr") or row.get("mac"),
                        notes=row.get("if_descr") or row.get("if"),
                        metadata={"backend": "kea", "state": row.get("state")},
                    ))
                if records or backend == "kea":
                    return records
            except ApiError:
                if backend == "kea":
                    raise

        for row in _api_rows(self._get(client, "/api/dhcpv4/leases/search_lease")):
            ip = valid_ipv4(row.get("address") or row.get("ip"))
            if not ip:
                continue
            records.append(make_record(
                ip, hostname=row.get("hostname") or row.get("client_id"), source=self.name,
                record_type="dhcp_lease", mac=row.get("mac"), notes=row.get("if_descr") or row.get("interface"),
                metadata={"backend": "isc", "state": row.get("state"), "ends": row.get("ends")},
            ))
        return records

    def _collect_dhcp_static(self, client):
        records = []
        backend = self.params.get("dhcp_backend", "auto")
        if backend in ("auto", "kea"):
            try:
                for row in _api_rows(self._post(client, "/api/kea/dhcpv4/search_reservation")):
                    ip = valid_ipv4(row.get("ip_address") or row.get("address"))
                    if not ip:
                        continue
                    records.append(make_record(
                        ip, hostname=row.get("hostname") or row.get("description"), source=self.name,
                        record_type="dhcp_static", mac=row.get("hwaddr") or row.get("mac"),
                        notes=row.get("if_descr") or row.get("if"), metadata={"backend": "kea"},
                    ))
            except ApiError:
                if backend == "kea":
                    raise
        return records

    def _collect_unbound(self, client):
        records = []
        for row in _api_rows(self._post(client, "/api/unbound/settings/search_host_override")):
            rr = (row.get("rr") or "A").upper()
            if rr not in ("A", "AAAA"):
                continue
            ip = valid_ipv4(row.get("server"))
            if not ip and rr == "A":
                continue
            records.append(make_record(
                ip or row.get("server", ""), hostname=_fqdn(row.get("hostname"), row.get("domain")), source=self.name,
                record_type="dns_override", notes=row.get("description"),
                metadata={"rr": rr, "enabled": row.get("enabled"), "uuid": row.get("uuid")},
            ))
        return records

    def _collect_arp(self, client):
        records = []
        for row in _api_rows(self._get(client, "/api/diagnostics/interface/get_arp")):
            ip = valid_ipv4(row.get("ip") or row.get("address"))
            if not ip:
                continue
            records.append(make_record(
                ip, hostname=row.get("hostname") or row.get("name"), source=self.name, record_type="arp",
                mac=row.get("mac") or row.get("hwaddr"), vlan=row.get("intf") or row.get("interface"),
                metadata={"expires": row.get("expires"), "permanent": row.get("permanent")},
            ))
        return records

    def _collect_interfaces(self, client):
        records = []
        for row in _api_rows(self._get(client, "/api/interfaces/overview/interfaces_info")):
            identifier = row.get("identifier") or row.get("device")
            descr = row.get("description") or row.get("descr") or identifier
            vlan_tag = row.get("vlan_tag")
            if not vlan_tag and isinstance(row.get("vlan"), dict):
                vlan_tag = row["vlan"].get("tag")

            addresses = []
            for entry in _as_list(row.get("ipv4")):
                addr = (entry.get("ipaddr") or entry.get("ip")) if isinstance(entry, dict) else entry
                if addr:
                    addresses.append(str(addr))
            if row.get("addr4"):
                addresses.append(str(row["addr4"]))

            seen_cidrs = set()
            for addr in addresses:
                try:
                    if "/" in addr:
                        iface = ipaddress.ip_interface(addr)
                        ip, cidr = str(iface.ip), str(iface.network)
                    else:
                        ip = cidr = addr
                    ipaddress.IPv4Address(ip)
                except ValueError:
                    continue
                if cidr in seen_cidrs:
                    continue
                seen_cidrs.add(cidr)
                records.append(make_record(
                    ip, hostname=identifier, source=self.name, record_type="subnet",
                    vlan=str(vlan_tag) if vlan_tag else None, notes=descr,
                    metadata={
                        "cidr": cidr,
                        "device": row.get("device"),
                        "description": descr,
                        "status": row.get("status"),
                        "identifier": identifier,
                    },
                ))
        return records

    def _collect_vlans(self, client):
        records = []
        for row in _api_rows(self._post(client, "/api/interfaces/vlan_settings/search_item")):
            tag = row.get("tag") or row.get("vlan")
            parent = row.get("if") or row.get("parent")
            descr = row.get("descr") or row.get("description") or "vlan%s" % tag
            records.append(make_record(
                "", hostname="%s (vlan %s)" % (descr, tag), source=self.name, record_type="vlan",
                vlan=str(tag) if tag else None, notes="parent=%s" % parent,
                metadata={"parent": parent, "tag": tag, "uuid": row.get("uuid")},
            ))
        return records
