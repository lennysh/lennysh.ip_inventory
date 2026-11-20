# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Serve the unit-test API fixtures over HTTP so the roles and inventory plugin can run end to end.

One server answers for all four sources (their API paths do not overlap) and checks
that each request carries the right kind of credentials.

    python3 tests/e2e/mock_api.py --port 8765
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "unit", "fixtures", "api")

EXPECTED_AUTH = (
    ("/api2/json/", lambda h: (h.get("Authorization") or "").startswith("PVEAPIToken=")),
    ("/proxy/network/", lambda h: bool(h.get("X-API-KEY"))),
    ("/api/zones/", lambda h: (h.get("Authorization") or "").startswith("Bearer ")),
    ("/api/dhcp/", lambda h: (h.get("Authorization") or "").startswith("Bearer ")),
    ("/api/", lambda h: (h.get("Authorization") or "").startswith("Basic ")),
)


def load_routes():
    routes = {}
    for name in sorted(os.listdir(FIXTURES)):
        if name.endswith(".json"):
            with open(os.path.join(FIXTURES, name)) as handle:
                routes.update(json.load(handle))
    return routes


class Handler(BaseHTTPRequestHandler):
    routes = {}

    def _reply(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self):
        url = urlparse(self.path)
        params = dict((k, v[0]) for k, v in parse_qs(url.query).items())
        key = "%s %s" % (self.command, url.path)
        if params.get("zone"):
            key += "?zone=%s" % params["zone"]
        for prefix, check in EXPECTED_AUTH:
            if url.path.startswith(prefix):
                if not check(self.headers):
                    return self._reply(401, {"error": "missing or wrong credentials for %s" % prefix})
                break
        if key not in self.routes:
            return self._reply(404, {"error": "no fixture for %s" % key})
        payload = self.routes[key]
        status = payload.get("__status__", 200) if isinstance(payload, dict) else 200
        return self._reply(status, payload)

    do_GET = _handle
    do_POST = _handle

    def log_message(self, fmt, *args):  # keep test output quiet
        if os.environ.get("MOCK_API_VERBOSE"):
            BaseHTTPRequestHandler.log_message(self, fmt, *args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--bind", default="127.0.0.1")
    args = parser.parse_args()
    Handler.routes = load_routes()
    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    print("mock API on http://%s:%d (%d routes)" % (args.bind, args.port, len(Handler.routes)), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
