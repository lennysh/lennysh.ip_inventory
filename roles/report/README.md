# lennysh.ip_inventory.report

Render IP inventory reports from Jinja2 templates.

Renders the selected built-in reports and any custom templates into `ip_inventory_output_dir` and prints a run summary.

Templates live in `roles/report/templates/` and can use every `ip_inventory_*` fact, so they are easy to copy and customise via `ip_inventory_report_custom`.

Sets `ip_inventory_report_files`, `ip_inventory_generated_at` and `ip_inventory_summary`.

Delivering the files (email, web server, object storage, ...) is left to your playbook; use `ip_inventory_report_files` after the role.

See the [collection README](../../README.md) for how the roles fit together.

## Role variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ip_inventory_hosts` | list of dict | **required** | Host rows to report. |
| `ip_inventory_subnets` | list of dict | `[]` | Subnet records. |
| `ip_inventory_orphan_vlans` | list of dict | `[]` | VLAN definitions without a subnet. |
| `ip_inventory_findings` | list of dict | `[]` | Findings from the `issues` role. |
| `ip_inventory_output_dir` | path | `$PWD/output` | Output directory. |
| `ip_inventory_reports` | list of str | `[inventory_json, inventory_csv, inventory_txt, inventory_html, subnets_csv, issues_md,
  issues_csv]` | Built-in reports to render. |
| `ip_inventory_report_custom` | list of dict | `[]` | Extra reports (`name`, `template`, `basename`, `ext`, optional `requires`). |
| `ip_inventory_report_timestamped` | bool | `true` | Append a timestamp to file names. |
| `ip_inventory_csv_bom` | bool | `true` | Write a UTF-8 BOM at the start of CSV files. |
| `ip_inventory_report_print_summary` | bool | `true` | Print the run summary. |
| `ip_inventory_report_txt_hostname_width` | int | `45` | Hostname column width in the text report. |
| `ip_inventory_report_set_stats` | bool | `true` | Publish a compact run summary (`ip_inventory_summary`) with `ansible.builtin.set_stats`. |

## Example playbook

```yaml
- name: Render only the CSV and HTML reports, without timestamps
  ansible.builtin.include_role:
    name: lennysh.ip_inventory.report
  vars:
    ip_inventory_reports: [inventory_csv, inventory_html]
    ip_inventory_report_timestamped: false
    ip_inventory_output_dir: /tmp/ip-inventory

- name: Deliver them however you like
  ansible.builtin.debug:
    var: ip_inventory_report_files
```

## License

GPL-3.0-or-later

## Author

Lenny Shirley (@lennysh)
