# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
name: ip_inventory
short_description: Build an Ansible inventory from OPNsense, Technitium, Proxmox and UniFi data
version_added: 1.0.0
author: Lenny Shirley (@lennysh)
description:
  - Collects IP observations from the configured sources, merges them into one host per IP,
    enriches each host with subnet/VLAN data, optionally pings them and sweeps subnets for
    unknown devices, runs the issue checks, and exposes the result as inventory.
  - Uses the same collectors and processing code as the C(lennysh.ip_inventory) modules, filters and roles.
  - Hosts get C(ansible_host) set to their IP and all inventory data under O(vars_prefix) host variables.
  - "Built-in groups (prefixed with O(group_prefix)): C(source_<name>), C(type_<record_type>),
    C(subnet_<cidr>), C(vlan_<name>), C(interface_<name>), C(ping_up), C(ping_down), C(dns_only),
    C(discovered), C(issue_<category>), C(issues_<severity>), C(proxmox_qemu), C(proxmox_lxc),
    C(proxmox_node_<node>), C(proxmox_tag_<tag>), C(unifi_device), C(unifi_client), C(unifi_wired),
    C(unifi_wireless), C(name_conflict)."
  - Subnet and VLAN groups carry C(<vars_prefix>subnet_*) group variables (cidr, netmask, gateway, broadcast,
    interface, vlan tag/name/parent), so every member host can read for example C(ip_inventory_subnet_gateway).
  - With O(global_vars) the C(all) group also gets the run-wide subnets, findings and stats.
  - String values in O(sources) and O(filters) may contain Jinja2 (for example C(lookup('env', ...)))
    or C(${VAR}) environment references; inline vault values work too. Collector secrets also fall back
    to their usual environment variables (E(OPNSENSE_API_KEY), E(TECHNITIUM_TOKEN), E(PROXMOX_TOKEN_SECRET), ...).
extends_documentation_fragment:
  - ansible.builtin.constructed
  - ansible.builtin.inventory_cache
options:
  plugin:
    description: Marks this as an instance of the C(ip_inventory) plugin.
    required: true
    choices: [lennysh.ip_inventory.ip_inventory]
  sources:
    description:
      - Mapping of source name (C(opnsense), C(technitium), C(proxmox), C(unifi)) to its options.
      - Options are the same as the matching C(lennysh.ip_inventory.<source>_info) module,
        plus C(enabled) (default V(true)) and C(filters) (per-source include/exclude rules).
    type: dict
    required: true
  filters:
    description:
      - Global include/exclude rules applied to every source.
      - "Keys: C(include_networks), C(exclude_networks), C(exclude_interfaces), C(exclude_name_patterns), C(exclude_record_types)."
    type: dict
    default: {}
  ignore_source_errors:
    description:
      - Warn and build the inventory from the remaining sources when a source fails,
        instead of failing the whole inventory source.
    type: bool
    default: false
  ping:
    description:
      - ICMP ping every host while building the inventory (sets C(ping_status) and the C(ping_up)/C(ping_down) groups).
      - Pings are sent from the controller and slow down inventory parsing; consider enabling O(cache).
    type: bool
    default: false
  ping_timeout:
    description: Seconds to wait for each ping reply.
    type: float
    default: 1.0
  ping_concurrency:
    description: Parallel pings.
    type: int
    default: 50
  discover_unknown:
    description: Sweep unused addresses in collected subnets and add responders as C(discovered) hosts.
    type: bool
    default: false
  discover_private_only:
    description: Only sweep private and link-local subnets.
    type: bool
    default: true
  discover_max_hosts_per_subnet:
    description: Skip subnets with more usable addresses than this.
    type: int
    default: 512
  analyze_issues:
    description: Run the issue checks and create C(issue_*) groups and the C(<vars_prefix>issues) host variable.
    type: bool
    default: true
  issue_skip_checks:
    description: Issue checks to skip (for example C(cname_aliases)).
    type: list
    elements: str
    default: []
  hostname_strategy:
    description:
      - How to name inventory hosts.
      - V(hostname) uses the primary hostname (usually the FQDN), V(short_hostname) its first label,
        V(ip) the IP address. Hosts without a hostname always use their IP.
      - When two IPs share a name, the IP with the strongest evidence keeps it (not DNS-only, then seen live
        by ARP/UniFi/Proxmox, then lowest IP); the others are named by IP and added to the C(name_conflict) group.
    type: str
    choices: [hostname, short_hostname, ip]
    default: hostname
  group_prefix:
    description: Prefix for every built-in group name.
    type: str
    default: ""
  vars_prefix:
    description: Prefix for every host and group variable set by this plugin.
    type: str
    default: ip_inventory_
  global_vars:
    description:
      - Set run-wide data on the C(all) group, C(<vars_prefix>subnets), C(<vars_prefix>orphan_vlans), C(<vars_prefix>findings),
        C(<vars_prefix>issue_summary), C(<vars_prefix>source_stats) and C(<vars_prefix>generated_at),
        so playbooks (for example the C(report) role) can use them.
      - Off by default because C(ansible-inventory --list) copies C(all) group vars into every host.
    type: bool
    default: false
  builtin_groups:
    description: Create the built-in groups. Set V(false) to rely only on O(groups) and O(keyed_groups).
    type: bool
    default: true
"""

EXAMPLES = r"""
# inventory/homelab.ip_inventory.yml
plugin: lennysh.ip_inventory.ip_inventory
sources:
  opnsense:
    url: https://opnsense.example.com
    api_key: "{{ lookup('ansible.builtin.env', 'OPNSENSE_API_KEY') }}"
    api_secret: ${OPNSENSE_API_SECRET}
  technitium:
    url: http://technitium.example.com:5380
    # token falls back to $TECHNITIUM_TOKEN
  proxmox:
    url: https://proxmox.example.com:8006
    token_id: ip-inventory@pam!inventory
  unifi:
    enabled: false
    url: https://unifi.example.com
filters:
  include_networks: [192.168.*]
  exclude_networks: [127.*, 172.17.*]
  exclude_interfaces: [lo0, wan]
  exclude_name_patterns: ["*docker*"]
hostname_strategy: short_hostname
cache: true
cache_plugin: ansible.builtin.jsonfile
cache_connection: ~/.cache/ansible-ip-inventory
cache_timeout: 900
# Constructable extras
compose:
  is_vm: "'proxmox' in ip_inventory_sources"
keyed_groups:
  - key: ip_inventory_record_types
    prefix: seen_as
groups:
  stale_dns: ip_inventory_dns_only and ip_inventory_ping_status | default('') != 'up'
"""

import os
import re
import shutil
import subprocess
from datetime import datetime, timezone

from ansible.errors import AnsibleParserError
from ansible.module_utils.common.text.converters import to_native
from ansible.plugins.inventory import BaseInventoryPlugin, Cacheable, Constructable

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.issues import findings_by_ip, summarize_findings
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.ping import ping_many
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.pipeline import PipelineError, run_pipeline
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.records import ACTIVE_RECORD_TYPES, ip_sort_key, meta

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")
_UNSAFE_GROUP_CHARS = re.compile(r"[^A-Za-z0-9_]")


def _run_quietly(argv):
    """Run a command on the controller, discarding output; return its exit code."""
    return subprocess.call(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _controller_ping(ips, timeout_seconds=1.0, concurrency=50):
    ping_bin = shutil.which("ping")
    if not ping_bin:
        raise PipelineError("ping is enabled but no 'ping' binary was found on the controller")
    return ping_many(ips, _run_quietly, timeout_seconds=timeout_seconds, concurrency=concurrency, ping_command=ping_bin)


def _expand_env(node):
    if isinstance(node, dict):
        return dict((k, _expand_env(v)) for k, v in node.items())
    if isinstance(node, list):
        return [_expand_env(v) for v in node]
    if isinstance(node, str):
        return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1), ""), str(node))
    return node


class InventoryModule(BaseInventoryPlugin, Constructable, Cacheable):

    NAME = "lennysh.ip_inventory.ip_inventory"

    def verify_file(self, path):
        if super(InventoryModule, self).verify_file(path):
            return path.endswith(("ip_inventory.yml", "ip_inventory.yaml"))
        return False

    # ----------------------------------------------------------------- config
    def _resolve(self, value):
        """Render Jinja2 (when present), then expand ${VAR} references."""
        if self.templar is not None:
            try:
                value = self.templar.template(value)
            except Exception as exc:
                raise AnsibleParserError("Failed to template ip_inventory options: %s" % to_native(exc))
        return _expand_env(value)

    def _pipeline_config(self):
        sources = self._resolve(self.get_option("sources") or {})
        if not isinstance(sources, dict) or not sources:
            raise AnsibleParserError("ip_inventory: 'sources' must be a non-empty mapping")
        return {
            "sources": dict((name, dict(cfg or {})) for name, cfg in sources.items()),
            "filters": self._resolve(self.get_option("filters") or {}),
            "ignore_source_errors": self.get_option("ignore_source_errors"),
            "ping": {
                "enabled": self.get_option("ping"),
                "timeout_seconds": self.get_option("ping_timeout"),
                "concurrency": self.get_option("ping_concurrency"),
                "discover_unknown": self.get_option("discover_unknown"),
                "discover_private_only": self.get_option("discover_private_only"),
                "discover_max_hosts_per_subnet": self.get_option("discover_max_hosts_per_subnet"),
            },
            "issues": {
                "enabled": self.get_option("analyze_issues"),
                "skip_checks": self.get_option("issue_skip_checks"),
            },
        }

    # ------------------------------------------------------------------ parse
    def parse(self, inventory, loader, path, cache=True):
        super(InventoryModule, self).parse(inventory, loader, path, cache)
        self._read_config_data(path)

        cache_key = self.get_cache_key(path)
        use_cache = self.get_option("cache")
        data = None
        update_cache = False
        if use_cache and cache:
            try:
                data = self._cache[cache_key]
            except KeyError:
                update_cache = True
        elif use_cache:
            update_cache = True

        if data is None:
            data = self._collect()
        if update_cache:
            self._cache[cache_key] = data

        self._populate(data)

    def _collect(self):
        try:
            result = run_pipeline(self._pipeline_config(), ping_func=_controller_ping)
        except PipelineError as exc:
            raise AnsibleParserError("ip_inventory: %s" % to_native(exc))
        for warning in result["warnings"]:
            self.display.warning("ip_inventory: %s" % warning)
        result["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        return result

    # --------------------------------------------------------------- populate
    def _group(self, *parts):
        """Create (if needed) a sanitized, prefixed group and return its name."""
        raw = "_".join(str(p) for p in parts if p not in (None, ""))
        name = _UNSAFE_GROUP_CHARS.sub("_", self.get_option("group_prefix") + raw).strip("_").lower()
        name = re.sub(r"_+", "_", name)
        if name and name[0].isdigit():
            name = "_" + name
        return self.inventory.add_group(name)

    def _host_names(self, hosts):
        """Choose an inventory name for every host IP, resolving name collisions."""
        strategy = self.get_option("hostname_strategy")

        def candidate(record):
            hostname = record.get("hostname")
            if strategy == "ip" or not hostname:
                return record["ip"]
            hostname = str(hostname).rstrip(".").lower()
            return hostname.split(".", 1)[0] if strategy == "short_hostname" else hostname

        # Strongest evidence first: not DNS-only, not a sweep discovery, seen live (ARP/UniFi/VM), then IP order.
        ordered = sorted(
            hosts,
            key=lambda r: (
                bool(meta(r).get("dns_only")),
                r.get("record_type") == "discovered",
                not (set(meta(r).get("all_record_types") or []) & ACTIVE_RECORD_TYPES),
                ip_sort_key(r["ip"]),
            ),
        )
        names, used, conflicts = {}, set(), set()
        for record in ordered:
            name = candidate(record)
            if name in used:
                conflicts.add(record["ip"])
                name = record["ip"]
            used.add(name)
            names[record["ip"]] = name
        return names, conflicts

    def _populate(self, data):
        prefix = self.get_option("vars_prefix")
        builtin = self.get_option("builtin_groups")
        strict = self.get_option("strict")
        hosts = [h for h in data["hosts"] if h.get("ip") and h.get("record_type") not in ("subnet", "vlan")]
        issues_by_ip = findings_by_ip(data["findings"])
        names, conflicts = self._host_names(hosts)

        all_vars = {
            "subnets": data["subnets"],
            "orphan_vlans": data["orphan_vlans"],
            "findings": data["findings"],
            "issue_summary": summarize_findings(data["findings"]),
            "source_stats": data["stats"],
            "generated_at": data.get("generated_at"),
        }
        if self.get_option("global_vars"):
            for key, value in all_vars.items():
                self.inventory.set_variable("all", prefix + key, value)

        subnet_groups = self._subnet_groups(data["subnets"], prefix) if builtin else {}

        for record in hosts:
            ip = record["ip"]
            host = names[ip]
            self.inventory.add_host(host)
            hostvars = self._host_vars(record, issues_by_ip.get(ip, []), ip in conflicts, prefix)
            for key, value in hostvars.items():
                self.inventory.set_variable(host, key, value)
            if builtin:
                for group in self._builtin_groups_for(record, issues_by_ip.get(ip, []), ip in conflicts, data["findings"], subnet_groups):
                    self.inventory.add_child(group, host)

            combined = self.inventory.get_host(host).get_vars()
            self._set_composite_vars(self.get_option("compose"), combined, host, strict=strict)
            combined = self.inventory.get_host(host).get_vars()
            self._add_host_to_composed_groups(self.get_option("groups"), combined, host, strict=strict)
            self._add_host_to_keyed_groups(self.get_option("keyed_groups"), combined, host, strict=strict)

    def _subnet_groups(self, subnets, prefix):
        """Create subnet/VLAN groups with group vars; return {cidr: [group names]}."""
        mapping = {}
        for subnet in subnets:
            smeta = meta(subnet)
            cidr = smeta.get("cidr")
            if not cidr:
                continue
            group_vars = {
                "cidr": cidr,
                "netmask": smeta.get("netmask"),
                "prefix_length": smeta.get("prefix_length"),
                "broadcast": smeta.get("broadcast"),
                "gateway": subnet.get("ip"),
                "interface": subnet.get("hostname"),
                "interface_description": subnet.get("notes"),
                "vlan": subnet.get("vlan"),
                "vlan_name": smeta.get("vlan_name"),
                "vlan_parent": smeta.get("vlan_parent"),
            }
            groups = [self._group("subnet", cidr)]
            vlan_label = smeta.get("vlan_name") or (("vlan%s" % subnet["vlan"]) if subnet.get("vlan") else None)
            if vlan_label:
                groups.append(self._group("vlan", vlan_label))
            for group in groups:
                for key, value in group_vars.items():
                    if value is not None:
                        self.inventory.set_variable(group, prefix + "subnet_" + key, value)
            mapping[cidr] = groups
        return mapping

    @staticmethod
    def _host_vars(record, issues, conflict, prefix):
        m = meta(record)
        src_meta = m.get("source_metadata") or {}
        hostvars = {
            "ansible_host": record["ip"],
            "ip": record["ip"],
            "hostname": record.get("hostname"),
            "hostnames": m.get("all_hostnames") or ([record["hostname"]] if record.get("hostname") else []),
            "dns_names": m.get("dns_names") or [],
            "cname_aliases": m.get("cname_aliases") or [],
            "dns_only": bool(m.get("dns_only")),
            "mac": record.get("mac"),
            "macs": m.get("all_macs") or ([record["mac"]] if record.get("mac") else []),
            "sources": m.get("all_sources") or [record.get("source")],
            "record_types": m.get("all_record_types") or [record.get("record_type")],
            "vlan": record.get("vlan"),
            "vlan_name": m.get("vlan_name"),
            "subnet": m.get("subnet"),
            "netmask": m.get("netmask"),
            "prefix_length": m.get("prefix_length"),
            "interface": m.get("interface"),
            "interface_description": m.get("interface_description"),
            "ping_status": record.get("ping_status"),
            "notes": record.get("notes"),
            "issues": issues,
            "name_conflict": conflict,
            "source_metadata": src_meta,
        }
        proxmox = src_meta.get("proxmox")
        if proxmox:
            for key in ("vmid", "node", "vm_type", "status", "tags"):
                if key in proxmox:
                    hostvars["proxmox_" + key] = proxmox[key]
        unifi = src_meta.get("unifi")
        if unifi:
            for key in ("model", "type", "version", "essid", "network", "is_wired", "oui"):
                if unifi.get(key) is not None:
                    hostvars["unifi_" + key] = unifi[key]
        out = {"ansible_host": hostvars.pop("ansible_host")}
        out.update((prefix + key, value) for key, value in hostvars.items())
        return out

    def _builtin_groups_for(self, record, issues, conflict, findings, subnet_groups):
        m = meta(record)
        groups = []
        for source in m.get("all_sources") or [record.get("source")]:
            groups.append(self._group("source", source))
        for rtype in m.get("all_record_types") or [record.get("record_type")]:
            groups.append(self._group("type", rtype))
        if m.get("subnet") in subnet_groups:
            groups.extend(subnet_groups[m["subnet"]])
        elif m.get("subnet"):
            groups.append(self._group("subnet", m["subnet"]))
        if m.get("interface"):
            groups.append(self._group("interface", m["interface"]))
        if record.get("ping_status") in ("up", "down"):
            groups.append(self._group("ping", record["ping_status"]))
        if m.get("dns_only"):
            groups.append(self._group("dns_only"))
        if "discovered" in (m.get("all_record_types") or []):
            groups.append(self._group("discovered"))
        for category in issues:
            groups.append(self._group("issue", category))
        for severity in sorted(set(f["severity"] for f in findings if record["ip"] in f.get("ips", []))):
            groups.append(self._group("issues", severity))
        if conflict:
            groups.append(self._group("name_conflict"))

        src_meta = m.get("source_metadata") or {}
        proxmox = src_meta.get("proxmox")
        if proxmox:
            if proxmox.get("vm_type"):
                groups.append(self._group("proxmox", proxmox["vm_type"]))
            if proxmox.get("node"):
                groups.append(self._group("proxmox_node", proxmox["node"]))
            for tag in proxmox.get("tags") or []:
                groups.append(self._group("proxmox_tag", tag))
        unifi = src_meta.get("unifi")
        if unifi:
            unifi_types = unifi.get("record_types") or []
            if "device" in unifi_types:
                groups.append(self._group("unifi_device"))
            if "client_active" in unifi_types or "client_known" in unifi_types:
                groups.append(self._group("unifi_client"))
                if unifi.get("is_wired") is True:
                    groups.append(self._group("unifi_wired"))
                elif unifi.get("essid"):
                    groups.append(self._group("unifi_wireless"))
        return groups
