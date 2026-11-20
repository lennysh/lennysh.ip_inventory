# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
"""UniFi Network: active clients, known clients, adopted devices."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible.module_utils.basic import env_fallback

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.collectors.base import Collector, connection_spec
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.api_client import ApiError
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.records import make_record, valid_ipv4


def _client_ip(row):
    for key in ("ip", "fixed_ip", "last_ip", "last_uplink_ip"):
        ip = valid_ipv4(row.get(key))
        if ip:
            return ip
    return None


def _client_hostname(row):
    for key in ("hostname", "name", "host_name"):
        value = row.get(key)
        if value and str(value).strip():
            return str(value).strip()
    return None


def _api_rows(data):
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return [row for row in data["data"] if isinstance(row, dict)]
    return []


class UnifiCollector(Collector):
    name = "unifi"
    argument_spec = dict(
        connection_spec("UNIFI"),
        site={"type": "str", "default": "default"},
        unifi_os={"type": "bool", "default": True},
        api_key={"type": "str", "no_log": True, "fallback": (env_fallback, ["UNIFI_API_KEY"])},
        username={"type": "str", "aliases": ["user"], "fallback": (env_fallback, ["UNIFI_USERNAME"])},
        password={"type": "str", "no_log": True, "fallback": (env_fallback, ["UNIFI_PASSWORD"])},
        collect={
            "type": "dict",
            "default": {},
            "apply_defaults": True,
            "options": {
                "active_clients": {"type": "bool", "default": True},
                "known_clients": {"type": "bool", "default": True},
                "devices": {"type": "bool", "default": True},
            },
        },
    )

    @property
    def site(self):
        return self.params.get("site") or "default"

    def _api_base(self):
        prefix = "/proxy/network" if self.params.get("unifi_os", True) else ""
        return "%s/api/s/%s" % (prefix, self.site)

    def _login(self, client):
        if self.params.get("api_key"):
            return
        username, password = self.params.get("username"), self.params.get("password")
        if not username or not password:
            raise ApiError("UniFi requires api_key or username/password")
        for path in ("/api/auth/login", "/api/login"):
            status, data = client.request("POST", path, json_body={"username": username, "password": password}, allow_status=(404,))
            if status == 404:
                continue
            if isinstance(data, dict) and data.get("error"):
                raise ApiError((data["error"] or {}).get("message") or "UniFi login failed")
            return
        raise ApiError("UniFi login failed")

    def _get(self, client, path):
        payload = client.get("%s/%s" % (self._api_base(), path))
        if isinstance(payload, dict):
            meta = payload.get("meta") or {}
            if meta.get("rc") == "error":
                raise ApiError(meta.get("msg") or "UniFi API error")
            error = payload.get("error")
            if error:
                raise ApiError((error.get("message") if isinstance(error, dict) else str(error)) or "UniFi API error")
        return _api_rows(payload)

    def collect(self):
        headers = {"Accept": "application/json"}
        if self.params.get("api_key"):
            headers["X-API-KEY"] = self.params["api_key"]
        client = self.client(headers=headers)
        self._login(client)
        opts = self.collect_opts
        records = []
        if opts.get("active_clients", True):
            records.extend(self._collect_active_clients(client))
        if opts.get("known_clients", True):
            records.extend(self._collect_known_clients(client))
        if opts.get("devices", True):
            records.extend(self._collect_devices(client))
        return records

    def _collect_active_clients(self, client):
        records = []
        for row in self._get(client, "stat/sta"):
            ip = _client_ip(row)
            if not ip:
                continue
            records.append(make_record(
                ip, hostname=_client_hostname(row), source=self.name, record_type="client_active", mac=row.get("mac"),
                vlan=str(row["vlan"]) if row.get("vlan") is not None else None, notes=self._client_notes(row, active=True),
                metadata={
                    "site": self.site,
                    "is_wired": row.get("is_wired"),
                    "essid": row.get("essid"),
                    "network": row.get("network"),
                    "oui": row.get("oui"),
                },
            ))
        return records

    def _collect_known_clients(self, client):
        records = []
        try:
            rows = self._get(client, "rest/user")
        except ApiError:
            return records
        for row in rows:
            ip = _client_ip(row)
            if not ip:
                continue
            records.append(make_record(
                ip, hostname=_client_hostname(row), source=self.name, record_type="client_known", mac=row.get("mac"),
                notes=self._client_notes(row, active=False),
                metadata={"site": self.site, "use_fixedip": row.get("use_fixedip"), "blocked": row.get("blocked"), "note": row.get("note")},
            ))
        return records

    def _collect_devices(self, client):
        records = []
        for row in self._get(client, "stat/device"):
            ip = valid_ipv4(row.get("ip"))
            if not ip:
                continue
            records.append(make_record(
                ip, hostname=row.get("name"), source=self.name, record_type="device", mac=row.get("mac"),
                notes=self._device_notes(row),
                metadata={"site": self.site, "model": row.get("model"), "type": row.get("type"), "version": row.get("version"), "state": row.get("state")},
            ))
        return records

    @staticmethod
    def _client_notes(row, active):
        parts = []
        if active:
            parts.append("active")
        if row.get("is_wired"):
            parts.append("wired")
        elif row.get("essid"):
            parts.append("ssid=%s" % row["essid"])
        if row.get("network"):
            parts.append("network=%s" % row["network"])
        if row.get("note"):
            parts.append(str(row["note"]))
        return "; ".join(parts) or None

    @staticmethod
    def _device_notes(row):
        parts = []
        if row.get("type"):
            parts.append(str(row["type"]))
        if row.get("model"):
            parts.append(str(row["model"]))
        if row.get("version"):
            parts.append("v%s" % row["version"])
        return "; ".join(parts) or None
