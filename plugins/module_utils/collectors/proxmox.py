# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Proxmox VE: QEMU guest-agent IPs, LXC runtime IPs, static IPs from guest config."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import ipaddress
import re

from ansible.module_utils.basic import env_fallback

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.collectors.base import Collector, connection_spec
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.api_client import ApiError
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.records import make_record

_IP_RE = re.compile(r"(\d{1,3}\.){3}\d{1,3}")
_MAC_RE = re.compile(r"([0-9A-Fa-f:]{11,17})")
_CONFIG_IP_RE = re.compile(r"ip=(\d{1,3}(?:\.\d{1,3}){3}/\d+)")


def _agent_interfaces(data):
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        result = data.get("result") or data.get("results")
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
    return []


class ProxmoxCollector(Collector):
    name = "proxmox"
    argument_spec = dict(
        connection_spec("PROXMOX"),
        token_id={"type": "str", "required": True, "fallback": (env_fallback, ["PROXMOX_TOKEN_ID"])},
        token_secret={"type": "str", "required": True, "no_log": True, "fallback": (env_fallback, ["PROXMOX_TOKEN_SECRET"])},
        use_guest_agent={"type": "bool", "default": True},
    )

    def _get(self, client, path, params=None):
        payload = client.get(path, params=params) or {}
        if payload.get("errors"):
            raise ApiError(str(payload["errors"]))
        return payload.get("data")

    def collect(self):
        client = self.client(
            base_url=self.params["url"].rstrip("/") + "/api2/json",
            headers={"Authorization": "PVEAPIToken=%s=%s" % (self.params["token_id"], self.params["token_secret"])},
        )
        records = []
        resources = self._get(client, "/cluster/resources", {"type": "vm"}) or []
        if not resources:
            if self._get(client, "/nodes"):
                self.warn(
                    "Connected to Proxmox, but the API token cannot see any VMs/containers. "
                    "Grant the token user read access (e.g. role 'PVE Auditor' on path '/' "
                    "or at least 'VM.Audit' + 'VM.Monitor' for guest-agent IPs)."
                )
            return records

        for resource in resources:
            if not isinstance(resource, dict) or resource.get("template"):
                continue
            vmid, node, name, vm_type = resource.get("vmid"), resource.get("node"), resource.get("name"), resource.get("type")
            if not vmid or not node:
                continue
            base = {"vmid": vmid, "node": node, "vm_type": vm_type, "status": resource.get("status")}
            if resource.get("tags"):
                base["tags"] = [t for t in re.split(r"[;, ]+", str(resource["tags"])) if t]
            if vm_type == "qemu" and self.params.get("use_guest_agent", True) and resource.get("status") == "running":
                records.extend(self._collect_qemu_ips(client, node, vmid, name, base))
            elif vm_type == "lxc":
                records.extend(self._collect_lxc_ips(client, node, vmid, name, base))
            records.extend(self._collect_config_ips(client, node, vmid, name, vm_type, base))
        return records

    def _collect_qemu_ips(self, client, node, vmid, name, base):
        records = []
        try:
            interfaces = _agent_interfaces(self._get(client, "/nodes/%s/qemu/%s/agent/network-get-interfaces" % (node, vmid)))
        except ApiError:
            return records
        for iface in interfaces:
            if iface.get("name") in ("lo", "docker0"):
                continue
            for addr in iface.get("ip-addresses") or []:
                if not isinstance(addr, dict) or str(addr.get("ip-address-type")).lower() not in ("ipv4", "inet", "v4"):
                    continue
                ip = addr.get("ip-address")
                if not ip or ip.startswith("127."):
                    continue
                records.append(make_record(
                    ip, hostname=name, source=self.name, record_type="vm_guest_agent", mac=iface.get("hardware-address"),
                    notes="vmid=%s node=%s iface=%s" % (vmid, node, iface.get("name")), metadata=dict(base, vm_type="qemu"),
                ))
        return records

    def _collect_lxc_ips(self, client, node, vmid, name, base):
        records = []
        try:
            interfaces = self._get(client, "/nodes/%s/lxc/%s/interfaces" % (node, vmid))
        except ApiError:
            interfaces = None
        for iface in interfaces or []:
            if not isinstance(iface, dict) or iface.get("name") == "lo":
                continue
            match = _IP_RE.search(iface.get("inet") or "")
            if not match:
                continue
            records.append(make_record(
                match.group(0), hostname=name, source=self.name, record_type="lxc_runtime", mac=iface.get("hwaddr"),
                notes="vmid=%s node=%s iface=%s" % (vmid, node, iface.get("name")), metadata=dict(base, vm_type="lxc"),
            ))
        return records

    def _collect_config_ips(self, client, node, vmid, name, vm_type, base):
        records = []
        try:
            config = self._get(client, "/nodes/%s/%s/%s/config" % (node, vm_type, vmid)) or {}
        except ApiError:
            return records
        for key, value in config.items():
            if not key.startswith("net") or not isinstance(value, str):
                continue
            ip_match = _CONFIG_IP_RE.search(value)
            if not ip_match:
                continue
            ip = ip_match.group(1).split("/")[0]
            try:
                ipaddress.IPv4Address(ip)
            except ipaddress.AddressValueError:
                continue
            mac_match = _MAC_RE.search(value)
            records.append(make_record(
                ip, hostname=name, source=self.name, record_type="%s_config_static" % vm_type,
                mac=mac_match.group(1) if mac_match else None,
                notes="vmid=%s node=%s %s=%s" % (vmid, node, key, value), metadata=dict(base, config_key=key),
            ))
        return records
