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
with open(os.path.join(_here, "overlay_config.yaml"), "r") as f:
    config = yaml.safe_load(f)

overlays = config.get("overlays", [])

if not overlays:
    print("No overlays found in overlay_config.yaml")
    exit(1)

# --------------------------------------------------
# Fetch existing VPCs from Prism
# --------------------------------------------------
print("Fetching VPCs...")
all_vpcs = client.get("/networking/v4.0/config/vpcs")
vpcs     = {v.get("name"): v.get("extId") for v in all_vpcs}

print(f"Found VPCs: {', '.join(vpcs.keys())}")

# --------------------------------------------------
# Create all overlay subnets from config
# --------------------------------------------------
print(f"\nFound {len(overlays)} overlay(s) in config — creating all...\n")

for overlay in overlays:
    subnet_name = overlay["name"]
    vpc_name    = overlay["vpc"]
    network_ip  = overlay["network_ip"]
    prefix      = overlay["prefix"]
    gateway_ip  = overlay["gateway_ip"]
    pool_start  = overlay.get("pool_start")
    pool_end    = overlay.get("pool_end")
    is_external = bool(overlay.get("is_external", False))

    # Look up VPC extId by name
    vpc_ext_id = vpcs.get(vpc_name)
    if not vpc_ext_id:
        print(f"Skipping '{subnet_name}' — VPC '{vpc_name}' not found in Prism")
        continue

    # Build ipv4 block
    ipv4 = {
        "defaultGatewayIp": {
            "value":        gateway_ip,
            "prefixLength": 32
        },
        "ipSubnet": {
            "ip": {
                "value":        network_ip,
                "prefixLength": 32
            },
            "prefixLength": prefix
        }
    }

    # Only add poolList if DHCP range is defined
    if pool_start and pool_end:
        ipv4["poolList"] = [
            {
                "startIp": {"value": pool_start, "prefixLength": 32},
                "endIp":   {"value": pool_end,   "prefixLength": 32}
            }
        ]

    payload = {
        "name":         subnet_name,
        "subnetType":   "OVERLAY",
        "vpcReference": vpc_ext_id,
        "isExternal":   is_external,
        "isNatEnabled": False,
        "ipConfig": [
            {
                "ipv4": ipv4
            }
        ]
    }

    print(f"Creating overlay '{subnet_name}' in VPC '{vpc_name}' (External: {is_external})...")

    r = client.session.post(
        f"{client.base_url}/networking/v4.0/config/subnets",
        json=payload,
        headers={"Ntnx-Request-Id": str(uuid.uuid4())}
    )

    if r.status_code in (200, 202):
        print(f"  Success!")
        data = r.json()
        print(f"  Task ExtId: {data.get('data', {}).get('extId', 'check Prism for task status')}")
    else:
        print(f"  Failed: {r.status_code}")
        print(f"  {r.text}")

print("\nDone!")