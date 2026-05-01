import requests
import urllib3
from dotenv import load_dotenv
import os

urllib3.disable_warnings()

load_dotenv()
PC_IP    = os.getenv("PC_IP")
USERNAME = os.getenv("PC_USER")
PASSWORD = os.getenv("PC_PASSWORD")

BASE_URL = f"https://{PC_IP}:9440/api"

session = requests.Session()
session.auth   = (USERNAME, PASSWORD)
session.verify = False
session.headers.update({"Content-Type": "application/json"})

print("Fetching VMs...")

response = session.get(f"{BASE_URL}/vmm/v4.0/ahv/config/vms")

if response.status_code != 200:
    print(f"Failed: {response.status_code}")
    print(response.text)
    exit(1)

vms = response.json().get("data", [])

print(f"\n{'Name':<30} {'ExtId':<40} {'Power State'}")
print("-" * 85)

for vm in vms:
    name        = vm.get("name", "unknown")
    ext_id      = vm.get("extId", "unknown")
    power_state = vm.get("powerState", "unknown")
    print(f"{name:<30} {ext_id:<40} {power_state}")