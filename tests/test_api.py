import json

from src.web.server import WebServer


class DummyPostgame:
    latest_recap = None
    latest_stats = None
    analyzing = False
    has_key = False

    def analyze(self, stats):
        return {"status": "analyzing"}


class DummyRecommender:
    def recommend(self, role, allies, enemies):
        return [{"champion": "Ahri", "score": 10, "tier": "A", "roles": ["middle"], "reasons": [], "build": {}}]


class DummyDB:
    def insights(self, limit=30):
        return {"count": 0}

    def recent_matches(self, limit=20):
        return [{"id": 1, "stats_json": "secret", "recap_json": "secret", "champion": "Ahri"}]

    def all_settings(self):
        return {}

    def set_setting(self, key, value):
        pass

    def list_pool(self):
        return []

    def upsert_pool(self, *args, **kwargs):
        pass

    def remove_pool(self, champion):
        pass

    def list_notes(self, limit=50):
        return []

    def add_note(self, content, category="general", champion=""):
        return 1

    def delete_note(self, note_id):
        pass


class DummyState:
    dragon = type("D", (), {"version": "15.1.1"})()
    store = None
    lcu = type("L", (), {"connected": False, "summoner": None})()
    recommender = DummyRecommender()
    postgame = DummyPostgame()
    db = DummyDB()

    def snapshot(self):
        return {"lcu_connected": False, "phase": "None", "patch": "15.1.1", "champ_select": None, "recommendations": [], "recap_available": False, "recap_analyzing": False, "recap_has_key": False}

    def build_info(self, champion, role=None):
        return {"champion": champion, "role": role or "mid", "tier": "A", "build": {"runes": []}}

    def all_champions(self):
        return [{"name": "Ahri"}]

    def import_runes(self, champion, role, confirm=False):
        return {"success": False, "needs_confirmation": True, "preview": {"page_name": f"LA: {champion}"}}


def client():
    server = WebServer(DummyState())
    server.flask.config["TESTING"] = True
    return server.flask.test_client()


def test_state_and_basic_routes():
    c = client()
    assert c.get("/api/state").status_code == 200
    assert c.get("/api/champions").get_json()[0]["name"] == "Ahri"
    assert c.get("/api/build/Ahri/middle").get_json()["champion"] == "Ahri"
    assert c.get("/api/insights").get_json()["count"] == 0


def test_matches_strip_large_json():
    c = client()
    rows = c.get("/api/matches").get_json()
    assert "stats_json" not in rows[0]
    assert "recap_json" not in rows[0]


def test_import_runes_confirmation_contract():
    c = client()
    resp = c.post("/api/import-runes", data=json.dumps({"champion": "Ahri", "role": "middle"}), content_type="application/json")
    data = resp.get_json()
    assert data["needs_confirmation"] is True
