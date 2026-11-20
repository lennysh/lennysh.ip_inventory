# Ansible Collection - lennysh.ip_inventory

[![CI](https://github.com/lennysh/lennysh.ip_inventory/actions/workflows/tests.yml/badge.svg?branch=devel)](https://github.com/lennysh/lennysh.ip_inventory/actions/workflows/tests.yml) [![Ansible Galaxy](https://img.shields.io/badge/galaxy-lennysh.ip__inventory-blue.svg?logo=ansible)](https://galaxy.ansible.com/ui/repo/published/lennysh/ip_inventory/) [![GitHub release](https://img.shields.io/github/v/release/lennysh/lennysh.ip_inventory?sort=semver)](https://github.com/lennysh/lennysh.ip_inventory/releases) [![ansible-core](https://img.shields.io/badge/ansible--core-%3E%3D2.16-blue.svg)](https://github.com/lennysh/lennysh.ip_inventory/blob/devel/meta/runtime.yml) [![GitHub license](https://img.shields.io/github/license/lennysh/lennysh.ip_inventory.svg)](https://github.com/lennysh/lennysh.ip_inventory/blob/devel/LICENSE) [![GitHub last commit](https://img.shields.io/github/last-commit/lennysh/lennysh.ip_inventory/devel.svg)](https://github.com/lennysh/lennysh.ip_inventory/commits/devel) [![GitHub issues](https://img.shields.io/github/issues/lennysh/lennysh.ip_inventory.svg)](https://github.com/lennysh/lennysh.ip_inventory/issues) [![Contributions welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg)](https://github.com/lennysh/lennysh.ip_inventory/blob/devel/.github/CONTRIBUTING.md)

Pull hostname and IP data from **OPNsense**, **Technitium DNS**, **Proxmox VE** and **UniFi Network**,
merge it into one row per IP, ping everything, flag anomalies, and write reports from Jinja2 templates.
The same data is also available as a **dynamic inventory**, grouped by subnet, VLAN, source, issue, and so on.

It solves the "I've lost track of my homelab" problem: DHCP leases, static reservations, DNS records, ARP
entries, VM guest-agent IPs and UniFi clients all land in one view, with the conflicts and stale entries flagged.

The collection is read-only. It never changes anything on your infrastructure, and it has no Python
dependencies beyond ansible-core.

## Contents

| Type | Name | Purpose |
|------|------|---------|
| Playbook | `lennysh.ip_inventory.run` | Whole pipeline: collect, reconcile, ping, analyze, report |
| Role | `run` | Orchestrates the roles below |
| Role | `collect_opnsense`, `collect_technitium`, `collect_proxmox`, `collect_unifi` | Collect observations from one source |
| Role | `collect_common` | Shared helper: filter and accumulate a collector's records |
| Role | `reconcile` | Merge observations into one row per IP, add subnet/VLAN data |
| Role | `reachability` | Ping known hosts, optional subnet sweep for unknown devices |
| Role | `issues` | MAC/hostname conflicts, stale DNS, unreachable hosts, ... |
| Role | `report` | Render JSON/CSV/TXT/HTML/Markdown reports from templates |
| Module | `opnsense_info`, `technitium_info`, `proxmox_info`, `unifi_info` | Read one source, return records |
| Module | `icmp_ping` | Concurrent ICMP ping of a list of IPs |
| Filter | `filter_records`, `reconcile`, `apply_ping`, `sweep_candidates`, `discovered`, `analyze_issues`, `issue_summary`, `issues_by_ip`, `dns_summary`, `sort_records`, `enrich_subnets`, `pingable_ips`, `csv_row` | The processing steps, usable in your own playbooks |
| Inventory | `lennysh.ip_inventory.ip_inventory` | Dynamic inventory built from the same pipeline |

Every plugin has full `ansible-doc` documentation (`ansible-doc -t filter lennysh.ip_inventory.reconcile`,
`ansible-doc -t inventory lennysh.ip_inventory.ip_inventory`, ...), and every role has an argument spec
(`ansible-doc -t role lennysh.ip_inventory.report`).

## Requirements

- ansible-core 2.16 or newer (the default in AAP 2.4 to 2.7 execution environments)
- The `ping` binary on the host running the play (for reachability checks)
- Network access from that host to the source APIs

## Install

```bash
ansible-galaxy collection install git+https://github.com/lennysh/lennysh.ip_inventory.git
# or, from a checkout:
ansible-galaxy collection build && ansible-galaxy collection install lennysh-ip_inventory-*.tar.gz
```

## Quick start (playbook and reports)

```bash
mkdir -p homelab/group_vars/all && cd homelab
cp <collection>/docs/examples/group_vars/all/ip_inventory.yml group_vars/all/
cp <collection>/docs/examples/group_vars/all/vault.yml.example group_vars/all/vault.yml
$EDITOR group_vars/all/ip_inventory.yml group_vars/all/vault.yml
ansible-vault encrypt group_vars/all/vault.yml

# group_vars next to an inventory or playbook are picked up automatically; with the
# collection playbook, pass them explicitly:
ansible-playbook lennysh.ip_inventory.run -e @group_vars/all/ip_inventory.yml -e @group_vars/all/vault.yml --ask-vault-pass
```

Reports are written to `./output/` with a timestamp in the file name:

| File | Content |
|------|---------|
| `inventory-<ts>.json` | `{generated_at, count, records: [...]}`, every merged row with all metadata |
| `inventory-<ts>.csv` | One row per IP; multi-value columns use `;`; all fields quoted, UTF-8 BOM |
| `inventory-<ts>.txt` | Plain-text table of every host (handy for `less` or a terminal) |
| `inventory-<ts>.html` | Self-contained page with summary cards, issues, hosts, subnets, live filter and sortable columns |
| `subnets-<ts>.csv` | Interface subnets with VLAN tag/name/parent, gateway, mask, broadcast (plus VLAN-only definitions) |
| `issues-<ts>.md` / `.csv` | Findings grouped by severity (written only when there are findings) |

A run summary (source stats, DNS summary, issue counts, high-severity findings, files written)
is printed at the end of the play.

### Common overrides

| Want to... | Pass |
|------------|------|
| Collect from some sources only | `-e '{"ip_inventory_sources": ["technitium"]}'` |
| Skip ping checks | `-e ip_inventory_ping_enabled=false` |
| Sweep subnets for unknown devices | `-e ip_inventory_discover_unknown=true` |
| See every raw observation, unmerged | `-e ip_inventory_raw=true` |
| Skip the issue analysis | `-e ip_inventory_issues_enabled=false` |
| Write to another directory, without timestamps | `-e ip_inventory_output_dir=DIR -e ip_inventory_report_timestamped=false` |

## Quick start (dynamic inventory)

```yaml
# homelab.ip_inventory.yml  (the file name must end in ip_inventory.yml)
plugin: lennysh.ip_inventory.ip_inventory
sources:
  opnsense:
    url: https://opnsense.example.com
  technitium:
    url: http://technitium.example.com:5380
  proxmox:
    url: https://proxmox.example.com:8006
    token_id: ip-inventory@pam!inventory
filters:
  include_networks: [192.168.*]
  exclude_interfaces: [lo0, wan]
hostname_strategy: short_hostname
cache: true
cache_plugin: ansible.builtin.jsonfile
cache_connection: ~/.cache/ansible-ip-inventory
```

```bash
export OPNSENSE_API_KEY=... OPNSENSE_API_SECRET=... TECHNITIUM_TOKEN=... PROXMOX_TOKEN_SECRET=...
ansible-inventory -i homelab.ip_inventory.yml --graph
ansible -i homelab.ip_inventory.yml 'vlan_iot:&issue_dns_only' --list-hosts
ansible-playbook -i homelab.ip_inventory.yml patch.yml --limit 'proxmox_qemu:&proxmox_tag_prod'
```

If `inventory/enable_plugins` is set in your `ansible.cfg`, add `lennysh.ip_inventory.ip_inventory` to it.

### Hosts

- One host per IP. With `hostname_strategy: hostname` (default) or `short_hostname` it is named after the
  primary hostname; hosts without a name, or whose name is already taken by another IP, are named by IP
  (the latter are also put in the `name_conflict` group).
- `ansible_host` is the IP. Everything else is under `ip_inventory_*`: `ip`, `hostname`, `hostnames`,
  `dns_names`, `cname_aliases`, `dns_only`, `mac`, `macs`, `sources`, `record_types`, `vlan`, `vlan_name`,
  `subnet`, `netmask`, `prefix_length`, `interface`, `ping_status`, `notes`, `issues`, `source_metadata`,
  plus `proxmox_vmid/node/vm_type/status/tags` and `unifi_model/type/essid/network/is_wired/...` when known.
- Subnet and VLAN groups carry `ip_inventory_subnet_*` group vars (`cidr`, `gateway`, `netmask`,
  `broadcast`, `vlan`, `vlan_name`, `vlan_parent`, `interface`), so every host can read for example
  `ip_inventory_subnet_gateway`.

### Built-in groups

| Group | Members |
|-------|---------|
| `source_<name>` | Seen by that source (`source_opnsense`, `source_proxmox`, ...) |
| `type_<record_type>` | Has that observation type (`type_arp`, `type_dhcp_reserved`, `type_vm_guest_agent`, ...) |
| `subnet_<cidr>` | Inside that OPNsense subnet (`subnet_192_168_20_0_24`) |
| `vlan_<name>` | Inside that VLAN's subnet (`vlan_iot`) |
| `interface_<name>` | Behind that OPNsense interface (`interface_opt1`) |
| `ping_up`, `ping_down` | With `ping: true` |
| `dns_only` | Only DNS evidence (stale-record candidates) |
| `discovered` | Found by the subnet sweep (`discover_unknown: true`) |
| `issue_<category>`, `issues_<severity>` | Has that finding (`issue_mac_conflict`, `issues_high`) |
| `proxmox_qemu`, `proxmox_lxc`, `proxmox_node_<node>`, `proxmox_tag_<tag>` | Proxmox guests |
| `unifi_device`, `unifi_client`, `unifi_wired`, `unifi_wireless` | UniFi devices and clients |
| `name_conflict` | Named by IP because another IP already had its hostname |

You can add your own with the standard `compose`, `groups` and `keyed_groups` options. Other options include
`group_prefix`, `vars_prefix`, `builtin_groups: false`, `ping`, `discover_unknown`, `ignore_source_errors`,
`global_vars` (run-wide subnets, findings and stats on the `all` group) and `issue_skip_checks`.
See `ansible-doc -t inventory lennysh.ip_inventory.ip_inventory` and
[docs/examples/homelab.ip_inventory.yml](docs/examples/homelab.ip_inventory.yml).

**Secrets in the inventory file:** string values may use Jinja (`"{{ lookup('env', 'X') }}"`), `${VAR}`
references, or inline `!vault` values. Each source also falls back to its usual environment variables.

## Configuration

### Sources

Variables are prefixed `ip_inventory_<source>_`. Empty values are omitted, so the module's environment
variable fallback applies.

| Source | Required | Environment fallbacks |
|--------|----------|----------------------|
| OPNsense | `url`, `api_key`, `api_secret` | `OPNSENSE_URL`, `OPNSENSE_API_KEY`, `OPNSENSE_API_SECRET` |
| Technitium | `url`, `token` or `user`/`password` | `TECHNITIUM_URL`, `TECHNITIUM_TOKEN`, `TECHNITIUM_USER`, `TECHNITIUM_PASSWORD` |
| Proxmox | `url`, `token_id`, `token_secret` | `PROXMOX_URL`, `PROXMOX_TOKEN_ID`, `PROXMOX_TOKEN_SECRET` |
| UniFi | `url`, `api_key` or `username`/`password` | `UNIFI_URL`, `UNIFI_API_KEY`, `UNIFI_USERNAME`, `UNIFI_PASSWORD` |

Each source also takes `validate_certs` (default `false`, except Technitium `true`), `timeout`, a `collect`
dict (which datasets to read) and a `filters` dict. Run `ansible-doc -t role lennysh.ip_inventory.collect_<source>`
for the full list.

<details>
<summary>API permissions per source</summary>

**OPNsense:** System > Access > Users: enable API access, create a key/secret, and grant
*Interfaces: Overview*, *Interfaces: VLANs* and *Diagnostics: ARP Table*. Only enable `collect.dhcp_leases` /
`dhcp_static` / `unbound_overrides` if OPNsense actually runs those services.
Endpoints: `/api/interfaces/overview/interfaces_info`, `/api/interfaces/vlan_settings/search_item`,
`/api/diagnostics/interface/get_arp` (optional: `/api/kea/leases4/search`, `/api/kea/dhcpv4/search_reservation`,
`/api/dhcpv4/leases/search_lease`, `/api/unbound/settings/search_host_override`).

**Technitium:** an API token (Users > API tokens) or user/password, with *Zones: View* and *DhcpServer: View*.
CNAMEs are resolved through to the target A record and attached to that IP; wildcard CNAMEs and
Forwarder/Stub/Secondary zones are skipped.

**Proxmox:** create a user and API token, and grant **PVE Auditor** on `/` (this includes VM.Audit and VM.Monitor,
which guest-agent IPs need). If a run reports 0 records although VMs exist, the token authenticated but cannot see
the VMs. The collector warns about this.

**UniFi:** an API key (Settings > Control Plane > Integrations) or a local admin account. Set `unifi_os: false` for
the legacy self-hosted Network Application.
</details>

### Filters

`ip_inventory_filters` applies to every source. `ip_inventory_<source>_filters` stacks extra excludes on top,
and a per-source `include_networks` replaces the global allow-list for that source.

```yaml
ip_inventory_filters:
  include_networks: [192.168.*]          # wildcard -> 192.168.0.0/16; CIDR also works; omit to allow all
  exclude_networks: [127.*, 172.17.*]
  exclude_interfaces: [lo0, wan]       # fnmatch on interface / identifier / vlan
  exclude_name_patterns: ["*docker*"]  # fnmatch (case-insensitive) on hostname / notes / description
  exclude_record_types: [dns_ptr]
```

### Reachability, issues, reports

| Variable | Default | Notes |
|----------|---------|-------|
| `ip_inventory_ping_enabled` | `true` | ICMP every known IP |
| `ip_inventory_ping_timeout` / `_concurrency` | `1.0` / `50` | |
| `ip_inventory_discover_unknown` | `false` | Sweep unused addresses in each subnet |
| `ip_inventory_discover_private_only` | `true` | |
| `ip_inventory_discover_max_hosts_per_subnet` | `512` | |
| `ip_inventory_issues_enabled` | `true` | |
| `ip_inventory_issues_checks` / `_skip_checks` | `[]` | Select checks |
| `ip_inventory_issues_fail_on` | `[]` | e.g. `[high]` fails the play: handy for scheduled jobs and CI |
| `ip_inventory_ignore_source_errors` | `false` | Continue when a source is down |
| `ip_inventory_output_dir` | `./output` | |
| `ip_inventory_reports` | all | `inventory_json`, `inventory_csv`, `inventory_txt`, `inventory_html`, `subnets_csv`, `issues_md`, `issues_csv` |
| `ip_inventory_report_custom` | `[]` | Your own templates, see below |
| `ip_inventory_report_timestamped` | `true` | `false` writes stable names |
| `ip_inventory_report_set_stats` | `true` | Publish `ip_inventory_summary` as job artifacts |

## Issue checks

| Category | Severity | What it catches |
|----------|----------|-----------------|
| `mac_conflict` | high | One IP with multiple MACs |
| `mac_shared` | high/medium | One MAC on multiple IPs (router gateways are downgraded to info) |
| `hostname_shared` | medium | Same hostname on multiple IPs (multi-homed DNS/router patterns become info) |
| `dns_only` | medium | DNS/PTR with no DHCP/ARP/UniFi/Proxmox evidence |
| `discovered` | medium | Ping-sweep responder missing from every source |
| `dns_unreachable` | low | DNS exists but ICMP is down |
| `active_unreachable` | low | ARP/UniFi/VM saw the host, but ping failed |
| `missing_mac` | low | Live/DHCP observation without a MAC |
| `cname_aliases` | info | Hosts with many CNAME aliases (audit aid) |

## How it fits together

```
collect_<source> ──► ip_inventory_observations   (filtered records, common schema)
        │
reconcile ─────────► ip_inventory_hosts / _subnets / _orphan_vlans
        │
reachability ──────► ping_status on hosts, + ip_inventory_discovered
        │
issues ────────────► ip_inventory_findings / _issue_summary
        │
report ────────────► templates ─► output/*.json|csv|txt|html|md
```

Every stage reads and writes plain facts, so you can call the roles individually, add your own tasks between
them, or use the filters directly ([docs/examples/custom_pipeline.yml](docs/examples/custom_pipeline.yml)).
The inventory plugin runs the same Python steps (`plugins/module_utils/pipeline.py`) in-process.

## Ansible Automation Platform

To run it in AAP you need a custom execution environment (adds `ping`), a custom credential type for the API
secrets (it serves both job templates and inventory sources), a project and an inventory source. Since EE
containers are discarded after each job, the job's playbook delivers the reports (email, web server, ...);
see [docs/examples/deliver_reports.yml](docs/examples/deliver_reports.yml).
[docs/aap.md](docs/aap.md) walks through every step and includes the credential type, the EE definition,
a template project and an `infra.aap_configuration` CasC file.

## Extending

- **New source** (pfSense, Kea, NetBox, Omada, ...): one collector class, a short module and a role.
- **New issue check:** one function.
- **New report:** a Jinja2 template plus an entry in `ip_inventory_report_custom`, with no collection change needed.
- **Report delivery** (email, web server, ...) belongs in your playbook, after the roles: use `ip_inventory_report_files`
  and `ip_inventory_summary` ([docs/examples/deliver_reports.yml](docs/examples/deliver_reports.yml)).

See [docs/extending.md](docs/extending.md).

## Development

See [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md). Every pull request needs a changelog fragment in
`changelogs/fragments/` ([format](https://docs.ansible.com/ansible/latest/community/development_process.html#changelogs)).
`CHANGELOG.rst` is generated from the fragments at release time.

```bash
# ansible-test needs the collection inside an ansible_collections/<ns>/<name> tree
ansible-test sanity --venv --requirements
ansible-test units --venv --requirements

# End-to-end: roles, inventory plugin, loopback ICMP and the delivery example against a mock of
# all four source APIs and a local SMTP sink (needs the collection and community.general installed)
tests/e2e/run.sh
```

CI (`.github/workflows/tests.yml`) runs ansible-lint, sanity and unit tests across the supported ansible-core
versions (via tox-ansible, plus ansible-core 2.16), the end-to-end suite on ansible-core 2.16, 2.18 and 2.20,
a Galaxy import check and a changelog check. Releases (`release_manual.yml` for the first one,
`release_auto.yml` on a schedule afterwards) build the changelog, tag a GitHub release and publish to Galaxy.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
