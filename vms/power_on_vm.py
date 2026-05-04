import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from client import NutanixClient

client = NutanixClient()
vms    = client.list_vms()

# Display VMs
print(f"\n{'#':<4} {'Name':<30} {'ExtId':<40} {'Power State'}")
print("-" * 90)

for i, vm in enumerate(vms):
    print(f"{i:<4} {vm.get('name',''):<30} {vm.get('extId',''):<40} {vm.get('powerState','')}")

# Select VMs
print()
choices  = input("Enter the # of the VM(s) to power on (comma separated): ")
selected = [vms[int(i.strip())] for i in choices.split(",")]

# Power on each
for vm in selected:
    print(f"\nPowering on {vm.get('name')}...")
    r = client.vm_action(vm.get("extId"), "power-on")
    if r.status_code in (200, 202):
        print(f"  Success!")
    else:
        print(f"  Failed: {r.status_code} {r.text}")

print("\nDone!")