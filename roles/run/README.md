# lennysh.ip_inventory.run

Run the whole IP inventory pipeline.

Runs the `collect_<source>` role for each entry in `ip_inventory_sources`, then the `reconcile`, `reachability`, `issues` and `report` roles.

Every stage reads and writes `ip_inventory_*` facts, so you can also call the roles individually or insert your own tasks between them.

Each role validates its own variables; see their argument specs for connection, ping, issue and report options.

See the [collection README](../../README.md) for how the roles fit together.

## Requirements

The `ping` binary on the host running the play (for the reachability checks).

## Role variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ip_inventory_sources` | list of str | `[opnsense, technitium, proxmox]` | Sources to collect. Short names map to `lennysh.ip_inventory.collect_<name>`; a fully-qualified role name is used as-is. |
| `ip_inventory_filters` | dict | `{}` | Global include/exclude rules applied to every source. |
| `ip_inventory_ignore_source_errors` | bool | `false` | Continue when a source fails. |
| `ip_inventory_raw` | bool | `false` | Report raw observations without merging. |
| `ip_inventory_reachability_enabled` | bool | `true` | Run the `reachability` role (ping and optional sweep). |
| `ip_inventory_report_enabled` | bool | `true` | Run the `report` role. |

## Example playbook

```yaml
- name: Collect, reconcile, ping, analyze and report
  hosts: localhost
  gather_facts: false
  vars:
    ip_inventory_sources: [opnsense, technitium, proxmox]
    ip_inventory_opnsense_url: https://opnsense.example.com
    ip_inventory_technitium_url: http://technitium.example.com:5380
    ip_inventory_proxmox_url: https://proxmox.example.com:8006
    ip_inventory_proxmox_token_id: ip-inventory@pam!inventory
    # secrets: Ansible Vault vars or OPNSENSE_API_KEY / TECHNITIUM_TOKEN / PROXMOX_TOKEN_SECRET ...
  roles:
    - role: lennysh.ip_inventory.run
```

## License

GPL-3.0-or-later

## Author

Lenny Shirley (@lennysh)
