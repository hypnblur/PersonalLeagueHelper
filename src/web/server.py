import os
from flask import Flask, render_template, jsonify, request


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
            recs = self.state.recommender.recommend(role, allies, enemies)
            return jsonify(recs)

        @self.flask.route("/api/build/<champion>")
        @self.flask.route("/api/build/<champion>/<role>")
        def api_build(champion, role=None):
            return jsonify(self.state.build_info(champion, role))

        @self.flask.route("/api/champions")
        def api_champions():
            return jsonify(self.state.all_champions())

        @self.flask.route("/api/import-runes", methods=["POST"])
        def api_import_runes():
            body = request.get_json(silent=True) or {}
            return jsonify(self.state.import_runes(body.get("champion"), body.get("role")))

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

    def run(self, host, port):
        self.flask.run(host=host, port=port, debug=False, use_reloader=False)
