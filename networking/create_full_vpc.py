import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from client import NutanixClient
import uuid
import yaml
import time

_here = os.path.dirname(os.path.abspath(__file__))

client = NutanixClient()

# --------------------------------------------------
# Load config
# --------------------------------------------------
with open(os.path.join(_here, "create_full_vpc_config.yaml"), "r") as f:
    config = yaml.safe_load(f)

subnets_cfg          = config.get("subnets", [])
transit_vpcs_cfg     = config.get("transit_vpcs", [])
transit_overlays_cfg = config.get("transit_overlays", [])
vpcs_cfg             = config.get("vpcs", [])
overlays_cfg         = config.get("overlays", [])
local_gateways       = config.get("local_gateways", [])
remote_gateways      = config.get("remote_gateways", [])

# --------------------------------------------------
# Fetch shared resources up front
# --------------------------------------------------
print("Fetching clusters...")
all_clusters = client.get("/clustermgmt/v4.0/config/clusters")
clusters_map = {c.get("name"): c.get("extId") for c in all_clusters}

print("Fetching virtual switches...")
switches = client.get("/networking/v4.0/config/virtual-switches")
vs0 = next((s for s in switches if s.get("name") == "vs0"), None)
if not vs0:
    print("ERROR: vs0 virtual switch not found")
    exit(1)
vs_ext_id = vs0.get("extId")
print(f"Using virtual switch: vs0 ({vs_ext_id})")

# --------------------------------------------------
# Utilities
# --------------------------------------------------
def ipv4(value, prefix=32):
    return {"value": value, "prefixLength": prefix}

def ntnx_post(url, payload):
    r = client.session.post(
        f"{client.base_url}{url}",
        json=payload,
        headers={"Ntnx-Request-Id": str(uuid.uuid4())}
    )
    if r.status_code in (200, 201, 202):
        print("  Success!")
        task_id = r.json().get("data", {}).get("extId")
        if task_id:
            print(f"  Task ExtId: {task_id}")
        return task_id or True
    print(f"  Failed: {r.status_code} — {r.text}")
    return None


def wait_for_tasks(task_ids, poll_interval=5, timeout=300):
    pending = [t for t in task_ids if t and t is not True]
    if not pending:
        return
    print(f"\nWaiting for {len(pending)} task(s) to complete...")
    deadline = time.time() + timeout
    while pending and time.time() < deadline:
        still_pending = []
        for task_id in pending:
            try:
                data = client.get(f"/prism/v4.0/config/tasks/{task_id}")
                status = data.get("status", "RUNNING") if isinstance(data, dict) else "RUNNING"
            except Exception:
                status = "RUNNING"
            if status in ("SUCCEEDED", "FAILED", "ABORTED", "CANCELED"):
                mark = "OK" if status == "SUCCEEDED" else "FAIL"
                print(f"  [{mark}] {task_id} — {status}")
            else:
                still_pending.append(task_id)
        pending = still_pending
        if pending:
            time.sleep(poll_interval)
    if pending:
        print(f"  WARNING: {len(pending)} task(s) did not finish within {timeout}s")

def fetch_map(endpoint):
    return {item.get("name"): item.get("extId") for item in client.get(endpoint)}

def step(n, label):
    print(f"\n{'='*60}")
    print(f"STEP {n}: {label}")
    print(f"{'='*60}\n")

# --------------------------------------------------
# Resource creators
# --------------------------------------------------
def create_vlan_subnet(subnet, cluster_ext_id):
    is_external = bool(subnet.get("is_external", False))
    payload = {
        "name":                   subnet["name"],
        "subnetType":             "VLAN",
        "networkId":              subnet["vlan_id"],
        "isExternal":             is_external,
        "clusterReference":       cluster_ext_id,
        "virtualSwitchReference": vs_ext_id,
        "ipConfig": [
            {
                "ipv4": {
                    "defaultGatewayIp": ipv4(subnet["gateway_ip"]),
                    "ipSubnet": {
                        "ip":           ipv4(subnet["network_ip"]),
                        "prefixLength": subnet["prefix"]
                    },
                    "poolList": [
                        {"startIp": ipv4(subnet["pool_start"]), "endIp": ipv4(subnet["pool_end"])}
                    ]
                }
            }
        ]
    }
    if is_external:
        payload["isNatEnabled"] = False

    print(f"Creating '{subnet['name']}' (VLAN {subnet['vlan_id']}, External: {is_external})...")
    return ntnx_post("/networking/v4.0/config/subnets", payload)


def create_vpc(vpc, subnets_map):
    vpc_name      = vpc["name"]
    ext_subnet    = vpc["external_subnet"]
    cidr          = vpc.get("routable_cidr")
    vpc_type      = vpc.get("vpc_type", "REGULAR").upper()
    subnet_ext_id = subnets_map.get(ext_subnet)

    if not subnet_ext_id:
        print(f"Skipping '{vpc_name}' — subnet '{ext_subnet}' not found in Prism")
        return

    payload = {
        "name":            vpc_name,
        "vpcType":         vpc_type,
        "externalSubnets": [{"subnetReference": subnet_ext_id}]
    }
    if cidr:
        cidr_ip, cidr_prefix = cidr.split("/")
        payload["externallyRoutablePrefixes"] = [
            {"ipv4": {"ip": ipv4(cidr_ip), "prefixLength": int(cidr_prefix)}}
        ]

    print(f"Creating VPC '{vpc_name}' (type: {vpc_type}, subnet: {ext_subnet}, CIDR: {cidr or 'none'})...")
    return ntnx_post("/networking/v4.0/config/vpcs", payload)


def create_overlay(overlay, vpcs_map):
    subnet_name = overlay["name"]
    vpc_name    = overlay["vpc"]
    is_external = bool(overlay.get("is_external", False))
    vpc_ext_id  = vpcs_map.get(vpc_name)

    if not vpc_ext_id:
        print(f"Skipping '{subnet_name}' — VPC '{vpc_name}' not found in Prism")
        return

    ipv4_cfg = {
        "defaultGatewayIp": ipv4(overlay["gateway_ip"]),
        "ipSubnet": {
            "ip":           ipv4(overlay["network_ip"]),
            "prefixLength": overlay["prefix"]
        }
    }
    if overlay.get("pool_start") and overlay.get("pool_end"):
        ipv4_cfg["poolList"] = [
            {"startIp": ipv4(overlay["pool_start"]), "endIp": ipv4(overlay["pool_end"])}
        ]

    payload = {
        "name":         subnet_name,
        "subnetType":   "OVERLAY",
        "vpcReference": vpc_ext_id,
        "isExternal":   is_external,
        "ipConfig":     [{"ipv4": ipv4_cfg}]
    }
    if is_external:
        payload["isNatEnabled"] = False

    print(f"Creating overlay '{subnet_name}' in VPC '{vpc_name}' (External: {is_external})...")
    return ntnx_post("/networking/v4.0/config/subnets", payload)


# --------------------------------------------------
# STEP 1: Create VLAN subnets
# --------------------------------------------------
if subnets_cfg:
    step(1, f"Creating {len(subnets_cfg)} VLAN subnet(s)")

    print(f"{'#':<4} {'Name':<30} {'ExtId':<40}")
    print("-" * 75)
    for i, c in enumerate(all_clusters):
        print(f"{i:<4} {c.get('name',''):<30} {c.get('extId',''):<40}")
    print()
    choice         = int(input("Select cluster # for VLAN subnets: "))
    cluster_ext_id = all_clusters[choice].get("extId")

    tasks = [create_vlan_subnet(subnet, cluster_ext_id) for subnet in subnets_cfg]
    wait_for_tasks(tasks)

# --------------------------------------------------
# STEP 2: Create transit VPCs
# --------------------------------------------------
if transit_vpcs_cfg:
    step(2, f"Creating {len(transit_vpcs_cfg)} transit VPC(s)")
    print("Refreshing subnets...")
    subnets_map = fetch_map("/networking/v4.0/config/subnets")
    tasks = [create_vpc(vpc, subnets_map) for vpc in transit_vpcs_cfg]
    wait_for_tasks(tasks)

# --------------------------------------------------
# STEP 3: Create transit overlays
# --------------------------------------------------
if transit_overlays_cfg:
    step(3, f"Creating {len(transit_overlays_cfg)} transit overlay(s)")
    print("Refreshing VPCs...")
    vpcs_map = fetch_map("/networking/v4.0/config/vpcs")
    tasks = [create_overlay(overlay, vpcs_map) for overlay in transit_overlays_cfg]
    wait_for_tasks(tasks)

# --------------------------------------------------
# STEP 4: Create child VPCs
# --------------------------------------------------
if vpcs_cfg:
    step(4, f"Creating {len(vpcs_cfg)} child VPC(s)")
    print("Refreshing subnets...")
    subnets_map = fetch_map("/networking/v4.0/config/subnets")
    tasks = [create_vpc(vpc, subnets_map) for vpc in vpcs_cfg]
    wait_for_tasks(tasks)

# --------------------------------------------------
# STEP 5: Create child overlay subnets
# --------------------------------------------------
if overlays_cfg:
    step(5, f"Creating {len(overlays_cfg)} child overlay subnet(s)")
    print("Refreshing VPCs...")
    vpcs_map = fetch_map("/networking/v4.0/config/vpcs")
    tasks = [create_overlay(overlay, vpcs_map) for overlay in overlays_cfg]
    wait_for_tasks(tasks)

# --------------------------------------------------
# STEP 6: Create gateways
# --------------------------------------------------
if local_gateways or remote_gateways:
    step(6, f"Creating {len(local_gateways)} local / {len(remote_gateways)} remote gateway(s)")
    print("Refreshing subnets and VPCs...")
    subnets_map = fetch_map("/networking/v4.0/config/subnets")
    vpcs_map    = fetch_map("/networking/v4.0/config/vpcs")

    for gw in local_gateways:
        name           = gw["name"]
        subnet_id      = subnets_map.get(gw["subnet"])
        vpc_id         = vpcs_map.get(gw["vpc"])
        cluster_ext_id = clusters_map.get(gw["cluster"])

        if not subnet_id:
            print(f"Skipping '{name}' — subnet '{gw['subnet']}' not found")
            continue
        if not vpc_id:
            print(f"Skipping '{name}' — VPC '{gw['vpc']}' not found")
            continue
        if not cluster_ext_id:
            print(f"Skipping '{name}' — cluster '{gw['cluster']}' not found")
            continue

        prefix     = gw["prefix"]
        gateway_ip = gw["gateway_ip"]
        static_ips = gw["static_ips"]

        payload = {
            "name": name,
            "deployment": {
                "clusterReference": cluster_ext_id,
                "managementInterface": {
                    "subnetReference": subnet_id,
                    "address":         {"ipv4": ipv4(static_ips[0], prefix)},
                    "defaultGateway":  {"ipv4": ipv4(gateway_ip)}
                },
                "interfaces": [
                    {
                        "subnetReference":       subnet_id,
                        "ipAddress":             {"ipv4": ipv4(ip, prefix)},
                        "defaultGatewayAddress": {"ipv4": ipv4(gateway_ip, prefix)}
                    }
                    for ip in static_ips
                ],
                "shouldSynchronizeSystemNtpServers": True,
                "shouldSynchronizeSystemDnsServers": True
            },
            "services": {
                "$objectType": "networking.v4.config.LocalNetworkServices",
                "localBgpService": {
                    "vpcReference": vpc_id,
                    "asn":          gw["asn"]
                }
            }
        }

        print(f"Creating local gateway '{name}' (VPC: {gw['vpc']}, ASN: {gw['asn']})...")
        ntnx_post("/networking/v4.0/config/gateways", payload)
        time.sleep(2)

    for gw in remote_gateways:
        payload = {
            "name": gw["name"],
            "services": {
                "$objectType": "networking.v4.config.RemoteNetworkServices",
                "remoteBgpService": {
                    "address": {"ipv4": ipv4(gw["service_ip"])},
                    "asn":     gw["asn"]
                }
            }
        }

        print(f"Creating remote gateway '{gw['name']}' (IP: {gw['service_ip']}, ASN: {gw['asn']})...")
        ntnx_post("/networking/v4.0/config/gateways", payload)
        time.sleep(2)

print("\nDone!")
