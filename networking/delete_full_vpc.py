import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from client import NutanixClient
import uuid
import yaml
import time

_here = os.path.dirname(os.path.abspath(__file__))

client = NutanixClient()

with open(os.path.join(_here, "create_full_vpc_config.yaml"), "r") as f:
    config = yaml.safe_load(f)

# --------------------------------------------------
# Utilities
# --------------------------------------------------
def step(n, label):
    print(f"\n{'='*60}")
    print(f"STEP {n}: {label}")
    print(f"{'='*60}\n")

def ntnx_delete(path):
    data, etag = client.get_with_etag(path)
    if not etag:
        print(f"  No ETag returned for {path}, skipping")
        return None
    r = client.session.delete(
        f"{client.base_url}{path}",
        headers={
            "If-Match":        etag,
            "Ntnx-Request-Id": str(uuid.uuid4()),
        }
    )
    if r.status_code in (200, 202, 204):
        print("  Deleted!")
        task_id = r.json().get("data", {}).get("extId") if r.content else None
        if task_id:
            print(f"  Task ExtId: {task_id}")
        return task_id or True
    print(f"  Failed: {r.status_code} — {r.text}")
    return None

def wait_for_tasks(task_ids, poll_interval=5, timeout=300):
    pending = [t for t in task_ids if t and t is not True]
    if not pending:
        return
    print(f"\nWaiting for {len(pending)} task(s)...")
    deadline = time.time() + timeout
    while pending and time.time() < deadline:
        still_pending = []
        for task_id in pending:
            try:
                data   = client.get(f"/prism/v4.0/config/tasks/{task_id}")
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

def build_map(endpoint):
    return {item.get("name"): item.get("extId") for item in client.get(endpoint)}

# --------------------------------------------------
# Fetch all resources up front
# --------------------------------------------------
print("Fetching resources...")
sessions_map = build_map("/networking/v4.0/config/bgp-sessions")
gateways_map = build_map("/networking/v4.0/config/gateways")
subnets_map  = build_map("/networking/v4.0/config/subnets")
vpcs_map     = build_map("/networking/v4.0/config/vpcs")

# --------------------------------------------------
# STEP 1: Delete BGP sessions
# --------------------------------------------------
bgp_sessions = config.get("bgp_sessions", [])
if bgp_sessions:
    step(1, f"Deleting {len(bgp_sessions)} BGP session(s)")
    tasks = []
    for s in bgp_sessions:
        name   = s["name"]
        ext_id = sessions_map.get(name)
        if not ext_id:
            print(f"Skipping '{name}' — not found")
            continue
        print(f"Deleting BGP session '{name}'...")
        t = ntnx_delete(f"/networking/v4.0/config/bgp-sessions/{ext_id}")
        tasks.append(t)
        time.sleep(1)
    wait_for_tasks(tasks)

# --------------------------------------------------
# STEP 2: Delete gateways
# --------------------------------------------------
local_gateways  = config.get("local_gateways", [])
remote_gateways = config.get("remote_gateways", [])
all_gateways    = local_gateways + remote_gateways
if all_gateways:
    step(2, f"Deleting {len(all_gateways)} gateway(s)")
    tasks = []
    for gw in all_gateways:
        name   = gw["name"]
        ext_id = gateways_map.get(name)
        if not ext_id:
            print(f"Skipping '{name}' — not found")
            continue
        print(f"Deleting gateway '{name}'...")
        t = ntnx_delete(f"/networking/v4.0/config/gateways/{ext_id}")
        tasks.append(t)
        time.sleep(1)
    wait_for_tasks(tasks)

# --------------------------------------------------
# STEP 3: Delete child overlay subnets
# --------------------------------------------------
overlays = config.get("overlays", [])
if overlays:
    step(3, f"Deleting {len(overlays)} child overlay subnet(s)")
    tasks = []
    for o in overlays:
        name   = o["name"]
        ext_id = subnets_map.get(name)
        if not ext_id:
            print(f"Skipping '{name}' — not found")
            continue
        print(f"Deleting overlay '{name}'...")
        t = ntnx_delete(f"/networking/v4.0/config/subnets/{ext_id}")
        tasks.append(t)
        time.sleep(1)
    wait_for_tasks(tasks)

# --------------------------------------------------
# STEP 4: Delete child VPCs
# --------------------------------------------------
vpcs = config.get("vpcs", [])
if vpcs:
    step(4, f"Deleting {len(vpcs)} child VPC(s)")
    tasks = []
    for v in vpcs:
        name   = v["name"]
        ext_id = vpcs_map.get(name)
        if not ext_id:
            print(f"Skipping '{name}' — not found")
            continue
        print(f"Deleting VPC '{name}'...")
        t = ntnx_delete(f"/networking/v4.0/config/vpcs/{ext_id}")
        tasks.append(t)
        time.sleep(1)
    wait_for_tasks(tasks)

# --------------------------------------------------
# STEP 5: Delete transit overlays
# --------------------------------------------------
transit_overlays = config.get("transit_overlays", [])
if transit_overlays:
    step(5, f"Deleting {len(transit_overlays)} transit overlay(s)")
    print("Refreshing subnets...")
    subnets_map = build_map("/networking/v4.0/config/subnets")
    tasks = []
    for o in transit_overlays:
        name   = o["name"]
        ext_id = subnets_map.get(name)
        if not ext_id:
            print(f"Skipping '{name}' — not found")
            continue
        print(f"Deleting transit overlay '{name}'...")
        t = ntnx_delete(f"/networking/v4.0/config/subnets/{ext_id}")
        tasks.append(t)
        time.sleep(1)
    wait_for_tasks(tasks)

# --------------------------------------------------
# STEP 6: Delete transit VPCs
# --------------------------------------------------
transit_vpcs = config.get("transit_vpcs", [])
if transit_vpcs:
    step(6, f"Deleting {len(transit_vpcs)} transit VPC(s)")
    print("Refreshing VPCs...")
    vpcs_map = build_map("/networking/v4.0/config/vpcs")
    tasks = []
    for v in transit_vpcs:
        name   = v["name"]
        ext_id = vpcs_map.get(name)
        if not ext_id:
            print(f"Skipping '{name}' — not found")
            continue
        print(f"Deleting transit VPC '{name}'...")
        t = ntnx_delete(f"/networking/v4.0/config/vpcs/{ext_id}")
        tasks.append(t)
        time.sleep(1)
    wait_for_tasks(tasks)

# --------------------------------------------------
# STEP 7: Delete VLAN subnets
# --------------------------------------------------
subnets = config.get("subnets", [])
if subnets:
    step(7, f"Deleting {len(subnets)} VLAN subnet(s)")
    print("Refreshing subnets...")
    subnets_map = build_map("/networking/v4.0/config/subnets")
    tasks = []
    for s in subnets:
        name   = s["name"]
        ext_id = subnets_map.get(name)
        if not ext_id:
            print(f"Skipping '{name}' — not found")
            continue
        print(f"Deleting VLAN subnet '{name}'...")
        t = ntnx_delete(f"/networking/v4.0/config/subnets/{ext_id}")
        tasks.append(t)
        time.sleep(1)
    wait_for_tasks(tasks)

print("\nDone!")
