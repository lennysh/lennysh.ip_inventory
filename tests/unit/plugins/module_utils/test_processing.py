# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.discover import discovered_records, sweep_candidates
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.filters import RecordFilter, ip_matches_pattern, wildcard_to_network
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.issues import analyze_issues, findings_by_ip, summarize_findings
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.merge import reconcile
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.ping import apply_ping_results, pingable_ips
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.records import make_record, normalize_mac


def rec(ip, rtype, source="test", **kw):
    return make_record(ip, source=source, record_type=rtype, **kw)


@pytest.mark.parametrize("value,expected", [
    ("AA-BB-CC-00-00-01", "aa:bb:cc:00:00:01"),
    ("aabb.cc00.0001", "aa:bb:cc:00:00:01"),
    ("weird", "weird"),
    (None, None),
])
def test_normalize_mac(value, expected):
    assert normalize_mac(value) == expected


@pytest.mark.parametrize("ip,pattern,expected", [
    ("192.168.1.5", "192.168.*", True),
    ("10.36.1.5", "192.168.*", False),
    ("192.168.1.5", "192.168.1.0/24", True),
    ("192.168.1.5", "192.168.1.5", True),
    ("172.17.0.2", "172.17.*", True),
])
def test_ip_patterns(ip, pattern, expected):
    assert ip_matches_pattern(ip, pattern) is expected


def test_wildcard_to_network():
    assert str(wildcard_to_network("192.168.*")) == "192.168.0.0/16"
    assert str(wildcard_to_network("10.*")) == "10.0.0.0/8"


def test_record_filter_global_and_per_source():
    records = [
        rec("192.168.1.5", "arp", source="opnsense", hostname="ok"),
        rec("192.168.1.6", "arp", source="opnsense", hostname="my-docker-box"),
        rec("10.20.1.5", "arp", source="opnsense"),                     # outside include_networks
        rec("192.168.1.7", "arp", source="opnsense", vlan="wan"),
        rec("192.168.1.8", "dns_ptr", source="technitium"),
        rec("192.168.9.9", "dns_a", source="technitium"),
    ]
    rf = RecordFilter(
        {"include_networks": ["192.168.*"], "exclude_name_patterns": ["*DOCKER*"], "exclude_interfaces": ["wan"]},
        {"technitium": {"include_networks": ["192.168.9.0/24"], "exclude_record_types": ["dns_ptr"]}},
    )
    assert [r["ip"] for r in rf.filter_records(records)] == ["192.168.1.5", "192.168.9.9"]


def test_reconcile_merges_by_ip_and_enriches_subnets():
    records = [
        rec("192.168.20.1", "subnet", source="opnsense", hostname="opt1", vlan="20", notes="IoT", metadata={"cidr": "192.168.20.0/24"}),
        rec("", "vlan", source="opnsense", hostname="IoT (vlan 20)", vlan="20", notes="parent=igb1", metadata={"parent": "igb1"}),
        rec("", "vlan", source="opnsense", hostname="Spare (vlan 99)", vlan="99", notes="parent=igb1", metadata={"parent": "igb1"}),
        rec("192.168.20.50", "dns_a", source="technitium", hostname="plug.lab"),
        rec("192.168.20.50", "dns_cname", source="technitium", hostname="alias.lab"),
        rec("192.168.20.50", "arp", source="opnsense", mac="AA-BB-CC-00-00-50", vlan="igb1_vlan20"),
        rec("192.168.20.9", "dns_a", source="technitium", hostname="stale.lab"),
        rec("192.168.20.10", "dns_a", source="technitium", hostname="x"),
    ]
    result = reconcile(records)
    hosts = dict((h["ip"], h) for h in result["hosts"])
    assert [h["ip"] for h in result["hosts"]] == ["192.168.20.9", "192.168.20.10", "192.168.20.50"]
    plug = hosts["192.168.20.50"]
    assert plug["hostname"] == "plug.lab"               # non-CNAME preferred
    assert plug["record_type"] == "arp"                 # ARP is the primary record
    assert plug["mac"] == "aa:bb:cc:00:00:50"
    assert plug["vlan"] == "20"                         # subnet tag beats ARP interface name
    assert plug["metadata"]["cname_aliases"] == ["alias.lab"]
    assert plug["metadata"]["vlan_name"] == "IoT"
    assert plug["metadata"]["subnet"] == "192.168.20.0/24"
    assert plug["metadata"]["source_metadata"]["opnsense"]["record_types"] == ["arp"]
    assert not plug["metadata"]["dns_only"] and hosts["192.168.20.9"]["metadata"]["dns_only"]
    assert result["subnets"][0]["metadata"]["vlan_parent"] == "igb1"
    assert result["subnets"][0]["metadata"]["total_hosts"] == 254
    assert [v["metadata"]["vlan_name"] for v in result["orphan_vlans"]] == ["Spare"]


def test_merge_notes_collapses_proxmox_prefix():
    records = [
        rec("192.168.1.51", "lxc_runtime", source="proxmox", notes="vmid=101 node=pve1 iface=eth0"),
        rec("192.168.1.51", "lxc_config_static", source="proxmox", notes="vmid=101 node=pve1 net0=ip=192.168.1.51/24"),
    ]
    assert reconcile(records)["hosts"][0]["notes"] == "vmid=101 node=pve1 iface=eth0; net0=ip=192.168.1.51/24"


def test_ping_helpers():
    records = [rec("10.0.0.1", "arp"), rec("10.0.0.2", "dns_a"), rec("10.0.0.254", "subnet")]
    assert pingable_ips(records) == ["10.0.0.1", "10.0.0.2"]
    statuses = [r["ping_status"] for r in apply_ping_results(records, {"10.0.0.1": True, "10.0.0.2": "down"})]
    assert statuses == ["up", "down", "skipped"]


def test_sweep_candidates_and_discovered():
    subnets = [
        rec("10.0.0.1", "subnet", hostname="lan", vlan="10", metadata={"cidr": "10.0.0.0/29", "vlan_name": "LAN"}),
        rec("8.8.8.1", "subnet", metadata={"cidr": "8.8.8.0/29"}),           # public: skipped
        rec("10.1.0.1", "subnet", metadata={"cidr": "10.1.0.0/16"}),         # too big: skipped
        rec("10.2.0.1", "subnet", metadata={"cidr": "10.2.0.0/31"}),         # /31: skipped
    ]
    candidates = sweep_candidates(subnets, {"10.0.0.3"})
    assert [c["ip"] for c in candidates] == ["10.0.0.2", "10.0.0.4", "10.0.0.5", "10.0.0.6"]
    found = discovered_records(candidates, {"10.0.0.4": True, "10.0.0.5": "up", "10.0.0.6": False}, subnets)
    assert [(r["ip"], r["record_type"], r["vlan"], r["metadata"]["interface"]) for r in found] == [
        ("10.0.0.4", "discovered", "10", "lan"), ("10.0.0.5", "discovered", "10", "lan")]
    assert [c["ip"] for c in sweep_candidates(subnets, set(), private_only=False, max_hosts_per_subnet=6)] == [
        "10.0.0.2", "10.0.0.3", "10.0.0.4", "10.0.0.5", "10.0.0.6", "8.8.8.2", "8.8.8.3", "8.8.8.4", "8.8.8.5", "8.8.8.6"]


def _hosts():
    records = [
        rec("10.0.0.1", "subnet", metadata={"cidr": "10.0.0.0/24"}),
        rec("10.0.0.10", "arp", mac="aa:aa:aa:aa:aa:10", hostname="a"),
        rec("10.0.0.10", "dhcp_reserved", mac="bb:bb:bb:bb:bb:10", hostname="a"),
        rec("10.0.0.20", "arp", mac="cc:cc:cc:cc:cc:20"),
        rec("10.0.0.21", "arp", mac="cc:cc:cc:cc:cc:20"),
        rec("10.0.0.30", "dns_a", hostname="dup.lab"),
        rec("10.0.0.31", "dhcp_lease", hostname="dup.lab"),
        rec("10.0.0.40", "dns_a", hostname="down.lab"),
        rec("10.0.0.40", "arp", mac="dd:dd:dd:dd:dd:40"),
    ]
    merged = reconcile(records)
    hosts = apply_ping_results(merged["hosts"], {"10.0.0.40": False})
    return hosts, merged["subnets"]


def test_analyze_issues_categories_and_order():
    hosts, subnets = _hosts()
    findings = analyze_issues(hosts, subnets)
    cats = [(f["severity"], f["category"]) for f in findings]
    assert cats[:2] == [("high", "mac_conflict"), ("high", "mac_shared")]
    assert ("medium", "hostname_shared") in cats and ("medium", "dns_only") in cats
    assert ("low", "dns_unreachable") in cats and ("low", "active_unreachable") in cats
    assert ("low", "missing_mac") in cats                                   # dhcp_lease without MAC
    summary = summarize_findings(findings)
    assert summary["total"] == len(findings) and summary["by_severity"]["high"] == 2
    assert "dns_only" in summary["descriptions"]
    assert findings_by_ip(findings)["10.0.0.10"] == ["mac_conflict", "active_unreachable"]


def test_analyze_issues_selection():
    hosts, subnets = _hosts()
    assert set(f["category"] for f in analyze_issues(hosts, subnets, checks=["dns_only"])) == {"dns_only"}
    assert "mac_shared" not in [f["category"] for f in analyze_issues(hosts, subnets, skip_checks=["mac_shared"])]
    with pytest.raises(ValueError, match="Unknown issue check"):
        analyze_issues(hosts, subnets, checks=["nope"])


def test_ping_many_uses_supplied_runner():
    from ansible_collections.lennysh.ip_inventory.plugins.module_utils.ping import ping_argv, ping_many

    calls = []

    def run(argv):
        calls.append(argv)
        if argv[-1] == "10.0.0.3":
            raise OSError("boom")
        return 0 if argv[-1] == "10.0.0.1" else 1

    results = ping_many(["10.0.0.1", "10.0.0.2", "10.0.0.1", "10.0.0.3", ""], run, timeout_seconds=2, concurrency=2)
    assert results == {"10.0.0.1": True, "10.0.0.2": False, "10.0.0.3": False}
    assert len(calls) == 3                                   # duplicates and empty values skipped
    assert ping_argv("10.0.0.9", 2.5, "/usr/bin/ping")[0] == "/usr/bin/ping"
    assert ping_many([], run) == {}
