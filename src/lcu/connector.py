import os
import requests
import urllib3
from config import LEAGUE_INSTALL_PATHS

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class LCUConnector:
    """Connects to the League Client Update (LCU) local API."""

    def __init__(self):
        self.port = None
        self.auth_token = None
        self.base_url = None
        self.connected = False
        self.summoner = None
        self._session = requests.Session()
        self._session.verify = False

    def try_connect(self):
        lockfile_content = self._find_lockfile() or self._find_from_process()
        if not lockfile_content:
            self.connected = False
            return False

        try:
            parts = lockfile_content.split(":")
            self.port = parts[2]
            self.auth_token = parts[3]
            protocol = parts[4].strip() if len(parts) > 4 else "https"
            self.base_url = f"{protocol}://127.0.0.1:{self.port}"
            self._session.auth = ("riot", self.auth_token)

            resp = self._session.get(
                f"{self.base_url}/lol-summoner/v1/current-summoner", timeout=3
            )
            if resp.status_code == 200:
                self.summoner = resp.json()
                self.connected = True
                return True
            else:
                print(f"[LCU] Summoner endpoint returned {resp.status_code}")
        except Exception as e:
            print(f"[LCU] Connection error: {e}")

        self.connected = False
        return False

    def _find_lockfile(self):
        for install_path in LEAGUE_INSTALL_PATHS:
            lockpath = os.path.join(install_path, "lockfile")
            if os.path.exists(lockpath):
                try:
                    with open(lockpath, "r") as f:
                        content = f.read().strip()
                    if content and ":" in content:
                        return content
                except Exception:
                    continue
        return None

    def _find_from_process(self):
        try:
            import psutil
        except ImportError:
            return None

        port = None
        token = None
        install_dir = None

        try:
            for proc in psutil.process_iter(["name", "cmdline"]):
                pname = proc.info.get("name") or ""
                if "LeagueClient" not in pname:
                    continue
                cmdline = proc.info.get("cmdline") or []
                for arg in cmdline:
                    if isinstance(arg, str):
                        if arg.startswith("--app-port="):
                            port = arg.split("=", 1)[1]
                        elif arg.startswith("--remoting-auth-token="):
                            token = arg.split("=", 1)[1]
                        elif arg.startswith("--install-directory="):
                            install_dir = arg.split("=", 1)[1].strip('"')

                if install_dir:
                    lockpath = os.path.join(install_dir, "lockfile")
                    if os.path.exists(lockpath):
                        with open(lockpath, "r") as f:
                            content = f.read().strip()
                        if content:
                            return content

                if port and token:
                    return f"LeagueClient:0:{port}:{token}:https"
        except Exception:
            pass

        return None

    def get(self, endpoint):
        if not self.connected:
            return None
        try:
            resp = self._session.get(f"{self.base_url}{endpoint}", timeout=3)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            self.connected = False
        return None

    def post(self, endpoint, data=None):
        if not self.connected:
            return None
        try:
            resp = self._session.post(
                f"{self.base_url}{endpoint}", json=data, timeout=3
            )
            return resp
        except Exception:
            self.connected = False
        return None

    def delete(self, endpoint):
        if not self.connected:
            return None
        try:
            return self._session.delete(f"{self.base_url}{endpoint}", timeout=3)
        except Exception:
            self.connected = False
        return None

    def get_gameflow_phase(self):
        if not self.connected:
            return "None"
        try:
            resp = self._session.get(
                f"{self.base_url}/lol-gameflow/v1/gameflow-phase", timeout=3
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return "None"

    def get_champ_select(self):
        return self.get("/lol-champ-select/v1/session")

    def import_rune_page(self, name, primary_style, sub_style, selected_perks):
        pages = self.get("/lol-perks/v1/pages")
        if pages:
            for page in pages:
                if page.get("isDeletable") and not page.get("isTemporary"):
                    self.delete(f"/lol-perks/v1/pages/{page['id']}")
                    break

        page_data = {
            "name": name,
            "primaryStyleId": primary_style,
            "subStyleId": sub_style,
            "selectedPerkIds": selected_perks,
            "current": True,
        }
        resp = self.post("/lol-perks/v1/pages", page_data)
        return resp is not None and resp.status_code in (200, 201)
