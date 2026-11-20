# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import os

import pytest

from ansible.inventory.data import InventoryData
from ansible.parsing.dataloader import DataLoader
from ansible.plugins.loader import init_plugin_loader, inventory_loader
from ansible.template import Templar

try:  # ansible-core >= 2.19: config files are loaded as trusted templates; mimic that here
    from ansible.template import trust_as_template
except ImportError:  # pragma: no cover
    def trust_as_template(value):
        return value

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.pipeline import run_pipeline
from ansible_collections.lennysh.ip_inventory.tests.unit.fake_api import make_factory

SOURCES = {
    "opnsense": {"url": "https://opn.test", "api_key": "k", "api_secret": "s"},
    "technitium": {"url": "http://tech.test", "token": "t"},
    "proxmox": {"url": "https://pve.test", "token_id": "a@pam!b", "token_secret": "x"},
    "unifi": {"url": "https://unifi.test", "api_key": "u"},
}
FILTERS = {"include_networks": ["192.168.*"], "exclude_interfaces": ["lo0", "wan"], "exclude_name_patterns": ["*docker*"]}


@pytest.fixture
def pipeline_data():
    return run_pipeline({"sources": SOURCES, "filters": FILTERS}, client_factory=make_factory(*SOURCES))


def load_plugin():
    """Load through the plugin loader so the documented options are registered."""
    plugin = inventory_loader.get("lennysh.ip_inventory.ip_inventory")
    if plugin is None:
        import ansible_collections.lennysh.ip_inventory as collection_pkg
        # <root>/ansible_collections/lennysh/ip_inventory -> <root>
        root = os.path.dirname(os.path.dirname(os.path.dirname(list(collection_pkg.__path__)[0])))
        init_plugin_loader([root])
        plugin = inventory_loader.get("lennysh.ip_inventory.ip_inventory")
    return plugin


def make_plugin(**options):
    plugin = load_plugin()
    plugin.inventory = InventoryData()
    plugin.loader = DataLoader()
    plugin.templar = Templar(loader=plugin.loader)
    direct = {"plugin": "lennysh.ip_inventory.ip_inventory", "sources": SOURCES}
    direct.update(options)
    plugin.set_options(direct=direct)
    return plugin


def groups_of(plugin, host):
    return sorted(g.name for g in plugin.inventory.get_host(host).get_groups())


def test_verify_file(tmp_path):
    good = tmp_path / "lab.ip_inventory.yml"
    good.write_text(u"plugin: lennysh.ip_inventory.ip_inventory\n")
    bad = tmp_path / "hosts.yml"
    bad.write_text(u"all: {}\n")
    plugin = load_plugin()
    assert plugin.verify_file(str(good))
    assert not plugin.verify_file(str(bad))


def test_populate_hosts_vars_and_groups(pipeline_data):
    plugin = make_plugin()
    plugin._populate(pipeline_data)
    inv = plugin.inventory
    assert "nas.lab.example" in inv.hosts and "web01" in inv.hosts
    assert "192.168.1.1" in inv.hosts                        # no hostname -> IP
    assert "192.168.20.31" in inv.hosts                      # multi.lab.example conflict -> IP
    assert "192.168.20.31" in [h.name for h in inv.groups["name_conflict"].get_hosts()]

    web = inv.get_host("web01").get_vars()
    assert web["ansible_host"] == "192.168.1.50"
    assert web["ip_inventory_proxmox_vmid"] == 100 and web["ip_inventory_proxmox_tags"] == ["web", "prod"]
    assert web["ip_inventory_subnet"] == "192.168.1.0/24"
    assert set(["source_proxmox", "proxmox_qemu", "proxmox_node_pve1", "proxmox_tag_prod", "subnet_192_168_1_0_24",
                "interface_lan"]) <= set(groups_of(plugin, "web01"))

    nas = groups_of(plugin, "nas.lab.example")
    assert "issue_mac_conflict" in nas and "issues_high" in nas and "unifi_wired" in nas
    assert "vlan_iot" in groups_of(plugin, "phone") and "unifi_wireless" in groups_of(plugin, "phone")
    assert inv.groups["vlan_iot"].get_vars()["ip_inventory_subnet_gateway"] == "192.168.20.1"
    assert "ip_inventory_findings" not in inv.groups["all"].get_vars()      # global_vars off by default


def test_hostname_strategies_prefix_and_global_vars(pipeline_data):
    plugin = make_plugin(hostname_strategy="short_hostname", group_prefix="lab_", vars_prefix="inv_", global_vars=True)
    plugin._populate(pipeline_data)
    inv = plugin.inventory
    assert "nas" in inv.hosts and "lab_source_proxmox" in inv.groups
    assert inv.get_host("nas").get_vars()["inv_ip"] == "192.168.1.10"
    assert inv.groups["all"].get_vars()["inv_issue_summary"]["total"] == len(pipeline_data["findings"])

    plugin = make_plugin(hostname_strategy="ip", builtin_groups=False)
    plugin._populate(pipeline_data)
    assert all(name[0].isdigit() for name in plugin.inventory.hosts)
    assert sorted(plugin.inventory.groups) == ["all", "ungrouped"]


def test_constructed_options(pipeline_data):
    plugin = make_plugin(
        compose={"is_vm": trust_as_template("'proxmox' in ip_inventory_sources")},
        groups={"stale_dns": trust_as_template("ip_inventory_dns_only")},
        keyed_groups=[{"key": trust_as_template("ip_inventory_record_types"), "prefix": "seen"}],
    )
    plugin._populate(pipeline_data)
    inv = plugin.inventory
    assert inv.get_host("web01").get_vars()["is_vm"] is True
    assert "old.lab.example" in [h.name for h in inv.groups["stale_dns"].get_hosts()]
    assert "web01" in [h.name for h in inv.groups["seen_vm_guest_agent"].get_hosts()]


def test_option_resolution(monkeypatch):
    monkeypatch.setenv("IPINV_TEST_SECRET", "s3cret")
    plugin = make_plugin(sources={"opnsense": {"url": "https://x", "api_key": trust_as_template("{{ 'k' ~ 1 }}"), "api_secret": "${IPINV_TEST_SECRET}"}})
    cfg = plugin._pipeline_config()
    assert cfg["sources"]["opnsense"]["api_key"] == "k1"
    assert cfg["sources"]["opnsense"]["api_secret"] == "s3cret"


def test_name_conflicts_prefer_live_evidence():
    plugin = make_plugin(hostname_strategy="short_hostname")

    def host(ip, types, dns_only=False):
        return {"ip": ip, "hostname": "iphone.lab", "record_type": types[0],
                "metadata": {"all_record_types": types, "dns_only": dns_only}}

    names, conflicts = plugin._host_names([
        host("10.0.0.4", ["dns_a"], dns_only=True),
        host("10.0.0.5", ["dhcp_dynamic"]),
        host("10.0.0.9", ["arp", "client_active", "dhcp_dynamic"]),
    ])
    assert names["10.0.0.9"] == "iphone"
    assert conflicts == {"10.0.0.4", "10.0.0.5"}
