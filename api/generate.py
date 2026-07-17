import base64
import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
from poster_lib import (  # noqa: E402
    get_details,
    fetch_backdrop_bytes,
    render_poster,
    build_caption,
    DEFAULT_WATERMARKS,
)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            tmdb_id = qs.get("id", [""])[0]
            media_type = qs.get("type", ["movie"])[0]
            if media_type not in ("movie", "tv"):
                media_type = "movie"
            if not tmdb_id:
                self._json(400, {"error": "Missing 'id' query param"})
                return

            details = get_details(tmdb_id, media_type)
            backdrop_bytes = fetch_backdrop_bytes(tmdb_id, media_type)
            watermark = DEFAULT_WATERMARKS.get(media_type, "YourSite")
            image_bytes = render_poster(backdrop_bytes, watermark)
            caption = build_caption(details, media_type)

            image_b64 = base64.b64encode(image_bytes).decode("ascii")
            self._json(200, {
                "title": details.get("title", ""),
                "image": f"data:image/jpeg;base64,{image_b64}",
                "caption": caption,
            })
        except Exception as e:
            self._json(500, {"error": str(e)})

    def _json(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
