# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Base class every source collector derives from.

Writing a new collector:

1. Subclass ``Collector``; set ``name`` and ``argument_spec`` (Ansible
   argument-spec format; reuse ``connection_spec()`` for url/TLS/timeout).
2. Implement ``collect()`` returning a list of ``make_record(...)`` dicts.
   Use ``self.client(...)`` for HTTP and ``self.warn(msg)`` for soft problems.
3. Register it in ``collectors/registry.py`` ``COLLECTORS``.
4. Add a thin module (copy ``plugins/modules/opnsense_info.py``) and a
   ``collect_<name>`` role (copy ``roles/collect_opnsense``).
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible.module_utils.basic import env_fallback

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.api_client import HttpClient


def connection_spec(env_prefix, validate_certs_default=False):
    return {
        "url": {"type": "str", "required": True, "fallback": (env_fallback, ["%s_URL" % env_prefix])},
        "validate_certs": {"type": "bool", "default": validate_certs_default, "aliases": ["verify_ssl"]},
        "timeout": {"type": "int", "default": 30},
    }


class Collector:
    name = "base"
    argument_spec = {}

    def __init__(self, params, client_factory=None):
        """``params`` are already validated against ``argument_spec``.

        ``client_factory`` lets tests swap the HTTP layer; it receives the same
        keyword arguments as ``HttpClient``.
        """
        self.params = params
        self.warnings = []
        self._client_factory = client_factory or HttpClient

    @property
    def collect_opts(self):
        return self.params.get("collect") or {}

    def client(self, base_url=None, **kwargs):
        kwargs.setdefault("validate_certs", self.params.get("validate_certs", True))
        kwargs.setdefault("timeout", self.params.get("timeout", 30))
        return self._client_factory(base_url or self.params["url"], **kwargs)

    def warn(self, message):
        self.warnings.append("%s: %s" % (self.name, message))

    def collect(self):
        raise NotImplementedError
