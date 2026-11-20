# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.collectors.registry import COLLECTORS, get_collector
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.api_client import ApiError
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.pipeline import validate_source_params
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.records import RECORD_KEYS
from ansible_collections.lennysh.ip_inventory.tests.unit.fake_api import load_api_fixture

PARAMS = {
    "opnsense": {"url": "https://opn.test", "api_key": "k", "api_secret": "s"},
    "technitium": {"url": "http://tech.test:5380", "token": "t"},
    "proxmox": {"url": "https://pve.test:8006", "token_id": "a@pam!b", "token_secret": "x"},
    "unifi": {"url": "https://unifi.test", "api_key": "u"},
}


def collect(name, client_factory, **overrides):
    params = dict(PARAMS[name], **overrides)
    collector = get_collector(name)(validate_source_params(name, params), client_factory=client_factory)
    return collector, collector.collect()


def by_type(records):
    out = {}
    for record in records:
        out.setdefault(record["record_type"], []).append(record)
    return out


@pytest.mark.parametrize("name", sorted(PARAMS))
def test_records_follow_schema(fake_api, name):
    _collector, records = collect(name, fake_api(name))
    assert records
    for record in records:
        assert set(record) == set(RECORD_KEYS)
        assert record["source"] == name
        assert isinstance(record["metadata"], dict)


def test_registry_lists_all_sources():
    assert sorted(COLLECTORS) == ["opnsense", "proxmox", "technitium", "unifi"]
    with pytest.raises(KeyError, match="Unknown source"):
        get_collector("netbox")


def test_opnsense(fake_api):
    factory = fake_api("opnsense")
    _c, records = collect("opnsense", factory)
    types = by_type(records)
    assert sorted(types) == ["arp", "subnet", "vlan"]
    subnets = dict((r["metadata"]["cidr"], r) for r in types["subnet"])
    assert subnets["192.168.20.0/24"]["vlan"] == "20"
    assert subnets["192.168.30.0/24"]["vlan"] == "30"   # vlan dict + addr4 form
    assert "not-an-ip" not in [r["ip"] for r in types["arp"]]
    assert types["vlan"][0]["hostname"] == "IoT (vlan 20)"
    client = factory.instances[0]
    assert client.force_basic_auth and client.url_username == "k" and client.url_password == "s"
    assert client.validate_certs is False


def test_opnsense_optional_datasets_off_by_default(fake_api):
    factory = fake_api("opnsense")
    collect("opnsense", factory)
    assert not [c for c in factory.calls if "dhcp" in c or "unbound" in c]


def test_opnsense_kea_falls_back_to_isc(fake_api):
    factory = fake_api("opnsense", **{
        "GET /api/dhcpv4/leases/search_lease": {"rows": [{"address": "192.168.1.77", "mac": "aa:aa:aa:aa:aa:aa", "hostname": "isc"}]},
    })
    _c, records = collect("opnsense", factory, collect={"dhcp_leases": True, "arp_table": False, "interfaces": False, "vlans": False})
    assert [(r["ip"], r["metadata"]["backend"]) for r in records] == [("192.168.1.77", "isc")]


def test_technitium(fake_api):
    _c, records = collect("technitium", fake_api("technitium"))
    types = by_type(records)
    cnames = dict((r["hostname"], r) for r in types["dns_cname"])
    # chained CNAME resolves through files -> nas
    assert cnames["www.lab.example"]["ip"] == "192.168.1.10"
    assert cnames["www.lab.example"]["metadata"]["cname_resolved"] == "nas.lab.example"
    # wildcard, unresolvable and looping CNAMEs are skipped
    assert not [n for n in cnames if n.startswith("*") or n.startswith("ext.") or n.startswith("loop")]
    assert sorted(r["ip"] for r in types["dns_ptr"]) == ["192.168.1.10", "192.168.1.99"]
    assert "192.168.1.98" not in [r["ip"] for r in records]           # disabled record
    assert types["dns_aname"][0]["ip"] == "192.168.1.41"
    assert sorted(r["ip"] for r in types["dhcp_reserved"]) == ["192.168.1.10", "192.168.20.60", "192.168.20.70"]
    zones = set(r["metadata"].get("zone") for r in records if r["metadata"].get("zone"))
    assert "corp.example" not in zones and "localhost" not in zones


def test_technitium_login(fake_api):
    factory = fake_api("technitium", **{"POST /api/user/login": {"status": "ok", "token": "sess"}})
    collect("technitium", factory, token=None, user="admin", password="pw")
    assert "POST /api/user/login" in factory.calls
    assert factory.instances[-1].headers["Authorization"] == "Bearer sess"


def test_technitium_requires_credentials(fake_api):
    with pytest.raises(ApiError, match="token or user/password"):
        collect("technitium", fake_api("technitium"), token=None)


def test_proxmox(fake_api):
    collector, records = collect("proxmox", fake_api("proxmox"))
    types = by_type(records)
    assert [r["ip"] for r in types["vm_guest_agent"]] == ["192.168.1.50"]          # lo + ipv6 skipped
    assert types["vm_guest_agent"][0]["metadata"]["tags"] == ["web", "prod"]
    assert [r["ip"] for r in types["lxc_runtime"]] == ["192.168.1.51"]
    assert [r["mac"] for r in types["lxc_config_static"]] == ["BC:24:11:00:01:01"]
    assert "tmpl" not in [r["hostname"] for r in records]                         # template skipped
    assert collector.warnings == []


def test_proxmox_warns_when_token_sees_nothing(fake_api):
    factory = fake_api(**{"GET /api2/json/cluster/resources": {"data": []}, "GET /api2/json/nodes": {"data": [{"node": "pve1"}]}})
    collector, records = collect("proxmox", factory)
    assert records == []
    assert "PVE Auditor" in collector.warnings[0]


def test_unifi(fake_api):
    factory = fake_api("unifi")
    _c, records = collect("unifi", factory)
    types = by_type(records)
    assert [r["ip"] for r in types["client_active"]] == ["192.168.20.80", "192.168.1.10"]
    assert types["client_active"][0]["vlan"] == "20"
    assert sorted(r["ip"] for r in types["client_known"]) == ["192.168.20.81", "192.168.20.82"]
    assert types["device"][0]["notes"] == "usw; US24; v7.1.26"
    assert factory.instances[0].headers["X-API-KEY"] == "u"


def test_unifi_legacy_controller_paths(fake_api):
    routes = dict((k.replace("/proxy/network", ""), v) for k, v in load_api_fixture("unifi").items())
    factory = fake_api(**routes)
    _c, records = collect("unifi", factory, unifi_os=False)
    assert len(records) == 5


def test_unifi_api_error(fake_api):
    factory = fake_api("unifi", **{"GET /proxy/network/api/s/default/stat/sta": {"meta": {"rc": "error", "msg": "api.err.NoSiteContext"}}})
    with pytest.raises(ApiError, match="NoSiteContext"):
        collect("unifi", factory)


def test_env_fallback(monkeypatch):
    monkeypatch.setenv("OPNSENSE_API_KEY", "from-env")
    params = validate_source_params("opnsense", {"url": "https://x", "api_secret": "s", "enabled": True, "filters": {}})
    assert params["api_key"] == "from-env"
    assert params["collect"]["arp_table"] is True and params["collect"]["dhcp_leases"] is False
