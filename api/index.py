import base64
import os
import sys

from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "lib"))
from poster_lib import (  # noqa: E402
    search_tmdb,
    get_details,
    fetch_backdrop_bytes,
    render_poster,
    build_caption,
    DEFAULT_WATERMARKS,
)

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
def root():
    with open(os.path.join(ROOT_DIR, "index.html"), "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/search")
def search(q: str = "", type: str = "movie"):
    q = q.strip()
    media_type = type if type in ("movie", "tv") else "movie"
    if not q:
        return JSONResponse({"error": "Missing 'q' query param"}, status_code=400)
    try:
        results = search_tmdb(q, media_type)
        return {"results": results}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/generate")
def generate(id: str = "", type: str = "movie"):
    media_type = type if type in ("movie", "tv") else "movie"
    if not id:
        return JSONResponse({"error": "Missing 'id' query param"}, status_code=400)
    try:
        details = get_details(id, media_type)
        backdrop_bytes = fetch_backdrop_bytes(id, media_type)
        watermark = DEFAULT_WATERMARKS.get(media_type, "YourSite")
        image_bytes = render_poster(backdrop_bytes, watermark)
        caption = build_caption(details, media_type)
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        return {
            "title": details.get("title", ""),
            "image": f"data:image/jpeg;base64,{image_b64}",
            "caption": caption,
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
