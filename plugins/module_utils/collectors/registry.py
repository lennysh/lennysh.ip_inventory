# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Collector registry. Add new sources here so the pipeline and inventory plugin can use them."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.collectors.opnsense import OpnsenseCollector
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.collectors.proxmox import ProxmoxCollector
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.collectors.technitium import TechnitiumCollector
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.collectors.unifi import UnifiCollector

COLLECTORS = dict(
    (cls.name, cls)
    for cls in (OpnsenseCollector, TechnitiumCollector, ProxmoxCollector, UnifiCollector)
)


def get_collector(name):
    try:
        return COLLECTORS[name]
    except KeyError:
        raise KeyError("Unknown source %r (available: %s)" % (name, ", ".join(sorted(COLLECTORS))))
