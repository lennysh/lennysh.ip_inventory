# Extending lennysh.ip_inventory

All data moves between stages as **observation records**: plain dicts with a fixed set of keys.
Anything that produces records can feed the pipeline, and anything that reads `ip_inventory_*` facts can report on it.

```python
{
    "ip": "192.168.1.10",          # "" for VLAN definitions
    "hostname": "nas.lab.example",
    "source": "technitium",      # collector name
    "record_type": "dns_a",      # arp, dhcp_lease, dhcp_reserved, dns_a, dns_cname, dns_ptr, subnet, vlan, ...
    "mac": "aa:bb:cc:00:00:10",
    "vlan": "20",
    "notes": "zone=lab.example",
    "metadata": {...},           # anything source specific
    "ping_status": None,         # up | down | skipped (set by reachability)
}
```

`plugins/module_utils/records.py` defines the schema, the record-type groups (`DNS_RECORD_TYPES`,
`ACTIVE_RECORD_TYPES`, ...) and the merge priority (`RECORD_PRIORITY`). If your new source uses new record types,
add them there so that merging and issue checks treat them correctly. For example, add a
"live" type to `ACTIVE_RECORD_TYPES`.

## Add a source

Say you want NetBox.

1. **Collector**: `plugins/module_utils/collectors/netbox.py`

   ```python
   from ansible.module_utils.basic import env_fallback
   from ansible_collections.lennysh.ip_inventory.plugins.module_utils.collectors.base import Collector, connection_spec
   from ansible_collections.lennysh.ip_inventory.plugins.module_utils.records import make_record

   class NetboxCollector(Collector):
       name = "netbox"
       argument_spec = dict(
           connection_spec("NETBOX", validate_certs_default=True),   # url / validate_certs / timeout
           token={"type": "str", "required": True, "no_log": True, "fallback": (env_fallback, ["NETBOX_TOKEN"])},
       )

       def collect(self):
           client = self.client(headers={"Authorization": "Token %s" % self.params["token"]})
           records = []
           for row in (client.get("/api/ipam/ip-addresses/", params={"limit": 0}) or {}).get("results", []):
               ip = row["address"].split("/")[0]
               records.append(make_record(ip, hostname=row.get("dns_name"), source=self.name,
                                          record_type="ipam_assigned", metadata={"status": row.get("status", {}).get("value")}))
           return records
   ```

   Use `self.warn("...")` for soft problems. Raise `ApiError` (from `module_utils.api_client`) for hard failures.

2. **Register it**: add the class to `COLLECTORS` in `plugins/module_utils/collectors/__init__.py`.
   The inventory plugin can now use `sources: {netbox: {...}}`.

3. **Module**: copy `plugins/modules/opnsense_info.py` to `netbox_info.py`, swap the import and
   `run_collector_module(NetboxCollector)`, and update `DOCUMENTATION` to match `argument_spec`
   (`ansible-test sanity` checks that they agree).

4. **Role**: copy `roles/collect_opnsense` to `roles/collect_netbox` and rename the variables
   (`ip_inventory_netbox_*`). The tail of `tasks/main.yml` stays as is:

   ```yaml
   - name: Filter and add NetBox observations
     ansible.builtin.include_role:
       name: lennysh.ip_inventory.collect_common
       tasks_from: add.yml
     vars:
       collect_common_source: netbox
       collect_common_result: "{{ _ip_inventory_netbox_result }}"
       collect_common_filters: "{{ ip_inventory_netbox_filters }}"
   ```

5. **Use it**: `ip_inventory_sources: [opnsense, technitium, netbox]`.

6. **Test it**: drop a fixture into `tests/unit/fixtures/api/netbox.json` (keys are `"METHOD /path"`),
   add a test in `tests/unit/plugins/module_utils/test_collectors.py` using the `fake_api("netbox")` fixture,
   and `tests/e2e/mock_api.py` will serve it automatically.

### Sources that live outside this collection

`ip_inventory_sources` also accepts fully-qualified role names. A role in your own collection only has to
append records to `ip_inventory_observations`, ideally through `collect_common`:

```yaml
ip_inventory_sources: [opnsense, technitium, my_ns.my_col.collect_spreadsheet]
```

## Add an issue check

In `plugins/module_utils/issues.py`:

```python
def check_lease_expired(hosts, ctx):
    findings = []
    for record in hosts:
        if "dhcp_lease" in all_record_types(record) and record.get("ping_status") == "down":
            findings.append(finding("low", "lease_unreachable", "Lease but no ping: %s" % record["ip"],
                                    "DHCP lease exists but the host does not answer.", ips=[record["ip"]]))
    return findings

CHECKS["lease_unreachable"] = check_lease_expired
CATEGORY_DESCRIPTIONS["lease_unreachable"] = "DHCP lease but ICMP is down"
```

Reports, the summary, the inventory plugin's `issue_*` groups and `ip_inventory_issues_fail_on` pick it up automatically.

## Add or change a report

Reports are plain Jinja2 templates in `roles/report/templates/`. Every `ip_inventory_*` fact is available:
`ip_inventory_hosts`, `ip_inventory_subnets`, `ip_inventory_orphan_vlans`, `ip_inventory_findings`,
`ip_inventory_issue_summary`, `ip_inventory_source_stats`, `ip_inventory_warnings`, `ip_inventory_generated_at`.
The collection's filters are handy inside templates (`csv_row`, `issue_summary`, `issues_by_ip`, `dns_summary`).

To add one without touching the collection:

```yaml
ip_inventory_report_custom:
  - name: dns_cleanup
    template: templates/dns_cleanup.md.j2     # relative to your playbook, or absolute
    basename: dns-cleanup
    ext: md
    requires: findings                         # optional: skip when there are no findings (or 'subnets')
```

See `docs/examples/templates/dns_cleanup.md.j2`. To change a built-in report, copy its template, edit it,
register the copy as a custom report, and drop the built-in name from `ip_inventory_reports`.

## Use the steps directly

Each processing step is a filter, so you can build your own flow:

```yaml
- lennysh.ip_inventory.technitium_info:
    url: http://dns:5380
  register: dns

- ansible.builtin.set_fact:
    merged: "{{ dns.records | lennysh.ip_inventory.filter_records(my_filters) | lennysh.ip_inventory.reconcile }}"

- ansible.builtin.debug:
    msg: "{{ merged.hosts | lennysh.ip_inventory.analyze_issues(merged.subnets, checks=['dns_only']) }}"
```
