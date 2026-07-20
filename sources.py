"""
sources.py

One function per external data source. Each function does ONE job:
go get raw signal for a topic and return it in a clean, common-ish shape.

Design principle (from the lessons this tool is built around):
we do NOT decide here who is "the same person" across sources — that
happens later in aggregator.py, deliberately, with evidence. A source
file's only job is to fetch and normalize its own data honestly,
including saying when it found nothing.
"""

import os
import xml.etree.ElementTree as ET
import requests

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
SEMANTIC_SCHOLAR_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()

REQUEST_TIMEOUT = 15


def _get(url, headers=None, params=None):
    """Thin wrapper so every source fails the same (soft) way."""
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            return resp, None
        return None, f"{url} -> HTTP {resp.status_code}: {resp.text[:200]}"
    except requests.RequestException as e:
        return None, f"{url} -> request failed: {e}"


# ---------------------------------------------------------------------------
# arXiv — free, no key, no rate-limit auth needed. Good for recent papers.
# ---------------------------------------------------------------------------
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}


def search_arxiv(topic: str, max_results: int = 20):
    """
    Returns a list of {title, authors[], published, arxiv_id, url, summary}
    """
    url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{topic}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    resp, err = _get(url, params=params)
    if err:
        return [], err

    papers = []
    try:
        root = ET.fromstring(resp.text)
        for entry in root.findall("atom:entry", ARXIV_NS):
            title_el = entry.find("atom:title", ARXIV_NS)
            id_el = entry.find("atom:id", ARXIV_NS)
            published_el = entry.find("atom:published", ARXIV_NS)
            summary_el = entry.find("atom:summary", ARXIV_NS)
            authors = [
                a.find("atom:name", ARXIV_NS).text.strip()
                for a in entry.findall("atom:author", ARXIV_NS)
                if a.find("atom:name", ARXIV_NS) is not None
            ]
            papers.append({
                "title": (title_el.text or "").strip().replace("\n", " ") if title_el is not None else "",
                "authors": authors,
                "published": published_el.text if published_el is not None else None,
                "arxiv_id": id_el.text if id_el is not None else None,
                "url": id_el.text if id_el is not None else None,
                "summary": (summary_el.text or "").strip().replace("\n", " ")[:400] if summary_el is not None else "",
            })
    except ET.ParseError as e:
        return [], f"arXiv response could not be parsed: {e}"

    return papers, None


# ---------------------------------------------------------------------------
# Semantic Scholar — free, no key required (100 req / 5 min unauthenticated,
# higher with a free API key). Gives citation counts, which is our strongest
# free signal of research influence.
# ---------------------------------------------------------------------------
def search_semantic_scholar(topic: str, limit: int = 20):
    """
    Returns a list of {title, authors[({name, authorId})], year,
    citationCount, influentialCitationCount, url, venue}
    """
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    headers = {}
    if SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY

    params = {
        "query": topic,
        "limit": limit,
        "fields": "title,year,authors,citationCount,influentialCitationCount,url,venue",
    }
    resp, err = _get(url, headers=headers, params=params)
    if err:
        return [], err

    data = resp.json().get("data", [])
    papers = []
    for p in data:
        papers.append({
            "title": p.get("title"),
            "authors": p.get("authors") or [],  # [{authorId, name}]
            "year": p.get("year"),
            "citationCount": p.get("citationCount") or 0,
            "influentialCitationCount": p.get("influentialCitationCount") or 0,
            "url": p.get("url"),
            "venue": p.get("venue"),
        })
    return papers, None


# ---------------------------------------------------------------------------
# GitHub — free, 60 req/hr unauthenticated, 5000 req/hr with a personal
# access token (set GITHUB_TOKEN). Search endpoint has its own, stricter
# limit (~30 req/min authenticated), so we keep calls minimal.
# ---------------------------------------------------------------------------
def _github_headers():
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def search_github_repos(topic: str, max_results: int = 10):
    """
    Returns a list of {name, full_name, description, stars, url, owner_login}
    for the most-starred repos matching the topic.
    """
    url = "https://api.github.com/search/repositories"
    params = {
        "q": f"{topic} in:name,description,readme",
        "sort": "stars",
        "order": "desc",
        "per_page": max_results,
    }
    resp, err = _get(url, headers=_github_headers(), params=params)
    if err:
        return [], err

    items = resp.json().get("items", [])
    repos = []
    for r in items:
        repos.append({
            "name": r.get("name"),
            "full_name": r.get("full_name"),
            "description": r.get("description"),
            "stars": r.get("stargazers_count", 0),
            "url": r.get("html_url"),
            "owner_login": (r.get("owner") or {}).get("login"),
        })
    return repos, None


def get_repo_contributors(owner: str, repo: str, max_results: int = 8):
    """
    Returns a list of {login, contributions, html_url} for a single repo.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/contributors"
    params = {"per_page": max_results}
    resp, err = _get(url, headers=_github_headers(), params=params)
    if err:
        return [], err
    contributors = []
    for c in resp.json():
        contributors.append({
            "login": c.get("login"),
            "contributions": c.get("contributions", 0),
            "html_url": c.get("html_url"),
        })
    return contributors, None


def get_github_user(login: str):
    """
    Resolves a GitHub username to a real display name (when public),
    company, and bio. This is the only thing that lets us try to match
    a GitHub contributor to a paper author later — and even then it's
    treated as a clue, not a verdict.
    """
    url = f"https://api.github.com/users/{login}"
    resp, err = _get(url, headers=_github_headers())
    if err:
        return None, err
    u = resp.json()
    return {
        "login": u.get("login"),
        "name": u.get("name"),
        "company": u.get("company"),
        "bio": u.get("bio"),
        "html_url": u.get("html_url"),
        "followers": u.get("followers", 0),
    }, None


# ---------------------------------------------------------------------------
# Hugging Face Hub — free, no key needed for public read search.
# ---------------------------------------------------------------------------
def search_huggingface_models(topic: str, max_results: int = 15):
    """
    Returns a list of {id, author, downloads, likes, url}
    """
    url = "https://huggingface.co/api/models"
    params = {"search": topic, "sort": "downloads", "direction": -1, "limit": max_results}
    resp, err = _get(url, params=params)
    if err:
        return [], err

    models = []
    for m in resp.json():
        model_id = m.get("id") or m.get("modelId") or ""
        author = model_id.split("/")[0] if "/" in model_id else None
        models.append({
            "id": model_id,
            "author": author,
            "downloads": m.get("downloads", 0),
            "likes": m.get("likes", 0),
            "url": f"https://huggingface.co/{model_id}" if model_id else None,
        })
    return models, None
