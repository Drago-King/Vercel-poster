"""
poster_lib.py — core logic for the poster + caption generator.
Stripped down from the original EchoFlix Telegram bot:
  - only the "poster" design (no card / cutout styles)
  - only movie + tv (no anime/AniList)
  - no rembg, no yt-dlp, no telegram, no buttons/admin/channels
"""
import io
import math
import os

import requests
from PIL import Image, ImageDraw, ImageFont

# ─── CONFIG ──────────────────────────────────────────────────────────────────
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_ORI = "https://image.tmdb.org/t/p/original"

DEFAULT_WEBSITE = os.getenv("SITE_WATERMARK_URL", "WWW.YOURSITE.COM")
DEFAULT_WATERMARKS = {"tv": "YourSite TV", "movie": "YourSite Movies"}

FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")


def _fnt(name, size):
    try:
        return ImageFont.truetype(os.path.join(FONTS_DIR, name), size)
    except Exception:
        return ImageFont.load_default()


# ─── POSTER RENDER ───────────────────────────────────────────────────────────
def render_poster(backdrop_bytes, watermark, website=None):
    website = website or DEFAULT_WEBSITE
    img = Image.open(io.BytesIO(backdrop_bytes)).convert("RGB")
    IW, IH = img.size
    sc = IW / 2560
    cs = max(60, int(86 * sc))
    cr = max(30, int(52 * sc))
    px = max(28, int(55 * sc))
    py = max(18, int(45 * sc))
    cg = max(14, int(24 * sc))
    us = max(22, int(30 * sc))

    bf = _fnt("Poppins-Bold.ttf", cs)
    uf = _fnt("Poppins-Bold.ttf", us)
    bx = px
    by = IH - py - cs - 10

    # bottom scrim so text stays readable over any backdrop
    sh = cs + py * 2 + 10
    scrim = Image.new("RGBA", (IW, sh), (0, 0, 0, 0))
    sd = ImageDraw.Draw(scrim)
    for y2 in range(sh):
        a = int(160 * (y2 / sh) ** 0.6)
        sd.rectangle([(0, y2), (IW, y2 + 1)], fill=(0, 0, 0, a))
    ia = img.convert("RGBA")
    ia.paste(scrim, (0, IH - sh), scrim)
    img = ia.convert("RGB")

    draw = ImageDraw.Draw(img)

    # little logo mark (circle + play-style triangle)
    cx = bx + cr
    cy = by + cs // 2
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=(29, 161, 242))
    s = cr * 0.60
    a = math.radians(-35)
    ca, sa = math.cos(a), math.sin(a)

    def rot(px2, py2):
        return (cx + px2 * ca - py2 * sa, cy + px2 * sa + py2 * ca)

    draw.polygon([rot(-s * .95, s * .25), rot(-s * .95, -s * .25), rot(s * .95, 0)], fill=(255, 255, 255))
    draw.polygon([rot(-s * .95, s * .25), rot(s * .95, 0), rot(-s * .15, s * .65)], fill=(185, 225, 255))
    draw.polygon([rot(-s * .95, -s * .05), rot(-s * .95, s * .25), rot(-s * .40, s * .05)], fill=(29, 161, 242))

    # watermark text next to logo
    tx = bx + cr * 2 + cg
    bb = draw.textbbox((0, 0), "Ag", font=bf)
    ty2 = by + (cs - (bb[3] - bb[1])) // 2 - bb[1]
    draw.text((tx, ty2), watermark, font=bf, fill=(255, 255, 255))

    # website top-right
    uw = int(draw.textlength(website, font=uf))
    draw.text((IW - uw - px, py), website, font=uf, fill=(255, 255, 255))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92, subsampling=2, optimize=False)
    return buf.getvalue()


# ─── CAPTION ─────────────────────────────────────────────────────────────────
CAPTION_TEMPLATES = {
    "movie": (
        "<b>{title}</b>\n"
        "╭───────────────────\n"
        " ➥ <b>Status:</b> {status}\n"
        " ➥ <b>Rating:</b> {rating} ⭐\n"
        " ➥ <b>Audio:</b> {audio}\n"
        "├───────────────────\n"
        " ➥ <b>Genres:</b> {genres}\n"
        "╰───────────────────\n"
        "<blockquote>{overview}</blockquote>"
    ),
    "tv": (
        "<b>{title}</b>\n"
        "╭───────────────────\n"
        " ➥ <b>Status:</b> {status}\n"
        " ➥ <b>Episodes:</b> {episodes}\n"
        " ➥ <b>Rating:</b> {rating} ⭐\n"
        " ➥ <b>Audio:</b> {audio}\n"
        "├───────────────────\n"
        " ➥ <b>Genres:</b> {genres}\n"
        "╰───────────────────\n"
        "<blockquote>{overview}</blockquote>"
    ),
}


def build_caption(details, media_type):
    tmpl = CAPTION_TEMPLATES.get(media_type, CAPTION_TEMPLATES["movie"])
    try:
        return tmpl.format(
            title=details.get("title", ""),
            status=details.get("status", "N/A"),
            episodes=details.get("episodes", "N/A"),
            rating=f"{details.get('rating', 0):.1f}",
            audio=details.get("audio", "English"),
            genres=", ".join(details.get("genres", [])),
            overview=details.get("overview", ""),
        )
    except KeyError as e:
        return f"Caption error: missing placeholder {e}\n\n{details.get('title', '')}"


# ─── TMDB ────────────────────────────────────────────────────────────────────
_session = requests.Session()
_session.headers.update({"Accept-Encoding": "gzip"})


def _tmdb(ep, **p):
    p["api_key"] = TMDB_API_KEY
    r = _session.get(f"{TMDB_BASE}{ep}", params=p, timeout=10)
    r.raise_for_status()
    return r.json()


def _fetch(url):
    r = _session.get(url, timeout=20)
    r.raise_for_status()
    return r.content


def search_tmdb(query, media_type):
    ep = "/search/tv" if media_type == "tv" else "/search/movie"
    data = _tmdb(ep, query=query, page=1)
    results = []
    for r in data.get("results", [])[:8]:
        name = r.get("name") or r.get("title", "?")
        year = (r.get("first_air_date") or r.get("release_date", ""))[:4]
        poster = r.get("poster_path")
        results.append({
            "id": r["id"],
            "title": name,
            "year": year,
            "thumb": f"https://image.tmdb.org/t/p/w200{poster}" if poster else None,
        })
    return results


def get_details(tmdb_id, media_type):
    ep = f"/movie/{tmdb_id}" if media_type == "movie" else f"/tv/{tmdb_id}"
    d = _tmdb(ep)

    if media_type == "movie":
        title = d.get("title", "")
        year = (d.get("release_date", ""))[:4]
        status = d.get("status", "N/A")
        episodes = "N/A"
    else:
        title = d.get("name", "")
        year = (d.get("first_air_date", ""))[:4]
        status = d.get("status", "N/A")
        episodes = str(d.get("number_of_episodes", "?"))

    genres = [g["name"] for g in d.get("genres", [])]
    rating = round(d.get("vote_average", 0) / 2, 1)
    overview = d.get("overview", "")

    return dict(
        title=title, year=year, genres=genres, rating=rating,
        overview=overview, status=status, episodes=episodes,
        audio="English",
    )


def get_backdrops(tmdb_id, media_type):
    ep = f"/movie/{tmdb_id}/images" if media_type == "movie" else f"/tv/{tmdb_id}/images"
    data = _tmdb(ep, include_image_language="en,null")
    imgs = data.get("backdrops", [])
    if not imgs:
        return []
    srt = sorted(imgs, key=lambda x: x.get("vote_average", 0), reverse=True)
    return [TMDB_IMG_ORI + x["file_path"] for x in srt]


def fetch_backdrop_bytes(tmdb_id, media_type):
    backdrops = get_backdrops(tmdb_id, media_type)
    if not backdrops:
        raise ValueError("No backdrop image found for this title")
    return _fetch(backdrops[0])
