import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
from poster_lib import search_tmdb  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            query = qs.get("q", [""])[0].strip()
            media_type = qs.get("type", ["movie"])[0]
            if media_type not in ("movie", "tv"):
                media_type = "movie"
            if not query:
                self._json(400, {"error": "Missing 'q' query param"})
                return
            results = search_tmdb(query, media_type)
            self._json(200, {"results": results})
        except Exception as e:
            self._json(500, {"error": str(e)})

    def _json(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
