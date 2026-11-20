# Running lennysh.ip_inventory in Ansible Automation Platform

This guide covers the two ways to use the collection in AAP:

- **Job template**: the `run` pipeline on a schedule. It collects, reconciles, pings, finds issues and writes reports.
- **Inventory source**: the `ip_inventory` plugin. It turns your network into an AAP inventory, grouped by
  subnet, VLAN, source, issue, Proxmox node, and so on. Other job templates can then target it.

Everything below is also available as configuration as code for `infra.aap_configuration`:
[aap/casc/ip_inventory.yml](aap/casc/ip_inventory.yml).

## What you need

| Piece | Why |
|-------|-----|
| A custom **execution environment** | The stock EEs have no `ping` binary. The collection declares `iputils` for ansible-builder. |
| A custom **credential type** ("IP Inventory Sources") | Stores the four sources' API secrets encrypted, and injects them as environment variables |
| A **credential** of that type | Your actual secrets |
| A **project** | Git repo with the playbook, non-secret vars, and the inventory plugin file |
| An **inventory** + **inventory source** | Dynamic inventory from the plugin |
| An **inventory** with `localhost` + a **job template** | Runs the report pipeline and delivers the reports (your playbook) |
| Optional: a **container group** (OpenShift) | Allows ICMP from unprivileged job pods |
| Optional: a **Machine credential** | If your playbook copies the reports to a server over SSH |

Requirements: AAP 2.4 or newer (ansible-core 2.16+ in the EE). The execution nodes (or job pods) must be able
to reach the four APIs, and the networks you want pinged.

```
                ┌────────── execution environment (job / inventory update) ──────────┐
 Credential ──► │ env: OPNSENSE_API_KEY, TECHNITIUM_TOKEN, PROXMOX_TOKEN_*, UNIFI_*   │
                │                                                                    │
 Project ─────► │ ip_inventory.yml ─► run role ─► collect ─► reconcile ─► ping ─►    │
 (git)          │ group_vars/all/ip_inventory.yml       issues ─► report ─► your     │──► email, web server, ...
                │                                       delivery tasks ─────────────►│
                │                                                                    │
                │ inventories/homelab.ip_inventory.yml ─► ip_inventory plugin ──────►│──► AAP inventory
                └────────────────────────────────────────────────────────────────────┘
```

Secrets only ever travel as environment variables. The modules and the inventory plugin fall back to them
whenever the matching option is unset. That is why one credential serves both the job template and the
inventory source. (AAP passes `extra_vars` injectors to job templates but not to inventory updates.)

## 1. Build the execution environment

[aap/execution-environment.yml](aap/execution-environment.yml) is a complete ansible-builder definition:
ee-minimal plus this collection. `iputils` comes in automatically through the collection's
`meta/execution-environment.yml` and `bindep.txt`.

```bash
podman login registry.redhat.io
ansible-builder build -f docs/aap/execution-environment.yml -t registry.example.com/ip-inventory-ee:1.0.0
podman push registry.example.com/ip-inventory-ee:1.0.0     # your private automation hub, quay.io, ...
```

- Pin `version:` to a tag or commit for reproducible images.
- Base image: `ee-minimal-rhel9:2.16` works on AAP 2.4 to 2.7. On AAP 2.7 you can use `:2.20`.
- If the collection is baked into the EE, the project doesn't need `collections/requirements.yml`. If both exist,
  the project's copy wins, which is handy for testing changes without rebuilding.

In AAP: **Automation Execution > Infrastructure > Execution Environments > Create**, with name `IP Inventory EE`,
the image above, and pull policy *Only pull the image if not present* (use *Always* for `:latest`-style tags).

## 2. Create the credential type

**Automation Execution > Infrastructure > Credential Types > Create credential type** (requires platform admin):

- Name: `IP Inventory Sources`
- Input configuration: [aap/credential_type_inputs.yml](aap/credential_type_inputs.yml)
- Injector configuration: [aap/credential_type_injectors.yml](aap/credential_type_injectors.yml)

| Field | Injected as | Used by |
|-------|-------------|---------|
| OPNsense API key / secret | `OPNSENSE_API_KEY`, `OPNSENSE_API_SECRET` | `opnsense_info`, plugin |
| Technitium token | `TECHNITIUM_TOKEN` | `technitium_info`, plugin |
| Technitium username / password | `TECHNITIUM_USER`, `TECHNITIUM_PASSWORD` | only when no token |
| Proxmox token ID / secret | `PROXMOX_TOKEN_ID`, `PROXMOX_TOKEN_SECRET` | `proxmox_info`, plugin |
| UniFi API key | `UNIFI_API_KEY` | `unifi_info`, plugin |
| UniFi username / password | `UNIFI_USERNAME`, `UNIFI_PASSWORD` | only when no API key |

All fields are optional, so fill in only the sources you use. A blank field ends up as an empty (or unset)
environment variable, which the collection treats as "not set": UniFi falls back to username/password,
Technitium to user/password. Sources you don't list in `ip_inventory_sources` / `sources:` are never contacted.

**Why one combined type instead of one per source?** An AAP inventory source accepts only a single credential,
and a job template accepts only one credential of each type.

## 3. Create the credential

**Automation Execution > Infrastructure > Credentials > Create credential** with type *IP Inventory Sources*,
and fill in the secrets for the sources you use, for example: OPNsense key and secret, Technitium token,
Proxmox token ID and secret, and a UniFi API key (or username and password).

## 4. Create the project

Copy [aap/project/](aap/project/) into a Git repository (a separate "homelab automation" repo works well):

```
ip_inventory.yml                        # job template playbook: runs the pipeline, then delivers the reports
group_vars/all/ip_inventory.yml         # non-secret settings: URLs, filters, ping, delivery targets
inventories/homelab.ip_inventory.yml    # inventory source file for the plugin
collections/requirements.yml            # pulls lennysh.ip_inventory at project sync (optional, see step 1)
```

Edit the URLs and filters, but **do not put secrets there**. Leaving `ip_inventory_<source>_api_key` and the like
unset is what makes the collection read the credential's environment variables.

> Wrap the run in your own play (as `ip_inventory.yml` does) rather than `import_playbook: lennysh.ip_inventory.run`.
> `group_vars/` is loaded relative to each play's playbook, so with `import_playbook` your project's `group_vars`
> would be ignored.

In AAP: **Projects > Create project**, Source control type *Git*, your repo URL, *Update revision on launch*,
default execution environment *IP Inventory EE*. If `collections/requirements.yml` points at a private repo or hub,
the organization needs a matching Galaxy or SCM credential.

## 5. Dynamic inventory (inventory source)

1. **Inventories > Create inventory**, for example `Homelab (ip_inventory)`. On OpenShift, set its instance group
   to the container group from [Ping from job pods](#ping-from-job-pods).
2. **Sources > Create source**:
   - Source: *Sourced from a Project*, project *Homelab IP Inventory*
   - Inventory file: `inventories/homelab.ip_inventory.yml`
   - Credential: *IP Inventory Sources - homelab*
   - Execution environment: *IP Inventory EE*
   - Options: *Overwrite*, *Overwrite variables*, *Update on launch* (with a cache timeout such as 900s)
3. Sync it. Hosts appear with `ansible_host` set to their IP and all data under `ip_inventory_*` host variables.
   Subnet and VLAN groups carry `ip_inventory_subnet_*` group variables.

Other job templates can now use limits like `vlan_vlan050_iot:&ping_down`, `proxmox_lxc`, `issue_dns_only` or
`unifi_wireless`. The file's notes:

- `cache: false`. AAP stores the imported inventory itself, and a file cache inside a throwaway EE does nothing.
- `ignore_source_errors: true`. One unreachable API doesn't empty the whole inventory.
- `ping: true` adds a few seconds. Leave `discover_unknown` off here, since the sweep takes about 90s. The job template runs it.
- `global_vars` (run-wide findings and subnets on the `all` group) is off by default and rarely needed in AAP.

## 6. Report job template

1. **Inventories > Create inventory** `IP Inventory Runner` with a single host `localhost`,
   variables `ansible_connection: local`. The built-in *Demo Inventory* also works.
2. **Templates > Create job template**:
   - Inventory: *IP Inventory Runner*, Project: *Homelab IP Inventory*, Playbook: `ip_inventory.yml`
   - Execution environment: *IP Inventory EE*
   - Credentials: *IP Inventory Sources - homelab* (plus a Machine credential if your delivery copies files over SSH)
   - Instance group: the container group (OpenShift only)

### Delivering the reports

The collection only renders the reports, into `ip_inventory_output_dir`. It lists their paths in
`ip_inventory_report_files` and a compact summary in `ip_inventory_summary`. Delivery is up to your playbook.
That matters in AAP because the EE container, and the files in it, is deleted when the job ends.

The template project's `ip_inventory.yml` (the same as
[examples/deliver_reports.yml](examples/deliver_reports.yml)) shows two common options, each switched on by
a variable in `group_vars/all/ip_inventory.yml`:

| Delivery | Variables | Needs |
|----------|-----------|-------|
| HTML report to a web server (`index.html`) | `report_web_host`, `report_web_root` | SSH to the web server: attach a Machine credential to the job template |
| Email with the HTML report as the body and the CSV/Markdown files attached | `report_mail_to`, `report_mail_from`, `report_smtp_host`, `report_smtp_port` | `community.general` in the EE or project requirements |

Swap in whatever you prefer: object storage, a Git commit, a chat message with `ip_inventory_summary`, and so on.

### Artifacts, notifications and workflows

- The `report` role publishes `ip_inventory_summary` with `set_stats`: counts, per-source stats, issue counts by
  severity and category, and report paths. It shows under the job's **Artifacts** and is passed to later
  workflow nodes as an extra variable. For example, a follow-up node could open a ticket when
  `ip_inventory_summary.issues.by_severity.high > 0`.
- `ip_inventory_issues_fail_on: [high]` makes the job fail on high-severity findings, so a normal
  *on failure* notification (email, Slack, ...) becomes an alert.
- `ip_inventory_ignore_source_errors: true` keeps the job green when one API is down. The failure is listed in
  the summary and in `ip_inventory_summary.sources`.

## 7. Schedules

Typical setup: sync the inventory source hourly, and run the report job nightly (with the subnet sweep).
Both are in the CasC file.

## Ping from job pods

The `ping` binary needs either the `NET_RAW` capability or an "unprivileged ICMP" group range.

- **VM-based / containerized installs (podman):** works out of the box, because podman sets
  `net.ipv4.ping_group_range=0 0` in containers.
- **OpenShift (operator installs):** job pods run as an arbitrary UID with all capabilities dropped, so every host
  shows `ping_status: down`. Fix it with a **container group** whose pod spec sets the Kubernetes *safe*
  sysctl below. No extra SCC privileges are needed. Then attach the group to the job template and to the
  inventory:

  ```yaml
  spec:
    securityContext:
      sysctls:
        - name: net.ipv4.ping_group_range
          value: "0 2147483647"
  ```

  The full pod spec is in the CasC file (`controller_instance_groups`). Start from AAP's default pod spec
  (shown when you create a container group) and add the `securityContext` block.
- If ICMP is simply blocked between the execution node and your networks (firewall), set
  `ip_inventory_ping_enabled: false` and `ping: false`. Everything except the reachability checks still works.

## Alternative: Ansible Vault instead of a credential type

You can commit an encrypted `group_vars/all/vault.yml` (see `docs/examples/group_vars/all/vault.yml.example`) and attach a *Vault*
credential to the job template. This works for the job template only: inventory sources can't decrypt
`unvault` lookups with an AAP Vault credential. The custom credential type covers both.

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `missing required arguments: url` | The project's `group_vars` weren't loaded. Use a real play (see step 4), not `import_playbook` |
| `missing required arguments: api_key` (or similar) | Credential not attached, or the field is blank for a source listed in `ip_inventory_sources` |
| `Collection lennysh.ip_inventory does not support Ansible version` | EE ansible-core is older than 2.16 |
| Every host `ping_status: down` | No `ping` in the EE (use the custom EE), OpenShift pod without the sysctl, or a firewall |
| `executable ping not found` / `Failed to find required executable "ping"` | The job is using a stock EE. Switch to *IP Inventory EE* |
| Inventory sync fails with *Unable to parse ... as an inventory source* | The file name must end in `ip_inventory.yml`, and the collection must be installed (EE or project requirements) |
| Inventory sync: one source missing | With `ignore_source_errors: true` the sync log shows a warning naming the failing source |
| Reports "missing" after the job | They were written inside the discarded EE. Deliver them from the playbook (step 6) |

## What was verified

- The EE definition builds with ansible-builder, `iputils` is pulled in through the collection's `bindep.txt`, and
  the full playbook and the inventory plugin run inside the image (ansible-core 2.16) against a mock of all four APIs.
- The template project was run inside that EE with credential-style environment variables (including blank
  fields), as both the job-template playbook and the inventory source. The delivery playbook's web-server
  copy was tested against a local stand-in host, and the email task against `tests/e2e/smtp_sink.py`
  (HTML body plus CSV/Markdown attachments).
- Unprivileged ICMP: with all capabilities dropped and a non-root UID, `ping` fails by default and works once the
  process's group is inside `net.ipv4.ping_group_range`. This was simulated locally with podman, not on an
  OpenShift cluster.
- The CasC field names were checked against `infra.aap_configuration` 3.8.0, but the file hasn't been applied to a
  live AAP.
