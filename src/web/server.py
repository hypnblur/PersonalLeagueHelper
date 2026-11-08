import os

from flask import Flask, jsonify, render_template, request


class WebServer:
    def __init__(self, app_state):
        self.state = app_state
        self.flask = Flask(
            __name__,
            template_folder=os.path.join(os.path.dirname(__file__), "templates"),
            static_folder=os.path.join(os.path.dirname(__file__), "static"),
        )
        self._routes()

    def _routes(self):
        @self.flask.route("/")
        def index():
            return render_template("index.html")

        @self.flask.route("/api/state")
        def api_state():
            return jsonify(self.state.snapshot())

        @self.flask.route("/api/recommend")
        def api_recommend():
            role = request.args.get("role", "")
            allies = [a for a in request.args.getlist("allies") if a]
            enemies = [e for e in request.args.getlist("enemies") if e]
            recs = self.state.recommend(role, allies, enemies)
            return jsonify(recs)

        @self.flask.route("/api/build/<champion>")
        @self.flask.route("/api/build/<champion>/<role>")
        def api_build(champion, role=None):
            enemies = [e for e in request.args.getlist("enemies") if e]
            return jsonify(self.state.build_info(champion, role, enemies=enemies))

        @self.flask.route("/api/champions")
        def api_champions():
            return jsonify(self.state.all_champions())

        @self.flask.route("/api/import-runes", methods=["POST"])
        def api_import_runes():
            body = request.get_json(silent=True) or {}
            confirm = bool(body.get("confirm"))
            build = body.get("build") if isinstance(body.get("build"), dict) else None
            return jsonify(self.state.import_runes(body.get("champion"), body.get("role"), confirm=confirm, build=build, option_name=body.get("option_name")))

        @self.flask.route("/api/recap")
        def api_recap():
            recap = self.state.postgame.latest_recap
            if not recap:
                return jsonify({"status": "none"})
            return jsonify(recap)

        @self.flask.route("/api/recap/reanalyze", methods=["POST"])
        def api_reanalyze():
            stats = self.state.postgame.latest_stats
            if not stats:
                return jsonify({"status": "error", "message": "No game data to analyze"})
            self.state.postgame.analyze(stats)
            return jsonify({"status": "analyzing"})

        @self.flask.route("/api/insights")
        def api_insights():
            limit = request.args.get("limit", 30, type=int)
            return jsonify(self.state.db.insights(limit=limit))

        @self.flask.route("/api/matches")
        def api_matches():
            limit = request.args.get("limit", 20, type=int)
            rows = self.state.db.recent_matches(limit=limit)
            for r in rows:
                r.pop("stats_json", None)
                r.pop("recap_json", None)
            return jsonify(rows)

        @self.flask.route("/api/settings", methods=["GET", "POST"])
        def api_settings():
            if request.method == "POST":
                body = request.get_json(silent=True) or {}
                allowed = {"default_role", "show_insights", "auto_open_build", "theme"}
                for k, v in body.items():
                    if k in allowed:
                        self.state.db.set_setting(k, v)
                return jsonify({"ok": True, "settings": self.state.db.all_settings()})
            from config import AI_MODEL, AI_PROVIDER, GEMINI_API_KEY, RECAP_MODEL, RUNE_PAGE_PREFIX, SAFE_RUNE_IMPORT
            ai_ok = False
            try:
                from src.engine.ai_provider import get_provider
                ai_ok = get_provider().is_configured()
            except Exception:
                ai_ok = bool(GEMINI_API_KEY)
            return jsonify({
                "stored": self.state.db.all_settings(),
                "runtime": {
                    "has_gemini_key": bool(GEMINI_API_KEY),  # legacy
                    "recap_model": RECAP_MODEL,              # legacy
                    "ai_provider": AI_PROVIDER,
                    "ai_model": AI_MODEL,
                    "ai_configured": ai_ok,
                    "safe_rune_import": SAFE_RUNE_IMPORT,
                    "rune_page_prefix": RUNE_PAGE_PREFIX,
                },
            })

        @self.flask.route("/api/draft/analysis")
        def api_draft_analysis():
            role = request.args.get("role", "")
            allies = [a for a in request.args.getlist("allies") if a]
            enemies = [e for e in request.args.getlist("enemies") if e]
            return jsonify(self.state.draft_analysis(role, allies, enemies))

        @self.flask.route("/api/draft/bans")
        def api_draft_bans():
            role = request.args.get("role", "")
            allies = [a for a in request.args.getlist("allies") if a]
            enemies = [e for e in request.args.getlist("enemies") if e]
            return jsonify(self.state.ban_suggestions(role, allies, enemies))

        @self.flask.route("/api/draft/what-to-play")
        def api_what_to_play():
            role = request.args.get("role", "")
            allies = [a for a in request.args.getlist("allies") if a]
            enemies = [e for e in request.args.getlist("enemies") if e]
            return jsonify(self.state.what_should_i_play(role, allies, enemies))

        @self.flask.route("/api/draft/coach", methods=["POST"])
        def api_draft_coach():
            body = request.get_json(silent=True) or {}
            return jsonify(self.state.run_draft_ai("coach", body))

        @self.flask.route("/api/draft/ai")
        def api_draft_ai():
            return jsonify(getattr(self.state, "_draft_ai", {"status": "idle"}))

        @self.flask.route("/api/build-explain", methods=["POST"])
        def api_build_explain():
            body = request.get_json(silent=True) or {}
            return jsonify(self.state.run_draft_ai("build_explain", body))

        @self.flask.route("/api/pool", methods=["GET", "POST", "DELETE"])
        def api_pool():
            if request.method == "POST":
                body = request.get_json(silent=True) or {}
                champion = (body.get("champion") or "").strip()
                if not champion:
                    return jsonify({"error": "champion required"}), 400
                self.state.db.upsert_pool(champion, body.get("role", ""), body.get("priority", 0), body.get("notes", ""))
                return jsonify({"ok": True})
            if request.method == "DELETE":
                champion = request.args.get("champion", "")
                self.state.db.remove_pool(champion)
                return jsonify({"ok": True})
            return jsonify(self.state.db.list_pool())

        @self.flask.route("/api/notes", methods=["GET", "POST", "DELETE"])
        def api_notes():
            if request.method == "POST":
                body = request.get_json(silent=True) or {}
                content = (body.get("content") or "").strip()
                if not content:
                    return jsonify({"error": "content required"}), 400
                note_id = self.state.db.add_note(content, body.get("category", "general"), body.get("champion", ""))
                return jsonify({"ok": True, "id": note_id})
            if request.method == "DELETE":
                self.state.db.delete_note(request.args.get("id", 0))
                return jsonify({"ok": True})
            return jsonify(self.state.db.list_notes(limit=50))

    def run(self, host, port):
        self.flask.run(host=host, port=port, debug=False, use_reloader=False)
