#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: proxmox_info
short_description: Collect VM and container IP addresses from Proxmox VE
version_added: 1.0.0
author: Lenny Shirley (@lennysh)
description:
  - Reads QEMU guest-agent IPs (running VMs), LXC runtime IPs, and static IPs from VM/LXC
    network config, and returns them as observation records.
  - The token user needs B(PVE Auditor) on C(/) (includes VM.Audit and VM.Monitor).
    Without VM read ACLs Proxmox returns empty lists; the module warns when that happens.
extends_documentation_fragment:
  - lennysh.ip_inventory.connection
  - lennysh.ip_inventory.connection.records
  - ansible.builtin.action_common_attributes
options:
  validate_certs:
    default: false
  token_id:
    description:
      - API token ID in C(user@realm!tokenname) form. Falls back to E(PROXMOX_TOKEN_ID).
    type: str
    required: true
  token_secret:
    description:
      - API token secret (UUID). Falls back to E(PROXMOX_TOKEN_SECRET).
    type: str
    required: true
  use_guest_agent:
    description:
      - Query the QEMU guest agent of running VMs for their live IP addresses.
    type: bool
    default: true
"""

EXAMPLES = r"""
- name: Collect Proxmox guest IPs
  lennysh.ip_inventory.proxmox_info:
    url: https://proxmox.example.com:8006
    token_id: ip-inventory@pam!inventory
    token_secret: "{{ vault_proxmox_token_secret }}"
  register: proxmox
"""

RETURN = r"""
source:
  description: Collector name.
  returned: always
  type: str
  sample: proxmox
count:
  description: Number of records returned.
  returned: always
  type: int
  sample: 12
records:
  description: Observation records in the common lennysh.ip_inventory schema.
  returned: always
  type: list
  elements: dict
  sample:
    - ip: 192.168.1.50
      hostname: web01
      source: proxmox
      record_type: vm_guest_agent
      mac: bc:24:11:00:01:00
      vlan: null
      notes: vmid=100 node=pve1 iface=eth0
      metadata: {vmid: 100, node: pve1, vm_type: qemu, status: running, tags: [web, prod]}
      ping_status: null
"""

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.collectors.proxmox import ProxmoxCollector
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.module_runner import run_collector_module


def main():
    run_collector_module(ProxmoxCollector)


if __name__ == "__main__":
    main()
