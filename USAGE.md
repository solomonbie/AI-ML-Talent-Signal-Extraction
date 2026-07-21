# How to use the AI/ML Talent Sourcer

A practical walkthrough — what to type, what you'll see, and how to actually
use the results to find people, not just admire a dashboard.

---

## 1. What this tool is actually for

You give it a **topic** (a research area, technique, or technology). It goes
and finds real people currently active in that space — by looking at who's
publishing papers, who's citing them, who's writing the code, and who's
shipping models — instead of relying on job titles or LinkedIn keyword
matching.

It is a **discovery tool**, not a database. Every search hits live APIs and
computes fresh results in real time. Nothing is pre-scraped or cached from
a prior run.

---

## 2. Before you search: pick a good topic

The topic box is the single biggest lever on result quality.

**Good topics** — specific enough to be relevant, common enough to have
real activity:
- "retrieval augmented generation" or "RAG"
- "LLM quantization"
- "vision transformers"
- "RLHF"
- "speculative decoding"

**Topics that will disappoint you:**
- Too broad ("AI", "machine learning") → thousands of irrelevant, generic results
- Too narrow / too new ("my specific niche sub-technique") → empty results,
  nothing published yet

If a search comes back thin, don't assume the tool is broken — try a
slightly broader or more common phrasing first.

---

## 3. Running a search — what actually happens

1. Type your topic, hit **Search**.
2. The app queries **arXiv, Semantic Scholar, GitHub, and Hugging Face**
   at the same time.
3. Across the top you'll see a coverage strip: how many papers, repos, and
   models were actually found *this run* — always live, never stale.
4. If a source failed (rate limit, timeout), you'll see it in the
   **"⚠️ source error(s)"** box — errors are shown, not hidden.

---

## 4. Reading the results — two tabs, two different jobs

### 🏆 Ranked profiles tab
This is the aggregated, scored view. Each card shows:

- **Name** and a **confidence stamp** — `high` / `medium` / `low`. This
  tells you how sure the tool is that this is really one person and not
  an accidental name collision across sources.
- **Score** — a transparent number built from citations, GitHub stars,
  contributions, and Hugging Face downloads. Higher isn't automatically
  "better fit" — it mostly reflects *visibility and reach*, not
  necessarily hands-on skill.
- **📍 Location**, when known (sparse — most profiles won't have it).
- **Quick links** — GitHub profile / Hugging Face profile / a pre-filled
  LinkedIn search, right under the name, so you can click through
  immediately.
- **"Show evidence trail"** — the actual papers, repos, and models backing
  the score. **Always open this before treating someone as a real lead.**
  The score is a starting point for triage, not a verdict.

### 👥 Browse contributors by repo tab
This is the unscored, unranked view — the "low-hanging fruit" list. For
every GitHub repo the search found, it lists **every contributor**
(up to 25), with their commit count and a direct link to their profile.

This is where you'll find people who are hands-on and active but too
small (in citations/stars) to rank high in the scored tab — often more
reachable, and just as real.

---

## 5. Filtering by location

Type into the **"Filter by location"** box (e.g. "Berlin", "Remote") and
the Ranked tab filters live — no need to search again.

**Important limitation:** location only exists when GitHub's
self-reported profile field or a Semantic Scholar author affiliation is
publicly set. Most profiles will have no location at all. Turn on
**"Deep GitHub name-matching"** before searching if you want a real shot
at populating GitHub locations (it costs more API calls, so it's off by
default).

---

## 6. A full example, start to finish

**Scenario:** You need to find 5-10 people who are genuinely hands-on with
retrieval-augmented generation, ideally with some in Europe.

1. Search **"RAG"** (broader/shorter term than the full phrase — better
   Hugging Face coverage).
2. Type **"Germany"** in the location filter, leave it for now — you'll
   apply it after seeing the full spread.
3. Check the coverage strip — confirm all four sources returned something.
   If Semantic Scholar shows 0, you likely hit its free rate limit — see
   the Troubleshooting section.
4. In the **Ranked profiles** tab, open "Show evidence trail" on the top
   5–10 people. For each one, ask: *does the actual paper/repo/model
   title genuinely match what I'm hiring for, or did they just get swept
   up by a popular repo mentioning the term once?*
5. Click their **GitHub profile** link. Look at their bio, company field,
   pinned repos — this is your first real verification step.
6. Switch to **Browse contributors by repo**. Skim the repos most
   relevant to your actual use case (not just the most-starred one) and
   look at contributors with 5–20 commits — often the most realistic,
   reachable candidates.
7. For anyone promising, click **"Search LinkedIn"** to manually confirm
   their identity and current role — the tool cannot do this step for
   you (no legal LinkedIn API exists).
8. Now apply the location filter and repeat steps 4–7 focused on that
   subset.

That's the intended loop: **search → skim ranked list for direction →
dig into evidence trail → cross-check the raw contributor list for
people the score buried → manually verify on GitHub/LinkedIn before you
reach out.**

---

## 7. What to trust, and what to double-check

| Signal | How solid is it |
|---|---|
| GitHub contribution count | Very solid — real commit history, verifiable by clicking through |
| Citation counts | Solid — from Semantic Scholar's own data |
| A cross-source name match ("high confidence") | Still just a name match — verify before treating as fact |
| GitHub stars attributed to a person | Reflects the *repo's* popularity, not necessarily that person's individual contribution weight |
| Location | Self-reported, sparse, unverified |
| "Search LinkedIn" link | A starting point only — never a confirmed identity |

---

## 8. Troubleshooting quick reference

- **Semantic Scholar shows 0 results / a 429 error** → you hit the free
  rate limit (100 requests / 5 min). Wait a few minutes, or add a free
  `SEMANTIC_SCHOLAR_API_KEY` in your app's Secrets.
- **Hugging Face looks empty** → HF search is literal keyword matching.
  Try a shorter/more common term (e.g. "RAG" instead of the full phrase).
- **Everything errors with `AttributeError`** → the deployed code is out
  of sync with what's on GitHub. Reboot the app in Manage app, or delete
  and redeploy if a reboot doesn't help.
- **125+ profiles, mostly irrelevant** → your topic was too broad, or
  matched an unrelated mega-repo. Narrow the topic.

---

## 9. What this tool will never do

- Confirm a LinkedIn identity for you (no legal API exists)
- Guarantee two profiles across sources are really the same person — it
  labels its confidence and shows you the evidence; the final call is
  yours
- Replace actually messaging and talking to the person
