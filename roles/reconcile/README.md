# lennysh.ip_inventory.reconcile

Merge collected observations into one row per IP.

Reads `ip_inventory_observations` (filled by the `collect_*` roles), merges them by IP, folds VLAN definitions into subnets and enriches every host with subnet/VLAN data.

Sets `ip_inventory_hosts`, `ip_inventory_subnets` and `ip_inventory_orphan_vlans`.

See the [collection README](../../README.md) for how the roles fit together.

## Role variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ip_inventory_observations` | list of dict | `[]` | Filtered observation records. |
| `ip_inventory_raw` | bool | `false` | Do not merge; publish every observation as its own row. |

## Example playbook

```yaml
- name: Collect from Technitium only, then merge
  hosts: localhost
  gather_facts: false
  tasks:
    - name: Collect
      ansible.builtin.include_role:
        name: lennysh.ip_inventory.collect_technitium
    - name: Reconcile
      ansible.builtin.include_role:
        name: lennysh.ip_inventory.reconcile
    - name: Show the merged hosts
      ansible.builtin.debug:
        var: ip_inventory_hosts | map(attribute='ip') | list
```

## License

GPL-3.0-or-later

## Author

Lenny Shirley (@lennysh)
