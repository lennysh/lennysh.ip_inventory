# lennysh.ip_inventory.issues

Flag anomalies in the reconciled inventory.

Runs the issue checks over `ip_inventory_hosts` and sets `ip_inventory_findings` and `ip_inventory_issue_summary`.

Checks: mac_conflict, mac_shared, hostname_shared, dns_only, discovered, dns_unreachable, active_unreachable, missing_mac, cname_aliases.

See the [collection README](../../README.md) for how the roles fit together.

## Role variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ip_inventory_hosts` | list of dict | **required** | Reconciled host records. |
| `ip_inventory_subnets` | list of dict | `[]` | Subnet records (gateway detection). |
| `ip_inventory_issues_enabled` | bool | `true` | Run the analysis. When false `ip_inventory_findings` is empty. |
| `ip_inventory_issues_checks` | list of str | `[]` | Only run these checks. Empty runs all of them. |
| `ip_inventory_issues_skip_checks` | list of str | `[]` | Checks to skip. |
| `ip_inventory_issues_cname_alias_threshold` | int | `10` | Minimum CNAME aliases on one IP to report `cname_aliases`. |
| `ip_inventory_issues_fail_on` | list of str | `[]` | Fail the play if findings with these severities exist. |

## Example playbook

```yaml
- name: Analyze, failing the play on high-severity findings
  ansible.builtin.include_role:
    name: lennysh.ip_inventory.issues
  vars:
    ip_inventory_issues_skip_checks: [cname_aliases]
    ip_inventory_issues_fail_on: [high]
```

## License

GPL-3.0-or-later

## Author

Lenny Shirley (@lennysh)
