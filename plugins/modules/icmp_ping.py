#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: icmp_ping
short_description: Concurrently ICMP ping a list of IP addresses
version_added: 1.0.0
author: Lenny Shirley (@lennysh)
description:
  - Sends one ICMP echo request to each target using the system C(ping) binary,
    in parallel, and reports which targets answered.
  - Unlike M(ansible.builtin.ping) this is a real network ping, run from the host executing the module.
  - Used by the C(lennysh.ip_inventory.reachability) role for both known-host checks and subnet sweeps.
extends_documentation_fragment:
  - ansible.builtin.action_common_attributes
attributes:
  check_mode:
    support: full
    details: Pinging is read-only, so the module runs normally in check mode.
  diff_mode:
    support: none
  platform:
    platforms: posix
options:
  targets:
    description: IPv4 addresses to ping. Duplicates are ignored.
    type: list
    elements: str
    required: true
  timeout:
    description: Seconds to wait for each reply (rounded up to whole seconds on Linux).
    type: float
    default: 1.0
  concurrency:
    description: Maximum number of pings in flight at once.
    type: int
    default: 50
requirements:
  - C(ping) available in E(PATH) on the target host.
"""

EXAMPLES = r"""
- name: Ping a few hosts
  lennysh.ip_inventory.icmp_ping:
    targets: [192.168.1.1, 192.168.1.10]
  register: ping

- name: Show who answered
  ansible.builtin.debug:
    var: ping.up
"""

RETURN = r"""
reachable:
  description: Mapping of target IP to reachability.
  returned: always
  type: dict
  sample: {"192.168.1.1": true, "192.168.1.10": false}
up:
  description: Targets that answered, sorted.
  returned: always
  type: list
  elements: str
  sample: [192.168.1.1]
down:
  description: Targets that did not answer, sorted.
  returned: always
  type: list
  elements: str
  sample: [192.168.1.10]
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.ping import ping_many
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.records import ip_sort_key


def main():
    module = AnsibleModule(
        argument_spec=dict(
            targets=dict(type="list", elements="str", required=True),
            timeout=dict(type="float", default=1.0),
            concurrency=dict(type="int", default=50),
        ),
        supports_check_mode=True,
    )
    ping_bin = module.get_bin_path("ping", required=True)
    results = ping_many(
        module.params["targets"],
        lambda argv: module.run_command(argv)[0],
        timeout_seconds=module.params["timeout"],
        concurrency=module.params["concurrency"],
        ping_command=ping_bin,
    )
    module.exit_json(
        changed=False,
        reachable=results,
        up=sorted((ip for ip, ok in results.items() if ok), key=ip_sort_key),
        down=sorted((ip for ip, ok in results.items() if not ok), key=ip_sort_key),
    )


if __name__ == "__main__":
    main()
