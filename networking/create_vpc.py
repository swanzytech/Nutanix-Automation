import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from client import NutanixClient
import uuid
import yaml
import json

_here = os.path.dirname(os.path.abspath(__file__))

client = NutanixClient()

# --------------------------------------------------
# Load config file
# --------------------------------------------------
with open(os.path.join(_here, "vpc_config.yaml"), "r") as f:
    config = yaml.safe_load(f)

vpcs = config.get("vpcs", [])

if not vpcs:
    print("No VPCs found in vpc_config.yaml")
    exit(1)

# --------------------------------------------------
# Fetch all subnets from Prism
# --------------------------------------------------
print("Fetching subnets...")
all_subnets = client.get("/networking/v4.0/config/subnets")
subnets     = {s.get("name"): s.get("extId") for s in all_subnets}

print(f"Found subnets: {', '.join(subnets.keys())}")

# --------------------------------------------------
# Create all VPCs from config
# --------------------------------------------------
print(f"\nFound {len(vpcs)} VPC(s) in config — creating all...\n")

for vpc in vpcs:
    vpc_name   = vpc["name"]
    ext_subnet = vpc["external_subnet"]
    cidr       = vpc.get("routable_cidr")
    vpc_type   = vpc.get("vpc_type", "REGULAR").upper()

    # Look up subnet extId by name
    subnet_ext_id = subnets.get(ext_subnet)
    if not subnet_ext_id:
        print(f"Skipping '{vpc_name}' — subnet '{ext_subnet}' not found in Prism")
        continue

    payload = {
        "name":    vpc_name,
        "vpcType": vpc_type,
        "externalSubnets": [
            {
                "subnetReference": subnet_ext_id
            }
        ]
    }

    # Only add routable prefixes if defined in config
    if cidr:
        cidr_ip     = cidr.split("/")[0]
        cidr_prefix = int(cidr.split("/")[1])
        payload["externallyRoutablePrefixes"] = [
            {
                "ipv4": {
                    "ip": {
                        "value":        cidr_ip,
                        "prefixLength": 32
                    },
                    "prefixLength": cidr_prefix
                }
            }
        ]

    print(f"Creating VPC '{vpc_name}' (type: {vpc_type}, subnet: {ext_subnet}, CIDR: {cidr or 'none'})...")
    print("Payload:")
    print(json.dumps(payload, indent=2))

    r = client.session.post(
        f"{client.base_url}/networking/v4.0/config/vpcs",
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