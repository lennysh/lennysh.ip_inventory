# lennysh.ip_inventory.collect_common

Shared helper for the collect_* roles (use tasks_from add.yml).

Fails with usage help. Use `tasks_from=add.yml`.

Called by every `collect_<source>` role after running its `<source>_info` module.

Applies the global `ip_inventory_filters` plus per-source rules, then appends to `ip_inventory_observations` and updates `ip_inventory_source_stats`.

See the [collection README](../../README.md) for how the roles fit together.

## Requirements

## Role variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `collect_common_source` | str | **required** | Source name, used for per-source filters and stats. |
| `collect_common_result` | dict | **required** | Registered result of the collector module (needs `records`). |
| `collect_common_filters` | dict | `{}` | Per-source include/exclude rules. |
| `ip_inventory_filters` | dict | `{}` | Global include/exclude rules applied to every source. |

## Example playbook

```yaml
# In a collect_<source> role, after running the source's *_info module:
- name: Filter and add the records
  ansible.builtin.include_role:
    name: lennysh.ip_inventory.collect_common
    tasks_from: add.yml
  vars:
    collect_common_source: netbox
    collect_common_result: "{{ _netbox_result }}"
    collect_common_filters: "{{ ip_inventory_netbox_filters | default({}) }}"
```

## License

GPL-3.0-or-later

## Author

Lenny Shirley (@lennysh)
