# lennysh.ip_inventory.collect_proxmox

Collect IP observations from Proxmox VE.

Runs `lennysh.ip_inventory.proxmox_info` to read QEMU guest-agent IPs, LXC runtime IPs and static IPs from guest config, applies include/exclude rules and appends the records to `ip_inventory_observations`.

See the [collection README](../../README.md) for how the roles fit together.

## Requirements

Network access from the host running the play to the source API. Secrets can come from Ansible Vault variables or the environment variables noted below.

## Role variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ip_inventory_proxmox_url` | str |  | Proxmox base URL, e.g. https://pve.example.com:8006. Falls back to `PROXMOX_URL`. |
| `ip_inventory_proxmox_token_id` | str |  | API token ID (user@realm!name). Falls back to `PROXMOX_TOKEN_ID`. |
| `ip_inventory_proxmox_token_secret` | str |  | API token secret. Falls back to `PROXMOX_TOKEN_SECRET`. Store it in Ansible Vault. |
| `ip_inventory_proxmox_validate_certs` | bool | `false` | Verify TLS certificates. |
| `ip_inventory_proxmox_timeout` | int | `30` | HTTP timeout in seconds. |
| `ip_inventory_proxmox_use_guest_agent` | bool | `true` | Query the QEMU guest agent of running VMs. |
| `ip_inventory_proxmox_filters` | dict | `{}` | Per-source include/exclude rules, stacked on `ip_inventory_filters`. |
| `ip_inventory_filters` | dict | `{}` | Global include/exclude rules applied to every source. |
| `ip_inventory_ignore_source_errors` | bool | `false` | Record a failure in `ip_inventory_source_stats` and continue instead of failing the play. |

## Example playbook

```yaml
- name: Collect from Proxmox VE
  hosts: localhost
  gather_facts: false
  vars:
    ip_inventory_proxmox_url: https://proxmox.example.com:8006
    ip_inventory_proxmox_token_id: ip-inventory@pam!inventory
    ip_inventory_proxmox_token_secret: "{{ vault_proxmox_token_secret }}"
  roles:
    - role: lennysh.ip_inventory.collect_proxmox

  post_tasks:
    - name: Show what was collected
      ansible.builtin.debug:
        msg: "{{ ip_inventory_source_stats }}"
```

## License

GPL-3.0-or-later

## Author

Lenny Shirley (@lennysh)
