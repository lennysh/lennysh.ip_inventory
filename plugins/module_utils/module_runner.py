# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Shared ``main()`` for the ``*_info`` collector modules."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.api_client import ApiError


def run_collector_module(collector_cls):
    module = AnsibleModule(argument_spec=collector_cls.argument_spec, supports_check_mode=True)
    collector = collector_cls(module.params)
    try:
        records = collector.collect()
    except ApiError as exc:
        module.fail_json(msg="%s: %s" % (collector_cls.name, exc), status=exc.status, url=exc.url)
    for warning in collector.warnings:
        module.warn(warning)
    module.exit_json(changed=False, source=collector_cls.name, records=records, count=len(records))
