# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type


class ModuleDocFragment(object):

    DOCUMENTATION = r"""
options:
  url:
    description:
      - Base URL of the API endpoint, for example V(https://opnsense.example.com).
      - Falls back to the E(<SOURCE>_URL) environment variable (for example E(OPNSENSE_URL)).
    type: str
    required: true
  validate_certs:
    description:
      - Verify TLS certificates. Homelab appliances often use self-signed certificates.
    type: bool
    aliases: [verify_ssl]
  timeout:
    description:
      - HTTP timeout in seconds for each API request.
    type: int
    default: 30
"""

    RECORDS = r"""
attributes:
  check_mode:
    support: full
    details: Read-only; the module never changes the remote system.
  diff_mode:
    support: none
  platform:
    platforms: posix
notes:
  - The module only reads data. It is safe to run in check mode.
  - Returned records follow the common observation schema shared by every
    C(lennysh.ip_inventory) collector, so they can be fed straight into the
    P(lennysh.ip_inventory.reconcile#filter) filter or the C(lennysh.ip_inventory.reconcile) role.
seealso:
  - module: lennysh.ip_inventory.opnsense_info
  - module: lennysh.ip_inventory.technitium_info
  - module: lennysh.ip_inventory.proxmox_info
  - module: lennysh.ip_inventory.unifi_info
"""
