#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: opnsense_info
short_description: Collect interface subnets, VLANs, ARP and DHCP observations from OPNsense
version_added: 1.0.0
author: Lenny Shirley (@lennysh)
description:
  - Reads interface subnets, VLAN definitions and the ARP table from the OPNsense API
    and returns them as IP inventory observation records.
  - Optionally reads DHCP leases (Kea or ISC), Kea reservations and Unbound host overrides.
  - "Required API privileges: Interfaces: Overview, Interfaces: VLANs, Diagnostics: ARP Table."
extends_documentation_fragment:
  - lennysh.ip_inventory.connection
  - lennysh.ip_inventory.connection.records
  - ansible.builtin.action_common_attributes
options:
  validate_certs:
    default: false
  api_key:
    description:
      - OPNsense API key. Falls back to E(OPNSENSE_API_KEY).
    type: str
    required: true
  api_secret:
    description:
      - OPNsense API secret. Falls back to E(OPNSENSE_API_SECRET).
    type: str
    required: true
  dhcp_backend:
    description:
      - Which DHCP backend to query when O(collect.dhcp_leases) or O(collect.dhcp_static) are enabled.
      - V(auto) tries Kea first and falls back to ISC.
    type: str
    choices: [auto, kea, isc]
    default: auto
  collect:
    description:
      - Which datasets to collect.
    type: dict
    default: {}
    suboptions:
      arp_table:
        description: Collect the ARP table (IP, MAC, interface).
        type: bool
        default: true
      interfaces:
        description: Collect assigned interface IPv4 subnets (record type C(subnet)).
        type: bool
        default: true
      vlans:
        description: Collect VLAN definitions (record type C(vlan)).
        type: bool
        default: true
      dhcp_leases:
        description: Collect DHCPv4 leases.
        type: bool
        default: false
      dhcp_static:
        description: Collect Kea DHCPv4 reservations.
        type: bool
        default: false
      unbound_overrides:
        description: Collect Unbound DNS host overrides.
        type: bool
        default: false
"""

EXAMPLES = r"""
- name: Collect OPNsense subnets, VLANs and ARP entries
  lennysh.ip_inventory.opnsense_info:
    url: https://opnsense.example.com
    api_key: "{{ vault_opnsense_api_key }}"
    api_secret: "{{ vault_opnsense_api_secret }}"
  register: opnsense

- name: Also pull Kea leases
  lennysh.ip_inventory.opnsense_info:
    url: https://opnsense.example.com
    dhcp_backend: kea
    collect:
      dhcp_leases: true
  environment:
    OPNSENSE_API_KEY: "{{ vault_opnsense_api_key }}"
    OPNSENSE_API_SECRET: "{{ vault_opnsense_api_secret }}"
"""

RETURN = r"""
source:
  description: Collector name.
  returned: always
  type: str
  sample: opnsense
count:
  description: Number of records returned.
  returned: always
  type: int
  sample: 42
records:
  description: Observation records in the common lennysh.ip_inventory schema.
  returned: always
  type: list
  elements: dict
  sample:
    - ip: 192.168.1.10
      hostname: nas.lab.example
      source: opnsense
      record_type: arp
      mac: aa:bb:cc:00:00:10
      vlan: igb0
      notes: null
      metadata: {expires: 1200, permanent: null}
      ping_status: null
"""

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.collectors.opnsense import OpnsenseCollector
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.module_runner import run_collector_module


def main():
    run_collector_module(OpnsenseCollector)


if __name__ == "__main__":
    main()
