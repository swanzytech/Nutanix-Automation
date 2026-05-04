import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from client import NutanixClient
import uuid
import yaml

_here = os.path.dirname(os.path.abspath(__file__))

client = NutanixClient()

# --------------------------------------------------
# Load config file
# --------------------------------------------------
with open(os.path.join(_here, "subnet_config.yaml"), "r") as f:
    config = yaml.safe_load(f)

cluster_name = config.get("cluster")
subnets      = config.get("subnets", [])

if not subnets:
    print("No subnets found in subnet_config.yaml")
    exit(1)

# --------------------------------------------------
# Resolve cluster by name
# --------------------------------------------------
print("\nFetching clusters...")
clusters       = client.get("/clustermgmt/v4.0/config/clusters")
clusters_map   = {c.get("name"): c.get("extId") for c in clusters}
cluster_ext_id = clusters_map.get(cluster_name)
if not cluster_ext_id:
    print(f"ERROR: cluster '{cluster_name}' not found in Prism")
    exit(1)
print(f"Using cluster: {cluster_name} ({cluster_ext_id})")

# --------------------------------------------------
# Get vs0 automatically
# --------------------------------------------------
switches  = client.get("/networking/v4.0/config/virtual-switches")
vs0       = next(s for s in switches if s.get("name") == "vs0")
vs_ext_id = vs0.get("extId")
print(f"\nUsing virtual switch: vs0 ({vs_ext_id})")

# --------------------------------------------------
# Create all subnets from config
# --------------------------------------------------
print(f"\nFound {len(subnets)} subnet(s) in config — creating all...\n")

for subnet in subnets:
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
                    "defaultGatewayIp": {
                        "value":        subnet["gateway_ip"],
                        "prefixLength": 32
                    },
                    "ipSubnet": {
                        "ip": {
                            "value":        subnet["network_ip"],
                            "prefixLength": 32
                        },
                        "prefixLength": subnet["prefix"]
                    },
                    "poolList": [
                        {
                            "startIp": {"value": subnet["pool_start"], "prefixLength": 32},
                            "endIp":   {"value": subnet["pool_end"],   "prefixLength": 32}
                        }
                    ]
                }
            }
        ]
    }

    # Only add isNatEnabled for external subnets
    if is_external:
        payload["isNatEnabled"] = False

    print(f"Creating '{subnet['name']}' (VLAN {subnet['vlan_id']}, External: {is_external})...")

    r = client.session.post(
        f"{client.base_url}/networking/v4.0/config/subnets",
        json=payload,
        headers={"Ntnx-Request-Id": str(uuid.uuid4())}
    )

    if r.status_code in (200, 202):
        print(f"  Success!")
    else:
        print(f"  Failed: {r.status_code}")
        print(f"  {r.text}")

print("\nDone!")