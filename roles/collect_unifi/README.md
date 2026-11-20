# lennysh.ip_inventory.collect_unifi

Collect IP observations from UniFi Network.

Runs `lennysh.ip_inventory.unifi_info` to read active clients, known clients and adopted devices, applies include/exclude rules and appends the records to `ip_inventory_observations`.

See the [collection README](../../README.md) for how the roles fit together.

## Requirements

Network access from the host running the play to the source API. Secrets can come from Ansible Vault variables or the environment variables noted below.

## Role variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ip_inventory_unifi_url` | str |  | UniFi console/controller URL. Falls back to `UNIFI_URL`. |
| `ip_inventory_unifi_api_key` | str |  | API key (recommended on UniFi OS). Falls back to `UNIFI_API_KEY`. Store it in Ansible Vault. |
| `ip_inventory_unifi_username` | str |  | Local admin username when no API key is used. Falls back to `UNIFI_USERNAME`. |
| `ip_inventory_unifi_password` | str |  | Password. Falls back to `UNIFI_PASSWORD`. |
| `ip_inventory_unifi_site` | str | `default` | UniFi site name. |
| `ip_inventory_unifi_unifi_os` | bool | `true` | UniFi OS console (true) or legacy Network Application (false). |
| `ip_inventory_unifi_validate_certs` | bool | `false` | Verify TLS certificates. |
| `ip_inventory_unifi_timeout` | int | `30` | HTTP timeout in seconds. |
| `ip_inventory_unifi_collect` | dict | `{}` | Datasets to collect (active_clients, known_clients, devices). |
| `ip_inventory_unifi_filters` | dict | `{}` | Per-source include/exclude rules, stacked on `ip_inventory_filters`. |
| `ip_inventory_filters` | dict | `{}` | Global include/exclude rules applied to every source. |
| `ip_inventory_ignore_source_errors` | bool | `false` | Record a failure in `ip_inventory_source_stats` and continue instead of failing the play. |

## Example playbook

```yaml
- name: Collect from UniFi Network
  hosts: localhost
  gather_facts: false
  vars:
    ip_inventory_unifi_url: https://unifi.example.com
    ip_inventory_unifi_api_key: "{{ vault_unifi_api_key }}"
  roles:
    - role: lennysh.ip_inventory.collect_unifi

  post_tasks:
    - name: Show what was collected
      ansible.builtin.debug:
        msg: "{{ ip_inventory_source_stats }}"
```

## License

GPL-3.0-or-later

## Author

Lenny Shirley (@lennysh)
