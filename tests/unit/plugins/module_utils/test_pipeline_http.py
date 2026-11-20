# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from ansible_collections.lennysh.ip_inventory.plugins.module_utils.api_client import ApiError, HttpClient
from ansible_collections.lennysh.ip_inventory.plugins.module_utils.pipeline import PipelineError, run_pipeline

SOURCES = {
    "opnsense": {"url": "https://opn.test", "api_key": "k", "api_secret": "s", "filters": {"exclude_interfaces": ["lo0"]}},
    "technitium": {"url": "http://tech.test:5380", "token": "t"},
    "proxmox": {"url": "https://pve.test:8006", "token_id": "a@pam!b", "token_secret": "x"},
    "unifi": {"url": "https://unifi.test", "api_key": "u", "enabled": False},
}
FILTERS = {"include_networks": ["192.168.*"], "exclude_networks": ["127.*", "172.17.*"], "exclude_interfaces": ["lo0", "wan"],
           "exclude_name_patterns": ["*docker*"]}


def fake_ping(ips, timeout_seconds=1.0, concurrency=50):
    return dict((ip, ip in ("192.168.1.10", "192.168.30.77")) for ip in ips)


def test_run_pipeline_end_to_end(fake_api):
    factory = fake_api("opnsense", "technitium", "proxmox", "unifi")
    result = run_pipeline(
        {"sources": SOURCES, "filters": FILTERS, "ping": {"enabled": True, "discover_unknown": True}},
        client_factory=factory, ping_func=fake_ping,
    )
    assert sorted(result["stats"]) == ["opnsense", "proxmox", "technitium"]          # unifi disabled
    assert result["stats"]["opnsense"] == {"collected": 17, "kept": 13, "failed": False}
    ips = [h["ip"] for h in result["hosts"]]
    assert "172.17.0.2" not in ips and "192.168.30.15" not in ips                       # filtered (docker)
    assert result["hosts"][-1]["ip"] == "192.168.30.77" and result["hosts"][-1]["record_type"] == "discovered"
    nas = [h for h in result["hosts"] if h["ip"] == "192.168.1.10"][0]
    assert nas["ping_status"] == "up"
    assert "discovered" in [f["category"] for f in result["findings"]]


def test_run_pipeline_raw_and_issue_toggle(fake_api):
    factory = fake_api("opnsense")
    result = run_pipeline({"sources": {"opnsense": SOURCES["opnsense"]}, "raw": True}, client_factory=factory)
    assert len(result["hosts"]) == 16 and result["findings"] == []                     # lo0 dropped by source filter
    result = run_pipeline({"sources": {"opnsense": SOURCES["opnsense"]}, "issues": {"enabled": False}}, client_factory=factory)
    assert result["findings"] == []


def test_run_pipeline_errors(fake_api):
    factory = fake_api()      # no routes: every call 404s
    with pytest.raises(PipelineError, match="opnsense collection failed"):
        run_pipeline({"sources": {"opnsense": SOURCES["opnsense"]}}, client_factory=factory)
    result = run_pipeline({"sources": {"opnsense": SOURCES["opnsense"]}, "ignore_source_errors": True}, client_factory=factory)
    assert result["stats"]["opnsense"]["failed"] is True and result["warnings"]
    with pytest.raises(PipelineError, match="Invalid options for source 'proxmox'"):
        run_pipeline({"sources": {"proxmox": {"url": "x", "token_id": "a", "token_secret": "b", "bogus": 1}}})


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/ok"):
            body = json.dumps({"path": self.path, "auth": self.headers.get("Authorization")}).encode()
            self.send_response(200)
        elif self.path == "/text":
            body = b"not json"
            self.send_response(200)
        else:
            body = b'{"error": "nope"}'
            self.send_response(500)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever)
    thread.daemon = True
    thread.start()
    yield "http://127.0.0.1:%d" % httpd.server_address[1]
    httpd.shutdown()


def test_http_client_real_requests(server):
    client = HttpClient(server, headers={"Authorization": "Bearer abc"})
    assert client.get("/ok", params={"a": "1"}) == {"path": "/ok?a=1", "auth": "Bearer abc"}
    with pytest.raises(ApiError) as exc:
        client.get("/boom")
    assert exc.value.status == 500 and "nope" in str(exc.value)
    assert client.request("GET", "/boom", allow_status=(500,)) == (500, None)
    with pytest.raises(ApiError, match="Non-JSON"):
        client.get("/text")
    with pytest.raises(ApiError, match="Connection to"):
        HttpClient("http://127.0.0.1:1").get("/x")
