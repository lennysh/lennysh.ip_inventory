#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: unifi_info
short_description: Collect clients and adopted devices from UniFi Network
version_added: 1.0.0
author: Lenny Shirley (@lennysh)
description:
  - Reads active clients (C(stat/sta)), known clients (C(rest/user)) and adopted devices
    (C(stat/device)) from a UniFi Network controller and returns them as observation records.
  - Works with UniFi OS (UDM, UDR, Cloud Key Gen2+, UniFi OS Server) and the legacy self-hosted Network Application.
extends_documentation_fragment:
  - lennysh.ip_inventory.connection
  - lennysh.ip_inventory.connection.records
  - ansible.builtin.action_common_attributes
options:
  validate_certs:
    default: false
  site:
    description: UniFi site name.
    type: str
    default: default
  unifi_os:
    description:
      - Set V(true) for UniFi OS consoles (API under C(/proxy/network)).
      - Set V(false) for the legacy self-hosted Network Application.
    type: bool
    default: true
  api_key:
    description:
      - API key (Settings > Control Plane > Integrations). Preferred over O(username)/O(password).
      - Falls back to E(UNIFI_API_KEY).
    type: str
  username:
    description: Local admin username. Falls back to E(UNIFI_USERNAME).
    type: str
    aliases: [user]
  password:
    description: Password for O(username). Falls back to E(UNIFI_PASSWORD).
    type: str
  collect:
    description: Which datasets to collect.
    type: dict
    default: {}
    suboptions:
      active_clients:
        description: Currently connected clients.
        type: bool
        default: true
      known_clients:
        description: All known clients (including offline ones with a fixed or last IP).
        type: bool
        default: true
      devices:
        description: Adopted UniFi devices (APs, switches, gateways).
        type: bool
        default: true
"""

EXAMPLES = r"""
- name: Collect UniFi clients and devices with an API key
  lennysh.ip_inventory.unifi_info:
    url: https://unifi.example.com
    api_key: "{{ vault_unifi_api_key }}"
  register: unifi
"""

RETURN = r"""
source:
  description: Collector name.
  returned: always
  type: str
  sample: unifi
count:
  description: Number of records returned.
  returned: always
  type: int
  sample: 37
records:
  description: Observation records in the common lennysh.ip_inventory schema.
  returned: always
  type: list
  elements: dict
  sample:
    - ip: 192.168.20.80
      hostname: phone
      source: unifi
      record_type: client_active
      mac: aa:bb:cc:00:20:80
      vlan: "20"
      notes: active; ssid=HomeWifi; network=IoT
      metadata: {site: default, essid: HomeWifi, network: IoT}
      ping_status: null
"""

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.collectors.unifi import UnifiCollector
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.module_runner import run_collector_module


def main():
    run_collector_module(UnifiCollector)


if __name__ == "__main__":
    main()
