from client import NutanixClient
import uuid
import yaml
import time

client = NutanixClient()

with open("gateway_config.yaml", "r") as f:
    config = yaml.safe_load(f)

local_gateways  = config.get("local_gateways", [])
remote_gateways = config.get("remote_gateways", [])

if not local_gateways and not remote_gateways:
    print("No gateways found in gateway_config.yaml")
    exit(1)

# --------------------------------------------------
# Fetch resources
# --------------------------------------------------
print("Fetching resources...")
all_subnets  = client.get("/networking/v4.0/config/subnets")
subnets      = {s.get("name"): s.get("extId") for s in all_subnets}

all_vpcs     = client.get("/networking/v4.0/config/vpcs")
vpcs         = {v.get("name"): v.get("extId") for v in all_vpcs}

all_clusters = client.get("/clustermgmt/v4.0/config/clusters")
clusters     = {c.get("name"): c.get("extId") for c in all_clusters}

# --------------------------------------------------
# Create local gateways
# --------------------------------------------------
if local_gateways:
    print(f"\n{'='*60}")
    print(f"Creating {len(local_gateways)} local gateway(s)...")
    print(f"{'='*60}\n")

    for gw in local_gateways:
        name           = gw["name"]
        subnet_id      = subnets.get(gw["subnet"])
        vpc_id         = vpcs.get(gw["vpc"])
        cluster_ext_id = clusters.get(gw["cluster"])
        asn            = gw["asn"]
        gateway_ip     = gw["gateway_ip"]
        prefix         = gw["prefix"]
        static_ips     = gw["static_ips"]

        if not subnet_id:
            print(f"Skipping '{name}' — subnet '{gw['subnet']}' not found")
            continue
        if not vpc_id:
            print(f"Skipping '{name}' — VPC '{gw['vpc']}' not found")
            continue
        if not cluster_ext_id:
            print(f"Skipping '{name}' — cluster '{gw['cluster']}' not found")
            continue

        interfaces = [
            {
                "subnetReference": subnet_id,
                "ipAddress": {
                    "ipv4": {"value": ip, "prefixLength": prefix}
                },
                "defaultGatewayAddress": {
                    "ipv4": {"value": gateway_ip, "prefixLength": prefix}
                }
            }
            for ip in static_ips
        ]

        payload = {
            "name": name,
            "deployment": {
                "clusterReference": cluster_ext_id,
                "managementInterface": {
                    "subnetReference": subnet_id,
                    "address": {
                        "ipv4": {"value": static_ips[0], "prefixLength": prefix}
                    },
                    "defaultGateway": {
                        "ipv4": {"value": gateway_ip, "prefixLength": 32}
                    }
                },
                "interfaces":                       interfaces,
                "shouldSynchronizeSystemNtpServers": True,
                "shouldSynchronizeSystemDnsServers": True
            },
            "services": {
                "$objectType": "networking.v4.config.LocalNetworkServices",
                "localBgpService": {
                    "vpcReference": vpc_id,
                    "asn":          asn
                }
            }
        }

        print(f"Creating local gateway '{name}' (VPC: {gw['vpc']}, ASN: {asn})...")

        r = client.session.post(
            f"{client.base_url}/networking/v4.0/config/gateways",
            json=payload,
            headers={"Ntnx-Request-Id": str(uuid.uuid4())}
        )

        if r.status_code in (200, 201, 202):
            print(f"  Success!")
        else:
            print(f"  Failed: {r.status_code}")
            print(f"  {r.text}")
        time.sleep(2)

# --------------------------------------------------
# Create remote gateways
# --------------------------------------------------
if remote_gateways:
    print(f"\n{'='*60}")
    print(f"Creating {len(remote_gateways)} remote gateway(s)...")
    print(f"{'='*60}\n")

    for gw in remote_gateways:
        name       = gw["name"]
        service_ip = gw["service_ip"]
        asn        = gw["asn"]

        payload = {
            "name": name,
            "services": {
                "$objectType": "networking.v4.config.RemoteNetworkServices",
                "remoteBgpService": {
                    "address": {
                        "ipv4": {
                            "value":        service_ip,
                            "prefixLength": 32
                        }
                    },
                    "asn": asn
                }
            }
        }

        print(f"Creating remote gateway '{name}' (IP: {service_ip}, ASN: {asn})...")

        r = client.session.post(
            f"{client.base_url}/networking/v4.0/config/gateways",
            json=payload,
            headers={"Ntnx-Request-Id": str(uuid.uuid4())}
        )

        if r.status_code in (200, 201, 202):
            print(f"  Success!")
        else:
            print(f"  Failed: {r.status_code}")
            print(f"  {r.text}")
        time.sleep(2)