#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: technitium_info
short_description: Collect DNS records and DHCP leases from Technitium DNS Server
version_added: 1.0.0
author: Lenny Shirley (@lennysh)
description:
  - Reads A/ANAME, CNAME (resolved to target IPs) and PTR records from Primary zones,
    plus DHCP leases and scope reservations, and returns them as observation records.
  - Forwarder, Stub, Secondary and internal zones are skipped, as are wildcard CNAMEs and disabled records.
  - "Required permissions: Zones (View) and DhcpServer (View)."
extends_documentation_fragment:
  - lennysh.ip_inventory.connection
  - lennysh.ip_inventory.connection.records
  - ansible.builtin.action_common_attributes
options:
  validate_certs:
    default: true
  token:
    description:
      - API token (Users > API tokens). Preferred over O(user)/O(password).
      - Falls back to E(TECHNITIUM_TOKEN).
    type: str
  user:
    description:
      - Username used to log in when O(token) is not set. Falls back to E(TECHNITIUM_USER).
    type: str
    aliases: [username]
  password:
    description:
      - Password used with O(user). Falls back to E(TECHNITIUM_PASSWORD).
    type: str
  collect:
    description:
      - Which datasets to collect.
    type: dict
    default: {}
    suboptions:
      dns_records:
        description: A and ANAME records.
        type: bool
        default: true
      dns_cnames:
        description: CNAME aliases, resolved through to the target A record IP.
        type: bool
        default: true
      dns_ptrs:
        description: PTR records from C(in-addr.arpa) zones.
        type: bool
        default: true
      dhcp_leases:
        description: DHCP leases.
        type: bool
        default: true
      dhcp_scopes:
        description: Reserved leases defined in DHCP scopes.
        type: bool
        default: true
"""

EXAMPLES = r"""
- name: Collect everything from Technitium using an API token
  lennysh.ip_inventory.technitium_info:
    url: http://technitium.example.com:5380
    token: "{{ vault_technitium_token }}"
  register: technitium

- name: DNS only, log in with a user
  lennysh.ip_inventory.technitium_info:
    url: http://technitium.example.com:5380
    user: admin
    password: "{{ vault_technitium_password }}"
    collect:
      dhcp_leases: false
      dhcp_scopes: false
"""

RETURN = r"""
source:
  description: Collector name.
  returned: always
  type: str
  sample: technitium
count:
  description: Number of records returned.
  returned: always
  type: int
  sample: 120
records:
  description: Observation records in the common lennysh.ip_inventory schema.
  returned: always
  type: list
  elements: dict
  sample:
    - ip: 192.168.1.10
      hostname: files.lab.example
      source: technitium
      record_type: dns_cname
      mac: null
      vlan: null
      notes: files.lab.example → nas.lab.example
      metadata: {zone: lab.example, dns_type: CNAME, cname_target: nas.lab.example}
      ping_status: null
"""

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.collectors.technitium import TechnitiumCollector
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.module_runner import run_collector_module


def main():
    run_collector_module(TechnitiumCollector)


if __name__ == "__main__":
    main()
