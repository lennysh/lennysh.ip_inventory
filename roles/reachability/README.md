# lennysh.ip_inventory.reachability

Ping known hosts and optionally sweep subnets for unknown ones.

Pings every IP in `ip_inventory_hosts` with `lennysh.ip_inventory.icmp_ping` and sets `ping_status`.

With `ip_inventory_discover_unknown`, pings the unused addresses of each collected subnet and adds responders as `discovered` rows (also published as `ip_inventory_discovered`).

Pings are sent from the host running the play, so run it somewhere that can reach your networks.

See the [collection README](../../README.md) for how the roles fit together.

## Requirements

The `ping` binary on the host running the play (for the reachability checks).

## Role variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ip_inventory_hosts` | list of dict | **required** | Reconciled host records (from the `reconcile` role). |
| `ip_inventory_subnets` | list of dict | `[]` | Subnet records used for the sweep. |
| `ip_inventory_ping_enabled` | bool | `true` | Ping known hosts. |
| `ip_inventory_ping_timeout` | float | `1.0` | Seconds to wait for each reply. |
| `ip_inventory_ping_concurrency` | int | `50` | Parallel pings. |
| `ip_inventory_discover_unknown` | bool | `false` | Sweep unused subnet addresses for unknown responders. |
| `ip_inventory_discover_private_only` | bool | `true` | Only sweep private and link-local subnets. |
| `ip_inventory_discover_max_hosts_per_subnet` | int | `512` | Skip subnets larger than this many usable addresses. |

## Example playbook

```yaml
- name: Ping known hosts and sweep subnets for unknown devices
  ansible.builtin.include_role:
    name: lennysh.ip_inventory.reachability
  vars:
    ip_inventory_discover_unknown: true
```

## License

GPL-3.0-or-later

## Author

Lenny Shirley (@lennysh)
