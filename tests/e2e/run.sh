#!/usr/bin/env bash
# End-to-end tests against tests/e2e/mock_api.py (all four source APIs) and tests/e2e/smtp_sink.py.
# Used by CI (.github/workflows/tests.yml) and runnable locally:
#
#   tests/e2e/run.sh            # needs ansible-core, community.general, and this collection installed
#
# Checks: the run playbook writes every report, the inventory plugin builds groups, the
# reachability role pings (loopback only), and the delivery example copies + e-mails reports.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${HERE}/../.." && pwd)"
WORK="$(mktemp -d)"
API_PORT="${API_PORT:-8765}"
SMTP_PORT="${SMTP_PORT:-2525}"
PY="${PYTHON:-python3}"
export ANSIBLE_PYTHON_INTERPRETER=auto_silent ANSIBLE_NOCOWS=1

pids=()
cleanup() {
    for pid in "${pids[@]}"; do kill "${pid}" 2>/dev/null || true; done
    rm -rf "${WORK}"
}
trap cleanup EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
step() { echo; echo "=== $*"; }

wait_port() {
    for _ in $(seq 1 50); do
        "${PY}" -c "import socket,sys; socket.create_connection(('127.0.0.1', int(sys.argv[1])), 1)" "$1" 2>/dev/null && return 0
        sleep 0.2
    done
    fail "nothing listening on port $1"
}

step "Starting mock API (:${API_PORT}) and SMTP sink (:${SMTP_PORT})"
"${PY}" "${HERE}/mock_api.py" --port "${API_PORT}" > "${WORK}/mock_api.log" 2>&1 & pids+=($!)
"${PY}" "${HERE}/smtp_sink.py" --port "${SMTP_PORT}" --output "${WORK}/mail" > "${WORK}/smtp.log" 2>&1 & pids+=($!)
wait_port "${API_PORT}"
wait_port "${SMTP_PORT}"
ansible --version | head -1

step "Run playbook (lennysh.ip_inventory.run)"
ansible-playbook lennysh.ip_inventory.run -e @"${HERE}/vars.yml" -e ip_inventory_output_dir="${WORK}/out"
count=$(find "${WORK}/out" -type f | wc -l)
[ "${count}" -eq 7 ] || fail "expected 7 report files, found ${count}"
grep -q '"count": 22' "${WORK}"/out/inventory-*.json || fail "inventory JSON does not contain 22 hosts"

step "Inventory plugin"
E2E_TECHNITIUM_TOKEN=dummy ansible-inventory -i "${HERE}/e2e.ip_inventory.yml" --list > "${WORK}/inventory.json"
"${PY}" - "${WORK}/inventory.json" <<'EOF'
import json, sys
data = json.load(open(sys.argv[1]))
hosts = data["_meta"]["hostvars"]
assert len(hosts) == 22, len(hosts)
for group in ("subnet_192_168_20_0_24", "vlan_iot", "source_proxmox", "issue_mac_conflict", "name_conflict"):
    assert group in data, "missing group %s" % group
print("inventory OK: %d hosts, %d groups" % (len(hosts), len(data) - 1))
EOF

step "Reachability role (real ICMP, loopback only)"
ansible-playbook "${HERE}/reachability.yml"

step "Delivery example (web copy + e-mail)"
printf 'localhost ansible_connection=local\nwebbox ansible_connection=local\n' > "${WORK}/hosts.ini"
ansible-playbook -i "${WORK}/hosts.ini" "${REPO}/docs/examples/deliver_reports.yml" \
    -e @"${HERE}/vars.yml" -e ip_inventory_output_dir="${WORK}/out2" \
    -e report_web_host=webbox -e report_web_root="${WORK}/web" -e report_web_become=false \
    -e report_mail_to=ci@example.com -e report_smtp_host=127.0.0.1 -e report_smtp_port="${SMTP_PORT}"
[ -s "${WORK}/web/index.html" ] || fail "index.html was not published"
mail_file=$(find "${WORK}/mail" -name '*.eml' | head -1)
[ -n "${mail_file}" ] || fail "no e-mail received by the SMTP sink"
"${PY}" - "${mail_file}" <<'EOF'
import email, sys
msg = email.message_from_string(open(sys.argv[1]).read())
names = [p.get_filename() for p in msg.walk() if p.get_filename()]
assert len(names) == 4, names
print("e-mail OK: %d attachments" % len(names))
EOF

echo
echo "All end-to-end tests passed."
