"""
main.py — FastAPI backend.

Run with:
    uvicorn main:app --reload --port 8000

Then open frontend/index.html in a browser (or serve it, see README).
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

import sources
import aggregator

app = FastAPI(title="AI/ML Talent Sourcer", version="0.1.0")

# Wide-open CORS since this is meant to be run locally / self-hosted by
# whoever forks it. Tighten this if you deploy it publicly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/search")
def search(
    topic: str = Query(..., min_length=2, description="Topic to search, e.g. 'LLM quantization'"),
    max_papers: int = Query(15, ge=1, le=50),
    max_repos: int = Query(6, ge=1, le=15),
    max_models: int = Query(15, ge=1, le=50),
    deep_github_lookup: bool = Query(
        False,
        description="If true, also fetches GitHub contributors' public display "
                     "names to attempt name-matching against paper authors. "
                     "Uses several extra GitHub API calls per repo — costs more "
                     "of your rate limit, so it's opt-in.",
    ),
):
    errors = []

    # Fetch the three independent, name-bearing / metric-bearing sources
    # in parallel — they don't depend on each other.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(sources.search_arxiv, topic, max_papers): "arxiv",
            pool.submit(sources.search_semantic_scholar, topic, max_papers): "semantic_scholar",
            pool.submit(sources.search_github_repos, topic, max_repos): "github_repos",
            pool.submit(sources.search_huggingface_models, topic, max_models): "huggingface",
        }
        results = {}
        for future in as_completed(futures):
            key = futures[future]
            data, err = future.result()
            results[key] = data
            if err:
                errors.append(f"[{key}] {err}")

    arxiv_papers = results.get("arxiv", [])
    ss_papers = results.get("semantic_scholar", [])
    github_repos = results.get("github_repos", [])
    hf_models = results.get("huggingface", [])

    # GitHub contributors — one call per repo we found, in parallel.
    github_contributors_by_repo = {}
    if github_repos:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {}
            for repo in github_repos:
                owner, name = repo["owner_login"], repo["name"]
                if owner and name:
                    futures[pool.submit(sources.get_repo_contributors, owner, name)] = repo["full_name"]
            for future in as_completed(futures):
                full_name = futures[future]
                contributors, err = future.result()
                github_contributors_by_repo[full_name] = contributors
                if err:
                    errors.append(f"[github_contributors:{full_name}] {err}")

    # Optional, opt-in: resolve GitHub usernames to public display names so
    # the aggregator can attempt a conservative name match. Skipped by
    # default to conserve GitHub's rate limit.
    github_users_by_login = {}
    if deep_github_lookup:
        all_logins = {
            c["login"]
            for contributors in github_contributors_by_repo.values()
            for c in contributors
            if c.get("login")
        }
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(sources.get_github_user, login): login for login in all_logins}
            for future in as_completed(futures):
                login = futures[future]
                user, err = future.result()
                if user:
                    github_users_by_login[login] = user
                elif err:
                    errors.append(f"[github_user:{login}] {err}")

    profiles, coverage = aggregator.build_profiles(
        topic, arxiv_papers, ss_papers, github_repos, hf_models,
        github_contributors_by_repo, github_users_by_login,
    )

    return {
        "topic": topic,
        "coverage": coverage,
        "profiles": profiles,
        "raw_counts": {
            "arxiv_papers": len(arxiv_papers),
            "semantic_scholar_papers": len(ss_papers),
            "github_repos": len(github_repos),
            "huggingface_models": len(hf_models),
        },
        "errors": errors,  # surfaced, not hidden — Lesson #3: be honest about what worked
    }
