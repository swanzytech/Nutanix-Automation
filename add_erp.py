from client import NutanixClient
import uuid
import yaml
import time 

client = NutanixClient()

with open("add_erp.yaml", "r") as f:
    config = yaml.safe_load(f)

vpc_updates = config.get("vpcs", [])

if not vpc_updates:
    print("No VPCs found in add_erp.yaml")
    exit(1)

print("Fetching VPCs...")
all_vpcs = client.get("/networking/v4.0/config/vpcs")
vpcs     = {v.get("name"): v.get("extId") for v in all_vpcs}

for update in vpc_updates:
    vpc_name   = update["name"]
    to_add     = set(update.get("cidrs", []))

    vpc_ext_id = vpcs.get(vpc_name)
    if not vpc_ext_id:
        print(f"Skipping '{vpc_name}' — not found in Prism")
        continue

    vpc_data, etag = client.get_with_etag(f"/networking/v4.0/config/vpcs/{vpc_ext_id}")

    current_erps = set()
    for erp in vpc_data.get("externallyRoutablePrefixes", []):
        ip     = erp.get("ipv4", {}).get("ip", {}).get("value")
        prefix = erp.get("ipv4", {}).get("prefixLength")
        if ip and prefix:
            current_erps.add(f"{ip}/{prefix}")

    updated_erps = current_erps | to_add

    erp_payload = [
        {
            "ipv4": {
                "ip": {"value": cidr.split("/")[0], "prefixLength": 32},
                "prefixLength": int(cidr.split("/")[1])
            }
        }
        for cidr in updated_erps
    ]

    payload = {
        "name":                       vpc_data.get("name"),
        "vpcType":                    vpc_data.get("vpcType", "REGULAR"),
        "externalSubnets":            vpc_data.get("externalSubnets", []),
        "externallyRoutablePrefixes": erp_payload
    }

    print(f"Adding ERPs to '{vpc_name}': {sorted(to_add)}...")

    r = client.session.put(
        f"{client.base_url}/networking/v4.0/config/vpcs/{vpc_ext_id}",
        json=payload,
        headers={
            "If-Match":        etag,
            "Ntnx-Request-Id": str(uuid.uuid4()),
        }
    )

    if r.status_code in (200, 202):
        print(f"  Success!")
        time.sleep(2)
    else:
        print(f"  Failed: {r.status_code}")
        print(f"  {r.text}")

print("\nDone!")