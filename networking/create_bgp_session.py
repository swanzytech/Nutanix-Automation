import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from client import NutanixClient
import uuid
import yaml
import time

_here = os.path.dirname(os.path.abspath(__file__))

client = NutanixClient()

with open(os.path.join(_here, "bgp_session_config.yaml"), "r") as f:
    config = yaml.safe_load(f)

sessions = config.get("bgp_sessions", [])
if not sessions:
    print("No bgp_sessions found in bgp_session_config.yaml")
    exit(1)

# --------------------------------------------------
# Fetch gateways
# --------------------------------------------------
print("Fetching gateways...")
all_gateways = client.get("/networking/v4.0/config/gateways")
gateways_map = {g.get("name"): g.get("extId") for g in all_gateways}

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

# --------------------------------------------------
# Create BGP sessions
# --------------------------------------------------
print(f"\n{'='*60}")
print(f"Creating {len(sessions)} BGP session(s)...")
print(f"{'='*60}\n")

for session in sessions:
    name           = session["name"]
    local_gw_name  = session["local_gateway"]
    remote_gw_name = session["remote_gateway"]

    local_gw_id  = gateways_map.get(local_gw_name)
    remote_gw_id = gateways_map.get(remote_gw_name)

    if not local_gw_id:
        print(f"Skipping '{name}' — local gateway '{local_gw_name}' not found")
        continue
    if not remote_gw_id:
        print(f"Skipping '{name}' — remote gateway '{remote_gw_name}' not found")
        continue

    payload = {
        "name":                   name,
        "localGatewayReference":  local_gw_id,
        "remoteGatewayReference": remote_gw_id,
    }

    if "local_interface_ip" in session:
        payload["localGatewayInterfaceIpAddress"] = {
            "ipv4": {"value": session["local_interface_ip"]}
        }

    if session.get("advertise_all_prefixes"):
        payload["shouldAdvertiseAllExternallyRoutablePrefixes"] = True

    print(f"Creating BGP session '{name}'")
    print(f"  Local:     {local_gw_name} ({local_gw_id})")
    print(f"  Remote:    {remote_gw_name} ({remote_gw_id})")
    if "local_interface_ip" in session:
        print(f"  Interface: {session['local_interface_ip']}")
    ntnx_post("/networking/v4.0/config/bgp-sessions", payload)
    time.sleep(2)

print("\nDone!")
