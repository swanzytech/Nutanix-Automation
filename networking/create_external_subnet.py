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

subnets = config.get("subnets", [])

if not subnets:
    print("No subnets found in subnet_config.yaml")
    exit(1)

# --------------------------------------------------
# List clusters so user can pick one
# --------------------------------------------------
print("\nFetching clusters...")
clusters = client.get("/clustermgmt/v4.0/config/clusters")

print(f"\n{'#':<4} {'Name':<30} {'ExtId':<40}")
print("-" * 75)
for i, c in enumerate(clusters):
    print(f"{i:<4} {c.get('name',''):<30} {c.get('extId',''):<40}")

print()
choice         = int(input("Select cluster #: "))
cluster_ext_id = clusters[choice].get("extId")

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