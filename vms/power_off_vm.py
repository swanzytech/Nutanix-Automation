import requests
import uuid
import urllib3
from dotenv import load_dotenv
import os

urllib3.disable_warnings()

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
PC_IP    = os.getenv("PC_IP")
USERNAME = os.getenv("PC_USER")
PASSWORD = os.getenv("PC_PASSWORD")

BASE_URL = f"https://{PC_IP}:9440/api"

session = requests.Session()
session.auth   = (USERNAME, PASSWORD)
session.verify = False
session.headers.update({"Content-Type": "application/json"})

# Show available VMs
response = session.get(f"{BASE_URL}/vmm/v4.0/ahv/config/vms")
vms = response.json().get("data", [])

print(f"\n{'#':<4} {'Name':<30} {'ExtId':<40} {'Power State'}")
print("-" * 90)

for i, vm in enumerate(vms):
    print(f"{i:<4} {vm.get('name',''):<30} {vm.get('extId',''):<40} {vm.get('powerState','')}")

# Prompt user to pick one or more
print()
choices = input("Enter the # of the VM(s) to power off (comma separated, e.g. 0,2,3): ")
selected = [vms[int(i.strip())] for i in choices.split(",")]

print(f"\nSelected {len(selected)} VM(s):")
for vm in selected:
    print(f"  - {vm.get('name')}")

# Process each selected VM
for vm in selected:
    VM_EXT_ID = vm.get("extId")
    print(f"\nFetching {vm.get('name')}...")

    get_response = session.get(f"{BASE_URL}/vmm/v4.0/ahv/config/vms/{VM_EXT_ID}")

    if get_response.status_code != 200:
        print(f"  Failed to fetch: {get_response.status_code}")
        continue

    etag    = get_response.headers.get("Etag")
    vm_data = get_response.json().get("data")

    print(f"  ETag: {etag}")
    print(f"  Sending power off...")

    action_response = session.post(
        f"{BASE_URL}/vmm/v4.0/ahv/config/vms/{VM_EXT_ID}/$actions/power-off",
        headers={
            "If-Match": etag,
            "Ntnx-Request-Id": str(uuid.uuid4()),
        }
    )

    if action_response.status_code in (200, 202):
        print(f"  Success! ({action_response.status_code})")
    else:
        print(f"  Failed: {action_response.status_code}")
        print(f"  {action_response.text}")

print("\nDone!")