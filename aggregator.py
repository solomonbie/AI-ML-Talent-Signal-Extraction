"""
aggregator.py

This is the part of the tool that actually embodies the four lessons:

1. We only score signals we can point to concrete evidence for
   (a paper, a repo, a model) — nothing is invented.
2. We deliberately do NOT try to resolve fuzzy signals we can't verify
   cheaply (e.g. we don't attempt GitHub-username <-> real-name matching
   beyond exact/near-exact name comparison — see match_confidence()).
3. Every score is recomputed from the current query's live data, never
   cached and re-served as if it were fresh.
4. A name match across sources is a CLUE, never a VERDICT. We always
   label the confidence of a cross-source match and show the evidence
   trail so a human reviewer can override the merge.
5. A repo's star count reflects the REPO's popularity, not any one
   contributor's individual weight — so star credit is split by each
   contributor's share of commits, not handed out in full to everyone
   who ever touched the repo. Bot accounts are excluded entirely; they
   are not people and were never a real lead.
"""

import re
from datetime import datetime
from urllib.parse import quote


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation/diacritics-lite, collapse whitespace."""
    if not name:
        return ""
    name = name.lower().strip()
    name = re.sub(r"[.\-']", "", name)
    name = re.sub(r"\s+", " ", name)
    return name


def is_bot_login(login: str) -> bool:
    """
    Conservative bot filter: GitHub's own convention is that automated
    accounts (Dependabot, renovate-bot, github-actions, etc.) have
    logins ending in "[bot]". This will not catch every bot, but it
    will never wrongly exclude a real person, which is the safer
    direction to err in.
    """
    return bool(login) and login.strip().lower().endswith("[bot]")


def match_confidence(name_a: str, name_b: str) -> str:
    """
    Extremely conservative matcher on purpose (Lesson #4: a shared
    identifier is a clue, never a verdict). We only call two names a
    match if they're identical once normalized, or one is a clear
    subset of the other. Returns "exact", "partial", or "none".
    """
    a, b = normalize_name(name_a), normalize_name(name_b)
    if not a or not b:
        return "none"
    if a == b:
        return "exact"
    a_tokens, b_tokens = set(a.split()), set(b.split())
    if a_tokens and b_tokens and (a_tokens <= b_tokens or b_tokens <= a_tokens):
        return "partial"
    return "none"


def build_profiles(topic, arxiv_papers, ss_papers, github_repos, hf_models,
                    github_contributors_by_repo, github_users_by_login,
                    ss_author_affiliations=None):
    """
    Builds researcher profiles by starting from named authors (arXiv +
    Semantic Scholar, since those come with real names) and then
    layering in GitHub / Hugging Face evidence ONLY where a name match
    can be made — explicitly labeled with its confidence.
    """
    ss_author_affiliations = ss_author_affiliations or {}
    profiles = {}  # normalized_name -> profile dict

    def get_or_create(name):
        key = normalize_name(name)
        if not key:
            return None
        if key not in profiles:
            profiles[key] = {
                "name": name,
                "location": None,  # sparse — only set if a source reports one
                "sources": {"arxiv": [], "semantic_scholar": [], "github": [], "huggingface": []},
                "citation_count": 0,
                "influential_citation_count": 0,
                "github_stars": 0.0,
                "github_contributions": 0,
                "hf_downloads": 0,
                "hf_likes": 0,
                "match_notes": [],
            }
        return profiles[key]

    # --- Primary evidence: arXiv (real names, but no impact metric) ---
    for paper in arxiv_papers:
        for author in paper["authors"]:
            p = get_or_create(author)
            if p:
                p["sources"]["arxiv"].append({
                    "title": paper["title"], "url": paper["url"], "published": paper["published"],
                })

    # --- Primary evidence: Semantic Scholar (real names + citation impact) ---
    for paper in ss_papers:
        for author in paper["authors"]:
            author_name = author.get("name")
            if not author_name:
                continue
            p = get_or_create(author_name)
            if not p:
                continue
            p["sources"]["semantic_scholar"].append({
                "title": paper["title"], "url": paper["url"], "year": paper["year"],
                "citationCount": paper["citationCount"],
            })
            p["citation_count"] += paper["citationCount"]
            p["influential_citation_count"] += paper["influentialCitationCount"]

            author_id = author.get("authorId")
            if author_id and not p["location"]:
                affiliations = ss_author_affiliations.get(author_id)
                if affiliations:
                    p["location"] = ", ".join(affiliations)

    # --- Secondary evidence: GitHub. Only attach a contributor to an
    # existing profile if their public GitHub display name matches
    # (exact/partial) an author we already found in papers. Unmatched
    # contributors become their own entry — never force-merged.
    #
    # Star credit is split by each contributor's SHARE of commits among
    # the contributors we fetched for that repo, not handed out in full
    # to every single contributor — otherwise a person with 1 commit to
    # a 90,000-star repo looks identical to its lead maintainer.
    github_only = {}
    for repo in github_repos:
        contributors = [c for c in github_contributors_by_repo.get(repo["full_name"], [])
                         if not is_bot_login(c.get("login"))]
        total_contributions = sum(c["contributions"] for c in contributors) or 1

        for c in contributors:
            login = c["login"]
            share = c["contributions"] / total_contributions
            star_credit = repo["stars"] * share

            user = github_users_by_login.get(login)
            display_name = (user or {}).get("name")
            matched_key = None
            match_type = None
            if display_name:
                for key, prof in profiles.items():
                    conf = match_confidence(display_name, prof["name"])
                    if conf in ("exact", "partial"):
                        matched_key = key
                        match_type = conf
                        break
            if matched_key:
                p = profiles[matched_key]
                p["sources"]["github"].append({
                    "repo": repo["full_name"], "stars": repo["stars"],
                    "contributions": c["contributions"], "url": c["html_url"],
                })
                p["github_stars"] += star_credit
                p["github_contributions"] += c["contributions"]
                if user and user.get("location") and not p["location"]:
                    p["location"] = user["location"]
                p["match_notes"].append(
                    f"GitHub user '{login}' ({display_name}) {match_type}-matched to this profile by name — verify before treating as confirmed identity."
                )
            else:
                gkey = f"github:{login}"
                if gkey not in github_only:
                    github_only[gkey] = {
                        "name": display_name or f"@{login} (GitHub)",
                        "location": (user or {}).get("location"),
                        "sources": {"arxiv": [], "semantic_scholar": [], "github": [], "huggingface": []},
                        "citation_count": 0, "influential_citation_count": 0,
                        "github_stars": 0.0, "github_contributions": 0,
                        "hf_downloads": 0, "hf_likes": 0, "match_notes": [],
                    }
                github_only[gkey]["sources"]["github"].append({
                    "repo": repo["full_name"], "stars": repo["stars"],
                    "contributions": c["contributions"], "url": c["html_url"],
                })
                github_only[gkey]["github_stars"] += star_credit
                github_only[gkey]["github_contributions"] += c["contributions"]

    # --- Secondary evidence: Hugging Face. Same conservative approach.
    hf_only = {}
    for model in hf_models:
        author = model.get("author")
        if not author:
            continue
        matched_key = None
        match_type = None
        for key, prof in profiles.items():
            conf = match_confidence(author, prof["name"])
            if conf in ("exact", "partial"):
                matched_key = key
                match_type = conf
                break
        if matched_key:
            p = profiles[matched_key]
            p["sources"]["huggingface"].append(model)
            p["hf_downloads"] += model.get("downloads", 0)
            p["hf_likes"] += model.get("likes", 0)
            p["match_notes"].append(
                f"Hugging Face account '{author}' {match_type}-matched to this profile by name — verify before treating as confirmed identity."
            )
        else:
            hkey = f"hf:{author}"
            if hkey not in hf_only:
                hf_only[hkey] = {
                    "name": f"{author} (Hugging Face)",
                    "location": None,
                    "sources": {"arxiv": [], "semantic_scholar": [], "github": [], "huggingface": []},
                    "citation_count": 0, "influential_citation_count": 0,
                    "github_stars": 0.0, "github_contributions": 0,
                    "hf_downloads": 0, "hf_likes": 0, "match_notes": [],
                }
            hf_only[hkey]["sources"]["huggingface"].append(model)
            hf_only[hkey]["hf_downloads"] += model.get("downloads", 0)
            hf_only[hkey]["hf_likes"] += model.get("likes", 0)

    all_profiles = list(profiles.values()) + list(github_only.values()) + list(hf_only.values())

    current_year = datetime.utcnow().year

    # --- Scoring + research velocity (transparent, not a black box) ---
    for p in all_profiles:
        source_count = sum(1 for s in p["sources"].values() if len(s) > 0)
        cross_source_bonus = 40 * max(0, source_count - 1)
        p["source_count"] = source_count
        p["github_stars"] = round(p["github_stars"], 1)
        p["confidence"] = (
            "high" if source_count >= 2 else
            "medium" if (p["citation_count"] > 0 or p["github_stars"] > 0 or p["hf_downloads"] > 0) else
            "low"
        )
        p["score"] = round(
            p["citation_count"] * 1.0
            + p["influential_citation_count"] * 3.0
            + p["github_stars"] * 0.05
            + p["github_contributions"] * 0.2
            + p["hf_downloads"] * 0.0002
            + p["hf_likes"] * 0.5
            + cross_source_bonus,
            1,
        )

        # Research velocity: how recently/often this person has published,
        # not just their lifetime citation total.
        years = []
        for item in p["sources"]["arxiv"]:
            pub = item.get("published")
            if pub:
                try:
                    years.append(int(str(pub)[:4]))
                except (ValueError, TypeError):
                    pass
        for item in p["sources"]["semantic_scholar"]:
            y = item.get("year")
            if y:
                try:
                    years.append(int(y))
                except (ValueError, TypeError):
                    pass
        if years:
            p["latest_publication_year"] = max(years)
            p["recent_publications"] = sum(1 for y in years if y >= current_year - 1)
            if p["recent_publications"] >= 2:
                p["velocity"] = "rising"
            elif p["recent_publications"] == 1:
                p["velocity"] = "active"
            else:
                p["velocity"] = "quiet"
        else:
            p["latest_publication_year"] = None
            p["recent_publications"] = 0
            p["velocity"] = None

        # Direct, clickable "check this person out" links.
        github_url = p["sources"]["github"][0]["url"] if p["sources"]["github"] else None
        hf_author = p["sources"]["huggingface"][0].get("author") if p["sources"]["huggingface"] else None
        p["links"] = {
            "github": github_url,
            "huggingface": f"https://huggingface.co/{hf_author}" if hf_author else None,
            "linkedin_search": f"https://www.linkedin.com/search/results/people/?keywords={quote(p['name'])}",
        }

    all_profiles.sort(key=lambda p: p["score"], reverse=True)

    coverage = {
        "topic": topic,
        "arxiv_papers_found": len(arxiv_papers),
        "semantic_scholar_papers_found": len(ss_papers),
        "github_repos_found": len(github_repos),
        "huggingface_models_found": len(hf_models),
        "total_profiles_built": len(all_profiles),
        "cross_source_matches": sum(1 for p in all_profiles if p["source_count"] >= 2),
        "note": "Computed fresh from this query's live results — not cached from a prior run.",
    }

    return all_profiles, coverage
