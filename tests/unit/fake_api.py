# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Fixture-driven fake HTTP layer shared by the unit tests (and tests/e2e/mock_api.py's key format)."""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import json
import os
from urllib.parse import urlparse

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.api_client import ApiError, HttpClient

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "api")


def load_api_fixture(name):
    with open(os.path.join(FIXTURE_DIR, name + ".json")) as handle:
        return json.load(handle)


def fixture_key(method, url, params=None):
    """Same key format used by the fixtures and tests/e2e/mock_api.py."""
    key = "%s %s" % (method.upper(), urlparse(url).path)
    if params and params.get("zone"):
        key += "?zone=%s" % params["zone"]
    return key


class FakeClient(HttpClient):
    """HttpClient replacement that answers from a fixture dict and records calls."""

    routes = {}
    calls = []
    instances = []

    def __init__(self, base_url, **kwargs):
        super(FakeClient, self).__init__(base_url, **kwargs)
        self.init_kwargs = kwargs
        FakeClient.instances.append(self)

    def request(self, method, path, params=None, json_body=None, headers=None, allow_status=()):
        key = fixture_key(method, self.url_for(path), params)
        FakeClient.calls.append(key)
        if key not in self.routes:
            if 404 in allow_status:
                return 404, None
            raise ApiError("HTTP 404 from %s" % key, status=404)
        payload = self.routes[key]
        status = payload.get("__status__", 200) if isinstance(payload, dict) else 200
        if status >= 400:
            if status in allow_status:
                return status, None
            raise ApiError("HTTP %s from %s" % (status, key), status=status)
        return status, payload


def make_factory(*names, **overrides):
    """Return a FakeClient class answering from the named fixture files (plus overrides)."""
    routes = {}
    for name in names:
        routes.update(load_api_fixture(name))
    routes.update(overrides)
    FakeClient.routes = routes
    FakeClient.calls = []
    FakeClient.instances = []
    return FakeClient
