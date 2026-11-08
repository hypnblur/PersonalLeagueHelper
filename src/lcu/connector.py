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

    def get_gameflow_session(self):
        return self.get("/lol-gameflow/v1/session")

    def get_lobby(self):
        return self.get("/lol-lobby/v2/lobby")

    def get_summoner_by_id(self, summoner_id):
        if summoner_id in (None, "", 0):
            return None
        return self.get(f"/lol-summoner/v1/summoners/{summoner_id}")

    def get_ranked_stats(self, puuid):
        if not puuid:
            return None
        return self.get(f"/lol-ranked/v1/ranked-stats/{puuid}")

    def get_champion_mastery(self, puuid, champion_id):
        if not puuid or not champion_id:
            return None
        data = self.get(f"/lol-champion-mastery/v1/{puuid}/champion-mastery/by-champion/{int(champion_id)}")
        if data is None:
            return None
        return data

    def get_champion_masteries(self, puuid, limit=30):
        if not puuid:
            return []
        data = self.get(f"/lol-champion-mastery/v1/{puuid}/champion-masteries")
        if not isinstance(data, list):
            data = self.get(f"/lol-champion-mastery/v4/{puuid}/champion-masteries") or []
        if not isinstance(data, list):
            return []
        return data[: max(1, int(limit or 30))]

    def get_owned_champions(self):
        # Best-effort: endpoint/shape varies by client version.
        data = self.get("/lol-champions/v1/owned-champions-minimal")
        if isinstance(data, list) and data:
            return data
        sid = (self.summoner or {}).get("summonerId")
        if sid:
            data = self.get(f"/lol-champions/v1/inventories/{sid}/champions-minimal")
            if isinstance(data, list) and data:
                return data
        data = self.get("/lol-champ-select/v1/pickable-champion-ids")
        if isinstance(data, list):
            return [{"id": i, "ownership": {"owned": True}} for i in data]
        return []

    def import_rune_page(self, name, primary_style, sub_style, selected_perks, safe=True, prefix="LA:"):
        pages = self.get("/lol-perks/v1/pages") or []
        deleted = None
        # Safer behavior: only touch app-owned rune pages.
        if safe:
            for page in pages:
                pname = page.get("name") or ""
                if page.get("isDeletable") and not page.get("isTemporary") and pname.startswith(prefix):
                    self.delete(f"/lol-perks/v1/pages/{page['id']}")
                    deleted = {"id": page.get("id"), "name": pname}
                    break
        else:
            # Legacy behavior: free one deletable slot.
            for page in pages:
                if page.get("isDeletable") and not page.get("isTemporary"):
                    self.delete(f"/lol-perks/v1/pages/{page['id']}")
                    deleted = {"id": page.get("id"), "name": page.get("name")}
                    break

        page_data = {
            "name": name,
            "primaryStyleId": primary_style,
            "subStyleId": sub_style,
            "selectedPerkIds": selected_perks,
            "current": True,
        }
        resp = self.post("/lol-perks/v1/pages", page_data)
        ok = resp is not None and resp.status_code in (200, 201)
        result = {
            "ok": ok,
            "status_code": getattr(resp, "status_code", None),
            "deleted": deleted,
        }
        if not ok:
            try:
                body = resp.json() if resp is not None else None
            except Exception:
                body = getattr(resp, "text", None)
            result["error"] = body or "LCU rejected rune page"
            if isinstance(result["error"], dict):
                result["error"] = result["error"].get("message") or str(result["error"])
        return result

    def rune_import_preview(self, name, safe=True, prefix="LA:"):
        pages = self.get("/lol-perks/v1/pages") or []
        action = "create"
        target = None
        deletable_app = 0
        deletable_any = 0
        if safe:
            for page in pages:
                pname = page.get("name") or ""
                deletable = page.get("isDeletable") and not page.get("isTemporary")
                if deletable:
                    deletable_any += 1
                if deletable and pname.startswith(prefix):
                    deletable_app += 1
                    if not target:
                        action = "replace_app_page"
                        target = {"id": page.get("id"), "name": pname}
        else:
            for page in pages:
                if page.get("isDeletable") and not page.get("isTemporary"):
                    deletable_any += 1
                    if not target:
                        action = "replace_deletable_page"
                        target = {"id": page.get("id"), "name": page.get("name")}
        return {
            "safe": bool(safe),
            "action": action,
            "target": target,
            "page_name": name,
            "total_pages": len(pages),
            "deletable_app_pages": deletable_app,
            "deletable_pages": deletable_any,
        }
