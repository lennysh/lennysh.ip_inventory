# lennysh.ip_inventory.collect_opnsense

Collect IP observations from OPNsense.

Runs `lennysh.ip_inventory.opnsense_info` to read interface subnets, VLAN definitions and the ARP table (optionally DHCP leases, Kea reservations and Unbound overrides), applies include/exclude rules and appends the records to `ip_inventory_observations`.

See the [collection README](../../README.md) for how the roles fit together.

## Requirements

Network access from the host running the play to the source API. Secrets can come from Ansible Vault variables or the environment variables noted below.

## Role variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ip_inventory_opnsense_url` | str |  | OPNsense base URL. Falls back to `OPNSENSE_URL`. |
| `ip_inventory_opnsense_api_key` | str |  | API key. Falls back to `OPNSENSE_API_KEY`. Store it in Ansible Vault. |
| `ip_inventory_opnsense_api_secret` | str |  | API secret. Falls back to `OPNSENSE_API_SECRET`. Store it in Ansible Vault. |
| `ip_inventory_opnsense_validate_certs` | bool | `false` | Verify TLS certificates. |
| `ip_inventory_opnsense_timeout` | int | `30` | HTTP timeout in seconds. |
| `ip_inventory_opnsense_dhcp_backend` | str | `auto` | DHCP backend for lease/reservation collection (auto, kea, isc). |
| `ip_inventory_opnsense_collect` | dict | `{}` | Datasets to collect, merged over the module defaults (arp_table, interfaces, vlans, dhcp_leases, dhcp_static, unbound_overrides). |
| `ip_inventory_opnsense_filters` | dict | `{}` | Per-source include/exclude rules, stacked on `ip_inventory_filters`. |
| `ip_inventory_filters` | dict | `{}` | Global include/exclude rules applied to every source. |
| `ip_inventory_ignore_source_errors` | bool | `false` | Record a failure in `ip_inventory_source_stats` and continue instead of failing the play. |

## Example playbook

```yaml
- name: Collect from OPNsense
  hosts: localhost
  gather_facts: false
  vars:
    ip_inventory_opnsense_url: https://opnsense.example.com
    ip_inventory_opnsense_api_key: "{{ vault_opnsense_api_key }}"
    ip_inventory_opnsense_api_secret: "{{ vault_opnsense_api_secret }}"
  roles:
    - role: lennysh.ip_inventory.collect_opnsense

  post_tasks:
    - name: Show what was collected
      ansible.builtin.debug:
        msg: "{{ ip_inventory_source_stats }}"
```

## License

GPL-3.0-or-later

## Author

Lenny Shirley (@lennysh)
