# Poster Generator (Vercel, free tier)

Search a movie/show on TMDB, generate a poster image + caption. No bot, no
buttons, no cutout/card modes — just this one thing.

## Files
```
.
├── index.html          ← the whole frontend (no framework)
├── api/
│   ├── search.py        ← GET /api/search?q=..&type=movie|tv
│   └── generate.py       ← GET /api/generate?id=..&type=movie|tv
├── lib/
│   └── poster_lib.py      ← TMDB calls + poster rendering + caption
├── fonts/
│   └── Poppins-Bold.ttf
├── requirements.txt
└── vercel.json
```

## 1. Get a TMDB API key
Free, from https://www.themoviedb.org/settings/api

## 2. Push to GitHub
From Termux:
```
cd vercel-poster
git init
git add .
git commit -m "poster generator"
git branch -M main
git remote add origin https://github.com/<you>/poster-generator.git
git push -u origin main
```

## 3. Import into Vercel
1. vercel.com → New Project → import the GitHub repo
2. Framework preset: "Other" (it'll auto-detect the Python functions)
3. Add environment variable: `TMDB_API_KEY` = your key
4. Deploy

That's it — no build step needed, it's static HTML + two Python functions.

## Customizing
- Watermark text: edit `DEFAULT_WATERMARKS` in `lib/poster_lib.py`
- Website text shown on poster: set `SITE_WATERMARK_URL` env var in Vercel,
  or edit `DEFAULT_WEBSITE` in `lib/poster_lib.py`
- Caption layout: edit `CAPTION_TEMPLATES` in `lib/poster_lib.py`
