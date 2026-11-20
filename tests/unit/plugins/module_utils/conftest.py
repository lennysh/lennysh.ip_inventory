# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.lennysh.ip_inventory.tests.unit.fake_api import make_factory


@pytest.fixture
def fake_api():
    """Return a factory: ``fake_api('opnsense', 'technitium')`` -> client_factory."""
    return make_factory
