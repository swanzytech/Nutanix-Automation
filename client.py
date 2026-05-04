import requests
import uuid
import urllib3
from dotenv import load_dotenv
import os

urllib3.disable_warnings()
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

class NutanixClient:
    def __init__(self):
        self.base_url = f"https://{os.getenv('PC_IP')}:9440/api"
        self.session  = requests.Session()
        self.session.auth   = (os.getenv("PC_USER"), os.getenv("PC_PASSWORD"))
        self.session.verify = False
        self.session.headers.update({"Content-Type": "application/json"})

    def get(self, path):
        """Simple GET - returns response body"""
        r = self.session.get(f"{self.base_url}{path}")
        r.raise_for_status()
        return r.json().get("data", [])

    def get_with_etag(self, path):
        """GET a resource and return (data, etag)"""
        r = self.session.get(f"{self.base_url}{path}")
        r.raise_for_status()
        return r.json().get("data"), r.headers.get("Etag")

    def post_action(self, path):
        """POST an action with a fresh ETag and Request ID"""
        data, etag = self.get_with_etag(path)
        r = self.session.post(
            f"{self.base_url}{path.split('/$')[0]}/$actions/{path.split('/$actions/')[1]}",
            headers={
                "If-Match": etag,
                "Ntnx-Request-Id": str(uuid.uuid4()),
            }
        )
        r.raise_for_status()
        return r

    def vm_action(self, ext_id, action):
        """Run a power action on a VM by extId"""
        path = f"/vmm/v4.0/ahv/config/vms/{ext_id}"
        data, etag = self.get_with_etag(path)
        r = self.session.post(
            f"{self.base_url}{path}/$actions/{action}",
            headers={
                "If-Match": etag,
                "Ntnx-Request-Id": str(uuid.uuid4()),
            }
        )
        return r

    def list_vms(self):
        """Return list of all VMs"""
        return self.get("/vmm/v4.0/ahv/config/vms")