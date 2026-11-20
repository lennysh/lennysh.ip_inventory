# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible.errors import AnsibleFilterError

from ansible_collections.lennysh.ip_inventory.plugins.filter.ip_inventory import FilterModule

F = FilterModule().filters()


def test_all_filters_registered():
    assert sorted(F) == sorted([
        "filter_records", "reconcile", "sort_records", "enrich_subnets", "pingable_ips", "apply_ping",
        "sweep_candidates", "discovered", "analyze_issues", "issue_summary", "issues_by_ip", "dns_summary", "csv_row",
    ])


def test_csv_row_quotes_everything():
    assert F["csv_row"](["a", 'b "q"', "c,d", None, 5, "x\ny"]) == '"a","b ""q""","c,d","","5","x\ny"'


def test_pipeline_through_filters():
    observations = [
        {"ip": "10.0.0.1", "source": "opnsense", "record_type": "subnet", "hostname": "lan", "metadata": {"cidr": "10.0.0.0/29"}},
        {"ip": "10.0.0.2", "source": "technitium", "record_type": "dns_a", "hostname": "a.lab", "metadata": {}},
        {"ip": "10.0.0.2", "source": "technitium", "record_type": "dns_cname", "hostname": "b.lab", "metadata": {}},
        {"ip": "172.17.0.2", "source": "opnsense", "record_type": "arp", "metadata": {}},
    ]
    kept = F["filter_records"](observations, {"exclude_networks": ["172.17.*"]})
    merged = F["reconcile"](kept)
    assert [h["ip"] for h in merged["hosts"]] == ["10.0.0.2"]
    hosts = F["apply_ping"](merged["hosts"], {"10.0.0.2": False})
    assert F["pingable_ips"](hosts) == ["10.0.0.2"]
    candidates = F["sweep_candidates"](merged["subnets"], hosts)
    assert [c["ip"] for c in candidates] == ["10.0.0.3", "10.0.0.4", "10.0.0.5", "10.0.0.6"]
    found = F["discovered"](candidates, {"10.0.0.5": True}, merged["subnets"])
    hosts = F["sort_records"](found + hosts)
    assert [h["ip"] for h in hosts] == ["10.0.0.2", "10.0.0.5"]
    findings = F["analyze_issues"](hosts, merged["subnets"])
    # a discovered host has no MAC, so missing_mac fires too (discovered counts as live evidence)
    assert F["issue_summary"](findings)["by_category"] == {"discovered": 1, "dns_only": 1, "missing_mac": 1}
    assert F["issues_by_ip"](findings) == {"10.0.0.2": ["dns_only"], "10.0.0.5": ["discovered", "missing_mac"]}
    dns = F["dns_summary"](hosts)
    assert dns["with_cname_aliases"] == 1 and dns["dns_only"] == 1 and dns["dns_ping_down"] == 1
    assert dns["dns_ping_down_sample"] == []     # dns-only rows are reported separately


def test_filters_reject_wrong_input_types():
    with pytest.raises(AnsibleFilterError, match="expects a list"):
        F["reconcile"]({"not": "a list"})
    with pytest.raises(AnsibleFilterError, match="Unknown issue check"):
        F["analyze_issues"]([], [], checks=["bogus"])


def test_partial_records_are_normalized():
    hosts = F["reconcile"]([{"ip": "10.0.0.9", "hostname": "manual"}])["hosts"]
    assert hosts[0]["ping_status"] is None and hosts[0]["mac"] is None and hosts[0]["metadata"]["all_hostnames"] == ["manual"]
