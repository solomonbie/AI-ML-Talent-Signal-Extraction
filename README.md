# AI/ML Talent Sourcer

An open-source, free-to-run tool for finding people actually active in a
given AI/ML research area — by cross-referencing arXiv, Semantic Scholar,
GitHub, and Hugging Face, instead of relying on job titles or resumes.

Input a topic ("LLM quantization", "RLHF", "vision transformers"...) and it
returns ranked researcher/engineer profiles with a transparent evidence
trail: which papers, which repos, which models, and how confident the
cross-source identity match actually is.

## Why it's built this way

This tool is deliberately built around four rules, instead of trying to
maximize "coverage" at any cost:

1. **Validate before building.** Every signal here comes from a free,
   public API — no scraping, no paid data broker.
2. **Reject what you can't verify.** We don't attempt fuzzy identity
   resolution beyond conservative name matching. A GitHub contributor or
   Hugging Face author who doesn't clearly match a paper author is kept as
   their own separate entry — not force-merged.
3. **Metrics are recomputed live, every search.** Nothing here is a cached
   "coverage" number from a stale dataset.
4. **A shared identifier is a clue, never a verdict.** Every cross-source
   match is labeled `high` / `medium` / `low` confidence, with a note
   explaining why, so you — the human reviewer — make the final call.

This is intentionally a starting point, not a finished product. Fork it,
rip out what you don't need, add the sources you care about.

## What it does NOT do (on purpose)

- No Google Scholar. There's no free/legal API for it, and scraping it
  violates their Terms of Service — so it's out of scope for an
  open-source tool meant to be safely reusable.
- No automatic identity merging on a single weak signal (e.g. one shared
  email or a fuzzy name match alone). See rule 4 above.
- No paid enrichment APIs. Everything here runs on free tiers.

## Two ways to run this

**Streamlit (recommended — one app, free hosting, no server to manage)**
Everything in a single script. Good if you just want to use the tool or
share it with someone, with the least setup.

**FastAPI + HTML (the original split version, still included)**
A real backend + a separate frontend file. Better if you want to build
other clients against the API, add auth, or extend it into a bigger service.

Both use the exact same `sources.py` / `aggregator.py` logic — only the UI
layer differs.

## Architecture

```
ai-talent-sourcer/
├── streamlit_app.py    # Streamlit version — run this for the fastest path
├── sources.py            # (copy used by streamlit_app.py)
├── aggregator.py          # (copy used by streamlit_app.py)
├── requirements.txt      # Streamlit + requests only
│
└── backend/               # FastAPI version (alternative)
│   ├── main.py             # FastAPI app — the /api/search endpoint
│   ├── sources.py           # One function per data source (arXiv, Semantic
│   │                         # Scholar, GitHub, Hugging Face) — fetch + normalize only
│   ├── aggregator.py         # Cross-source matching, confidence scoring,
│   │                         # coverage reporting — no black-box merging
│   └── requirements.txt
└── frontend/
    └── index.html            # Single-file UI, no build step, calls the backend
```

## Setup — Streamlit (recommended)

```bash
pip install -r requirements.txt

# optional: raise free rate limits
export GITHUB_TOKEN=ghp_xxx
export SEMANTIC_SCHOLAR_API_KEY=xxx

streamlit run streamlit_app.py
```

It opens in your browser automatically — no separate backend to start,
no CORS, no "is the server running" step.

### Deploy it for free (so anyone can use it, not just you)

1. Push this repo to GitHub (already done if you're reading this on GitHub).
2. Go to [streamlit.io/cloud](https://streamlit.io/cloud), sign in with
   GitHub, click "New app," pick this repo, and set the main file to
   `streamlit_app.py`.
3. If you want higher rate limits, add `GITHUB_TOKEN` and
   `SEMANTIC_SCHOLAR_API_KEY` under the app's "Secrets" — same format as
   `.env.example`.
4. Deploy. You get a public URL, free, with no server to maintain.

## Setup — FastAPI + HTML (alternative)

### 1. Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt

# optional: copy .env.example to .env and add free API keys to raise rate limits
cp .env.example .env

# if you set env vars, export them (or use a tool like python-dotenv / direnv)
export GITHUB_TOKEN=ghp_xxx            # optional
export SEMANTIC_SCHOLAR_API_KEY=xxx    # optional

uvicorn main:app --reload --port 8000
```

Confirm it's up: open `http://localhost:8000/api/health` — should return `{"status":"ok"}`.

### 2. Frontend

Just open `frontend/index.html` directly in a browser. It calls
`http://localhost:8000` by default — edit the `BACKEND_URL` constant near
the bottom of the file if your backend runs elsewhere.

(If your browser blocks local file fetches, serve it instead:
`cd frontend && python -m http.server 5500`, then visit `http://localhost:5500`.)

## API rate limits (all free tiers)

| Source | Unauthenticated | With free key/token |
|---|---|---|
| arXiv | generous, no key | — |
| Semantic Scholar | 100 req / 5 min | higher, with free API key |
| GitHub (search) | 60 req / hr | ~30 req / min with a personal access token |
| Hugging Face | generous, no key | — |

The "deep GitHub name-matching" checkbox in the UI is off by default
because it uses one extra GitHub API call per contributor — turn it on
once you have a `GITHUB_TOKEN` set, or you'll burn through the
unauthenticated limit fast.

## Roadmap ideas (not built yet)

- ORCID / DBLP as additional low-noise identity anchors
- A simple SQLite cache so repeated topic searches don't re-hit every API
- CSV/JSON export of a search's results
- A "watchlist" feature to re-run a saved topic and diff what's new

## License

MIT — see LICENSE.
