# Nutanix Automation

Python scripts for automating Nutanix Prism Central operations via the v4 API. Covers VPC networking, BGP gateways, and VM power management.

## Requirements

- Python 3.10+
- Nutanix Prism Central with v4 API access

```bash
pip install -r requirements.txt
```

## Configuration

Create a `.env` file in the repo root:

```env
PC_IP=<prism-central-ip>
PC_USER=<username>
PC_PASSWORD=<password>
```

All scripts load credentials from this file automatically.

---

## Networking

### Full VPC Stack — `networking/create_full_vpc.py`

Creates a complete VPC networking stack in a single run. Edit `networking/create_full_vpc_config.yaml` to define your environment, then run:

```bash
python networking/create_full_vpc.py
```

**Execution order:**

| Step | Action |
|------|--------|
| 1 | VLAN subnets |
| 2 | Transit VPC |
| 3 | Transit overlay subnet |
| 4 | Child VPCs |
| 5 | Child overlay subnets |
| 6 | Local and remote BGP gateways |
| 7 | BGP sessions (waits for gateways to reach UP state) |

**Config sections:**

```yaml
cluster: "YOUR-CLUSTER"        # Prism Element cluster name

subnets:                        # VLAN subnets on the cluster
transit_vpcs:                   # Hub VPC connected to physical network
transit_overlays:               # Overlay subnet inside the Transit VPC
vpcs:                           # Child/tenant VPCs
overlays:                       # Workload subnets inside child VPCs
local_gateways:                 # On-cluster BGP gateway
remote_gateways:                # Upstream BGP peer
bgp_sessions:                   # One session per local gateway interface
```

---

### Delete VPC Stack — `networking/delete_full_vpc.py`

Tears down a VPC stack in reverse order (sessions → gateways → overlays → VPCs → subnets). Uses the same config file as `create_full_vpc.py`.

```bash
python networking/delete_full_vpc.py
```

---

### BGP Sessions — `networking/create_bgp_session.py`

Standalone script to create BGP sessions against existing gateways. Edit `networking/bgp_session_config.yaml`:

```yaml
bgp_sessions:
  - name: "MY-BGP-1"
    local_gateway: "LOCAL-GW-NAME"     # must exist in Prism Central
    remote_gateway: "REMOTE-GW-NAME"   # must exist in Prism Central
    local_interface_ip: "10.0.0.1"     # optional
    advertise_all_prefixes: true        # optional, default: false
```

```bash
python networking/create_bgp_session.py
```

---

### Individual Networking Scripts

These scripts handle single resource types and each has a matching YAML config:

| Script | Config | Purpose |
|--------|--------|---------|
| `create_external_subnet.py` | `subnet_config.yaml` | Create a VLAN subnet |
| `create_vpc.py` | `vpc_config.yaml` | Create a VPC |
| `create_overlay_subnet.py` | `overlay_config.yaml` | Create an overlay subnet |
| `create_gateway.py` | `gateway_config.yaml` | Create a BGP gateway |

---

## Externally Routable Prefixes (ERP)

Add or remove externally routable CIDRs on VPCs.

Edit `erp/add_erp.yaml` / `erp/remove_erp.yaml`:

```yaml
vpcs:
  - name: "Child-VPC-1"
    cidrs:
      - "10.0.0.0/24"
```

```bash
python erp/add_erp.py
python erp/remove_erp.py
```

---

## VM Management

Scripts in `vms/` operate against Prism Central. VMs are matched by name.

| Script | Action |
|--------|--------|
| `list_vms.py` | Print all VMs and their power state |
| `power_on_vm.py` | Power on a VM |
| `power_off_vm.py` | Power off a VM |
| `restart_vm.py` | Restart a VM |

```bash
python vms/list_vms.py
python vms/power_off_vm.py   # prompts for VM name
```

---

## Project Structure

```
.
├── client.py                        # Shared Nutanix API client
├── requirements.txt
├── .env                             # Credentials (not committed)
├── networking/
│   ├── create_full_vpc.py           # Full stack creation
│   ├── create_full_vpc_config.yaml
│   ├── delete_full_vpc.py           # Full stack teardown
│   ├── create_bgp_session.py
│   ├── bgp_session_config.yaml
│   ├── create_external_subnet.py
│   ├── create_vpc.py
│   ├── create_overlay_subnet.py
│   └── create_gateway.py
├── erp/
│   ├── add_erp.py
│   └── remove_erp.py
└── vms/
    ├── list_vms.py
    ├── power_on_vm.py
    ├── power_off_vm.py
    └── restart_vm.py
```
