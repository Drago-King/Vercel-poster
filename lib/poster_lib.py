"""
poster_lib.py — core logic for the poster + caption generator.

Renders the "card" design: vertical poster on the left, dark info panel on
the right with title, meta, genre pills, rating stars, overview, and
decorative (non-clickable) WATCH NOW / MORE INFO buttons baked into the image.

Stripped from the original EchoFlix Telegram bot — no cutout style, no
rembg, no yt-dlp, no telegram, no anime/AniList, no interactive buttons.
"""
import colorsys
import io
import math
import os

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ─── CONFIG (set these as env vars in Vercel — see README) ──────────────────
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_ORI = "https://image.tmdb.org/t/p/original"

# Your branding — hardcoded.
SITE_WATERMARK = {
    "movie": "EchoFlix Movies",
    "tv": "EchoFlix TV",
}
SITE_URL = "WWW.ECHOFLIX-TV.COM"
BTN_WATCH = "WATCH NOW"
BTN_INFO = "MORE INFO"

FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")


def _fnt(name, size):
    try:
        return ImageFont.truetype(os.path.join(FONTS_DIR, name), size)
    except Exception:
        return ImageFont.load_default()


F = {
    "title_xl": _fnt("Poppins-Bold.ttf", 300),
    "title_lg": _fnt("Poppins-Bold.ttf", 250),
    "title_md": _fnt("Poppins-Bold.ttf", 200),
    "title_sm": _fnt("Poppins-Bold.ttf", 160),
    "title_xs": _fnt("Poppins-Bold.ttf", 130),
    "title_xxs": _fnt("Poppins-Bold.ttf", 110),
    "title_min": _fnt("Poppins-Bold.ttf", 90),
    "meta": _fnt("Poppins-Medium.ttf", 78),
    "desc": _fnt("Poppins-Regular.ttf", 70),
    "btn": _fnt("Poppins-Bold.ttf", 76),
    "wmark": _fnt("Poppins-Bold.ttf", 72),
    "url": _fnt("Poppins-Medium.ttf", 54),
    "wmark_sm": _fnt("Poppins-Light.ttf", 56),
}

# ─── CANVAS CONSTANTS ────────────────────────────────────────────────────────
CW, CH = 3840, 2160
POSTER_W = 1420
RIGHT_X = POSTER_W + 200
MARGIN_R = 150
CONTENT_W = CW - RIGHT_X - MARGIN_R
TAG_H = 100
TAG_R = 50
TAG_PX = 44
RAT_PX = 38
GAP = 26


# ─── COLOR UTILS ─────────────────────────────────────────────────────────────
def _palette(img_bytes):
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    img.thumbnail((80, 80))
    q = img.quantize(colors=6, method=Image.Quantize.FASTOCTREE)
    pal = q.getpalette()
    c = {}
    for px in q.getdata():
        c[px] = c.get(px, 0) + 1
    idx = sorted(c, key=c.get, reverse=True)
    return [(pal[i * 3], pal[i * 3 + 1], pal[i * 3 + 2]) for i in idx[:6]]


def lum(rgb):
    r, g, b = [x / 255 for x in rgb]
    return 0.299 * r + 0.587 * g + 0.114 * b


def darken(rgb, f):
    return tuple(max(0, int(c * f)) for c in rgb)


def blend(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def _pick(palette):
    for c in palette:
        r, g, b = c
        mx = max(r, g, b)
        mn = min(r, g, b)
        if lum(c) > 0.06 and ((mx - mn) / mx > 0.10 if mx else False):
            return c
    return palette[0]


def smart_accent(p):
    r, g, b = [x / 255 for x in p]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    s = max(0.55, s)
    for vt in [v, .55, .65, .75, .85, .95]:
        r2, g2, b2 = colorsys.hsv_to_rgb(h, s, vt)
        c = (int(r2 * 255), int(g2 * 255), int(b2 * 255))
        if lum(c) >= 0.32:
            return c
    return (220, 165, 20)


def smart_bg(p):
    r, g, b = p
    return (max(8, int(r * .10)), max(8, int(g * .10)), max(8, int(b * .10)))


def tag_col(bg, acc):
    c = tuple(int(bg[i] * .35 + acc[i] * .65) for i in range(3))
    return c if lum(c) >= 0.28 else (185, 190, 205)


def btn_fg(acc):
    return (15, 15, 20) if lum(acc) > 0.50 else (255, 255, 255)


# ─── DRAWING UTILS ───────────────────────────────────────────────────────────
def tvc(draw, font, by, bh, nudge=5):
    bb = draw.textbbox((0, 0), "Ag", font=font)
    return by + (bh - (bb[3] - bb[1])) // 2 - bb[1] + nudge


def play_tri(draw, x, y, sz, col):
    w = int(sz * .85)
    draw.polygon([(x, y), (x, y + sz), (x + w, y + sz // 2)], fill=col)


def draw_star(draw, cx, cy, ro, ri, fill):
    pts = [(cx + (ro if i % 2 == 0 else ri) * math.cos(math.pi / 2 + i * math.pi / 5),
            cy - (ro if i % 2 == 0 else ri) * math.sin(math.pi / 2 + i * math.pi / 5)) for i in range(10)]
    draw.polygon(pts, fill=fill)


def fit_title(text, draw, mw):
    sizes = [("title_xl", 300), ("title_lg", 250), ("title_md", 200), ("title_sm", 160),
             ("title_xs", 130), ("title_xxs", 110), ("title_min", 90)]
    candidates = []
    for k, sz in sizes:
        f = F.get(k) or _fnt("Poppins-Bold.ttf", sz)
        if draw.textlength(text, font=f) <= mw:
            candidates.append((sz, f, [text]))
            continue
        words = text.split()
        lines = []
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            if draw.textlength(test, font=f) <= mw:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if len(lines) <= 4 and all(draw.textlength(l, font=f) <= mw for l in lines):
            candidates.append((sz, f, lines))
    if not candidates:
        f = F.get("title_min") or _fnt("Poppins-Bold.ttf", 90)
        words = text.split()
        lines = []
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            if draw.textlength(test, font=f) <= mw:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return f, lines

    def score(sz, lines):
        n = len(lines)
        if n == 1 and sz < 130:
            return 500 - sz + 5000
        return n * 500 - sz

    candidates.sort(key=lambda x: score(x[0], x[2]))
    best = candidates[0]
    return best[1], best[2]


def wrap(text, font, draw, mw, ml=5):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= mw:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
        if len(lines) == ml:
            break
    if cur and len(lines) < ml:
        lines.append(cur)
    if len(" ".join(lines).split()) < len(words):
        last = lines[-1]
        while last and draw.textlength(last + " …", font=font) > mw:
            last = last.rsplit(" ", 1)[0]
        lines[-1] = last + " …"
    return lines


def _fp(ts, rs):
    return _fnt("Poppins-Medium.ttf", ts), _fnt("Poppins-Bold.ttf", rs)


def _gw(draw, g, tf):
    return int(draw.textlength(g, font=tf)) + TAG_PX * 2 + GAP


def _rw_badge(draw, rating, rf):
    sro = 26
    sw = 5 * (sro * 2) + 4 * 10
    return sw + int(draw.textlength(f"  {rating:.1f} / 5", font=rf)) + RAT_PX * 2 + GAP + 20


def _draw_row(draw, genres, rating, ty, ACC, TC, tf, rf):
    tx = RIGHT_X
    for g in genres:
        tw = int(draw.textlength(g, font=tf))
        bw = tw + TAG_PX * 2
        draw.rounded_rectangle([tx, ty, tx + bw, ty + TAG_H], radius=TAG_R, outline=TC, width=4)
        draw.text((tx + TAG_PX, tvc(draw, tf, ty, TAG_H)), g, font=tf, fill=TC)
        tx += bw + GAP
    if rating is not None:
        rs2 = f"  {rating:.1f} / 5"
        sro, sri, sg = 26, 11, 10
        sw = 5 * (sro * 2) + 4 * sg
        rw2 = int(draw.textlength(rs2, font=rf))
        bw2 = sw + rw2 + RAT_PX * 2 + 20
        bx = tx + GAP
        draw.rounded_rectangle([bx, ty, bx + bw2, ty + TAG_H], radius=TAG_R, fill=ACC)
        sx = bx + RAT_PX
        sy = ty + TAG_H // 2
        BF = btn_fg(ACC)
        for i in range(5):
            cx2 = sx + i * (sro * 2 + sg) + sro
            draw_star(draw, cx2, sy, sro, sri, BF if i < int(rating) else darken(ACC, .55))
        draw.text((sx + sw, tvc(draw, rf, ty, TAG_H)), rs2, font=rf, fill=BF)


def draw_tags(draw, genres, rating, ty, ACC, BG1, TC):
    ts, rs = 70, 78
    while True:
        tf, rf = _fp(ts, rs)
        if sum(_gw(draw, g, tf) for g in genres) + _rw_badge(draw, rating, rf) <= CONTENT_W or ts <= 36:
            break
        ts -= 4
        rs = max(36, int(ts * 78 / 70))
    tf, rf = _fp(ts, rs)
    _draw_row(draw, genres, rating, ty, ACC, TC, tf, rf)
    return TAG_H


def smart_crop_center(img_bytes, target_w, target_h):
    """Shift crop toward the brightest region when the subject is off-centre."""
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    IW, IH = img.size
    scale = max(target_w / IW, target_h / IH)
    nw, nh = int(IW * scale), int(IH * scale)

    thumb = img.resize((64, 64), Image.BILINEAR)
    pixels = list(thumb.getdata())
    total_w = 0.0
    wx = 0.0
    wy = 0.0
    for idx, (r, g, b) in enumerate(pixels):
        brightness = 0.299 * r + 0.587 * g + 0.114 * b
        tx = (idx % 64) / 64.0
        ty = (idx // 64) / 64.0
        wx += brightness * tx
        wy += brightness * ty
        total_w += brightness
    if total_w == 0:
        cx_rel, cy_rel = 0.5, 0.5
    else:
        cx_rel = wx / total_w
        cy_rel = wy / total_w

    deviation = math.sqrt((cx_rel - 0.5) ** 2 + (cy_rel - 0.5) ** 2)
    if deviation < 0.15:
        cx_rel, cy_rel = 0.5, 0.5

    cx_px = int(cx_rel * nw)
    cy_px = int(cy_rel * nh)
    left = max(0, min(cx_px - target_w // 2, nw - target_w))
    top = max(0, min(cy_px - target_h // 2, nh - target_h))
    return left, top, left + target_w, top + target_h, nw, nh


# ─── CARD RENDERER ───────────────────────────────────────────────────────────
def render_card(details, watermark, poster_bytes, website=None):
    website = website or SITE_URL
    title = details.get("title", "")
    overview = details.get("overview", "")
    genres = details.get("genres", [])
    rating = details.get("rating", 0.0)
    meta = details.get("meta", "")

    pil = Image.open(io.BytesIO(poster_bytes)).convert("RGB")
    palette = _palette(poster_bytes)
    primary = _pick(palette)
    ACC = smart_accent(primary)
    BG1 = smart_bg(primary)
    BG2 = tuple(min(255, int(c * 1.6)) for c in BG1)
    BF = btn_fg(ACC)
    TC = tag_col(BG1, ACC)
    WHITE = (255, 255, 255)
    MC = (215, 215, 228)
    DC = (192, 192, 208)
    DIV = (72, 72, 88)

    card = Image.new("RGB", (CW, CH), BG1)
    draw = ImageDraw.Draw(card)
    for y in range(0, CH, 4):
        draw.rectangle([(POSTER_W - 80, y), (CW, min(y + 4, CH))], fill=blend(BG1, BG2, (y / CH) * .75))

    ratio = CH / pil.height
    nw = int(pil.width * ratio)
    res = pil.resize((nw, CH), Image.BILINEAR)
    l, _t, r, _b, _nw, _nh = smart_crop_center(poster_bytes, POSTER_W, CH)
    card.paste(res.crop((l, 0, l + POSTER_W, CH)), (0, 0))

    fade = Image.new("RGBA", (420, CH))
    fd = ImageDraw.Draw(fade)
    for x in range(0, 420, 2):
        fd.rectangle([(x, 0), (x + 2, CH)], fill=(*BG1, int(255 * (x / 420) ** 1.6)))
    c4 = card.convert("RGBA")
    c4.paste(fade, (POSTER_W - 420, 0), fade)
    card = c4.convert("RGB")

    vig = Image.new("RGBA", (110, CH))
    vd = ImageDraw.Draw(vig)
    for x in range(0, 110, 2):
        vd.rectangle([(x, 0), (x + 2, CH)], fill=(0, 0, 0, int(180 * (1 - x / 110) ** 2.2)))
    c4 = card.convert("RGBA")
    c4.paste(vig, (0, 0), vig)
    card = c4.convert("RGB")

    draw = ImageDraw.Draw(card)
    draw.rectangle([(POSTER_W - 120, 0), (CW, 12)], fill=ACC)

    wf = F["wmark"]
    wtw = int(draw.textlength(watermark, font=wf))
    wx = CW - wtw - MARGIN_R
    wy = 72
    pd = 34
    draw.rounded_rectangle([wx - pd, wy - 18, wx + wtw + pd, wy + wf.size + 18], radius=58, fill=ACC)
    draw.text((wx, tvc(draw, wf, wy - 18, wf.size + 36)), watermark, font=wf, fill=BF)

    draw.text((RIGHT_X, 290), meta, font=F["meta"], fill=MC)

    ty = 400
    tup = title.upper()
    tf2, tlines = fit_title(tup, draw, CONTENT_W)
    lh_t = tf2.size + 14
    for i, ln in enumerate(tlines):
        draw.text((RIGHT_X, ty + i * lh_t), ln, font=tf2, fill=WHITE)
    tb = ty + len(tlines) * lh_t + 6

    tag_y = tb + 80
    tags_h = draw_tags(draw, genres, rating, tag_y, ACC, BG1, TC)
    dv = tag_y + tags_h + 72
    draw.rectangle([(RIGHT_X, dv), (CW - MARGIN_R, dv + 3)], fill=DIV)
    dy = dv + 62
    dl = []
    for ml in [5, 4]:
        dl = wrap(overview, F["desc"], draw, CONTENT_W, ml)
        lh = F["desc"].size + 38
        if dy + len(dl) * lh + 62 + 78 + 148 + 20 <= CH - 108:
            break
    lh = F["desc"].size + 38
    for i, ln in enumerate(dl):
        draw.text((RIGHT_X, dy + i * lh), ln, font=F["desc"], fill=DC)
    dv2 = dy + len(dl) * lh + 62
    draw.rectangle([(RIGHT_X, dv2), (CW - MARGIN_R, dv2 + 3)], fill=DIV)

    by = dv2 + 78
    bh = 148
    br = 74
    bpx = 100
    psz = 62
    pgap = 36
    wnt = BTN_WATCH
    wntw = int(draw.textlength(wnt, font=F["btn"]))
    wnw = psz + pgap + wntw + bpx * 2
    draw.rounded_rectangle([RIGHT_X, by, RIGHT_X + wnw, by + bh], radius=br, fill=ACC)
    play_tri(draw, RIGHT_X + bpx, by + (bh - psz) // 2, psz, BF)
    draw.text((RIGHT_X + bpx + psz + pgap, tvc(draw, F["btn"], by, bh)), wnt, font=F["btn"], fill=BF)

    bmx = RIGHT_X + wnw + 44
    draw.rounded_rectangle([bmx, by, bmx + bh, by + bh], radius=br, outline=TC, width=4)
    bcx = bmx + bh // 2
    by1_ = by + 30
    by2_ = by + bh - 28
    draw.polygon([(bcx - 28, by1_), (bcx + 28, by1_), (bcx + 28, by2_), (bcx, by2_ - 24), (bcx - 28, by2_)], fill=ACC)

    mix = bmx + bh + 44
    mit = BTN_INFO
    mitw = int(draw.textlength(mit, font=F["btn"]))
    miw = mitw + bpx * 2
    draw.rounded_rectangle([mix, by, mix + miw, by + bh], radius=br, outline=TC, width=4)
    draw.text((mix + (miw - mitw) // 2, tvc(draw, F["btn"], by, bh)), mit, font=F["btn"], fill=TC)

    draw.text((RIGHT_X, CH - 108), website, font=F["url"], fill=ACC)
    wm2 = int(draw.textlength(watermark.lower(), font=F["wmark_sm"]))
    draw.text((CW - MARGIN_R - wm2, CH - 104), watermark.lower(), font=F["wmark_sm"], fill=DIV)
    draw.rectangle([(0, CH - 14), (POSTER_W, CH)], fill=ACC)

    card = card.filter(ImageFilter.UnsharpMask(radius=1.5, percent=130, threshold=2))
    buf = io.BytesIO()
    card.save(buf, format="JPEG", quality=88, subsampling=2, optimize=False)
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
        rt = d.get("runtime", 0)
        meta = f"{year}  ·  {rt} min" if rt else year
        status = d.get("status", "N/A")
        episodes = "N/A"
    else:
        title = d.get("name", "")
        year = (d.get("first_air_date", ""))[:4]
        seasons = d.get("number_of_seasons", 1)
        eps = d.get("number_of_episodes", "?")
        meta = f"{year}  ·  {seasons} Season{'s' if seasons != 1 else ''}  ·  {eps} Eps"
        status = d.get("status", "N/A")
        episodes = str(eps)

    genres = [g["name"] for g in d.get("genres", [])]
    rating = round(d.get("vote_average", 0) / 2, 1)
    overview = d.get("overview", "")

    return dict(
        title=title, year=year, meta=meta, genres=genres, rating=rating,
        overview=overview, status=status, episodes=episodes,
        audio="English",
    )


def get_posters(tmdb_id, media_type):
    ep = f"/movie/{tmdb_id}/images" if media_type == "movie" else f"/tv/{tmdb_id}/images"
    data = _tmdb(ep, include_image_language="en,null")
    imgs = data.get("posters", [])
    if not imgs:
        return []
    srt = sorted(imgs, key=lambda x: x.get("vote_average", 0), reverse=True)
    return [TMDB_IMG_ORI + x["file_path"] for x in srt]


def fetch_poster_bytes(tmdb_id, media_type):
    posters = get_posters(tmdb_id, media_type)
    if not posters:
        raise ValueError("No poster image found for this title")
    return _fetch(posters[0])
