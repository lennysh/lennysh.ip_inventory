# lennysh.ip_inventory.collect_technitium

Collect IP observations from Technitium DNS.

Runs `lennysh.ip_inventory.technitium_info` to read A/ANAME/CNAME/PTR zone records, DHCP leases and reservations, applies include/exclude rules and appends the records to `ip_inventory_observations`.

See the [collection README](../../README.md) for how the roles fit together.

## Requirements

Network access from the host running the play to the source API. Secrets can come from Ansible Vault variables or the environment variables noted below.

## Role variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ip_inventory_technitium_url` | str |  | Technitium base URL, e.g. http://dns.example.com:5380. Falls back to `TECHNITIUM_URL`. |
| `ip_inventory_technitium_token` | str |  | API token. Falls back to `TECHNITIUM_TOKEN`. Store it in Ansible Vault. |
| `ip_inventory_technitium_user` | str |  | Username, used when no token is set. Falls back to `TECHNITIUM_USER`. |
| `ip_inventory_technitium_password` | str |  | Password. Falls back to `TECHNITIUM_PASSWORD`. |
| `ip_inventory_technitium_validate_certs` | bool | `true` | Verify TLS certificates. |
| `ip_inventory_technitium_timeout` | int | `30` | HTTP timeout in seconds. |
| `ip_inventory_technitium_collect` | dict | `{}` | Datasets to collect (dns_records, dns_cnames, dns_ptrs, dhcp_leases, dhcp_scopes). |
| `ip_inventory_technitium_filters` | dict | `{}` | Per-source include/exclude rules, stacked on `ip_inventory_filters`. |
| `ip_inventory_filters` | dict | `{}` | Global include/exclude rules applied to every source. |
| `ip_inventory_ignore_source_errors` | bool | `false` | Record a failure in `ip_inventory_source_stats` and continue instead of failing the play. |

## Example playbook

```yaml
- name: Collect from Technitium DNS
  hosts: localhost
  gather_facts: false
  vars:
    ip_inventory_technitium_url: http://technitium.example.com:5380
    ip_inventory_technitium_token: "{{ vault_technitium_token }}"
  roles:
    - role: lennysh.ip_inventory.collect_technitium

  post_tasks:
    - name: Show what was collected
      ansible.builtin.debug:
        msg: "{{ ip_inventory_source_stats }}"
```

## License

GPL-3.0-or-later

## Author

Lenny Shirley (@lennysh)
