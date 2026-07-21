"""
streamlit_app.py

The whole tool as one Streamlit app — no separate backend, no CORS.

Run locally:
    pip install -r requirements.txt
    streamlit run streamlit_app.py
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

import streamlit as st

import sources
import aggregator
import topic_expansion

st.set_page_config(page_title="AI/ML Talent Sourcer", page_icon="🔎", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #12141C; }
    h1, h2, h3, p, span, div, label { color: #EDE9E2; }
    .stamp {
        display:inline-block; font-family:monospace; font-size:11px;
        letter-spacing:.1em; text-transform:uppercase; border:2px solid;
        border-radius:3px; padding:4px 10px; font-weight:600;
    }
    .stamp-high { color:#6FCF97; border-color:#6FCF97; }
    .stamp-medium { color:#E8A33D; border-color:#E8A33D; }
    .stamp-low { color:#6B7280; border-color:#6B7280; }
    .evidence-item {
        font-size:13px; padding:8px 10px; margin-bottom:6px;
        background:#20242F; border-radius:2px; border-left:2px solid #2C303C;
    }
    .note { color:#E8A33D; font-family:monospace; font-size:12px; }
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="note">OPEN-SOURCE · EVIDENCE-BASED</p>', unsafe_allow_html=True)
st.title("🔎 AI / ML Talent Sourcer")
st.write(
    "Give it a topic. It pulls fresh signal from arXiv, Semantic Scholar, GitHub, and "
    "Hugging Face, then triangulates who's actually active in that space — showing the "
    "evidence and confidence behind every match, never a silent merge."
)

col1, col2 = st.columns([4, 1])
with col1:
    topic = st.text_input("Topic", placeholder="e.g. LLM quantization, vision transformers, RLHF...",
                           label_visibility="collapsed")
with col2:
    search_clicked = st.button("Search", type="primary", use_container_width=True)

location_filter = st.text_input(
    "Filter by location (optional)",
    placeholder="e.g. San Francisco, Berlin, Remote",
)
st.caption(
    "Location is sparse by design: it only comes from a GitHub profile's self-reported "
    "location (needs 'deep GitHub name-matching' below) or a Semantic Scholar author "
    "affiliation, when either is publicly set. Most profiles won't have it."
)

deep_lookup = st.checkbox(
    "Deep GitHub name-matching (uses more API calls — turn on once you've set a GITHUB_TOKEN)"
)

related_terms = topic_expansion.expand_topic(topic, max_extra=2) if topic.strip() else []
expand_related = st.checkbox(
    f"Also search related terms{' (' + ', '.join(related_terms) + ')' if related_terms else ''} "
    "(uses more API calls)"
)
if topic.strip() and not related_terms:
    st.caption("No curated related terms for this topic yet — this checkbox has no effect for it.")

with st.expander("Optional: API keys (raises free rate limits)"):
    st.caption(
        "Set these as environment variables or Streamlit Cloud 'Secrets', not typed here."
    )


def _dedup(items, key_fn):
    seen = set()
    out = []
    for item in items:
        k = key_fn(item)
        if k and k not in seen:
            seen.add(k)
            out.append(item)
    return out


@st.cache_data(ttl=600, show_spinner=False)
def run_search(topic: str, deep_lookup: bool, expand_related: bool = False):
    errors = []
    topics_to_search = [topic]
    if expand_related:
        topics_to_search += topic_expansion.expand_topic(topic, max_extra=2)

    arxiv_papers, ss_papers, github_repos, hf_models = [], [], [], []

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {}
        for t in topics_to_search:
            futures[pool.submit(sources.search_arxiv, t, 15)] = ("arxiv", t)
            futures[pool.submit(sources.search_semantic_scholar, t, 15)] = ("semantic_scholar", t)
            futures[pool.submit(sources.search_github_repos, t, 6)] = ("github_repos", t)
            futures[pool.submit(sources.search_huggingface_models, t, 15)] = ("huggingface", t)
        for future in as_completed(futures):
            kind, t = futures[future]
            data, err = future.result()
            if err:
                errors.append(f"[{kind}:{t}] {err}")
                continue
            if kind == "arxiv":
                arxiv_papers.extend(data)
            elif kind == "semantic_scholar":
                ss_papers.extend(data)
            elif kind == "github_repos":
                github_repos.extend(data)
            elif kind == "huggingface":
                hf_models.extend(data)

    arxiv_papers = _dedup(arxiv_papers, lambda x: x.get("arxiv_id") or x.get("url"))
    ss_papers = _dedup(ss_papers, lambda x: x.get("url") or x.get("title"))
    github_repos = _dedup(github_repos, lambda x: x.get("full_name"))
    hf_models = _dedup(hf_models, lambda x: x.get("id"))

    ss_author_ids = [
        a.get("authorId") for paper in ss_papers for a in paper["authors"] if a.get("authorId")
    ]
    ss_author_affiliations, aff_err = sources.get_semantic_scholar_authors_batch(ss_author_ids)
    if aff_err:
        errors.append(f"[semantic_scholar_affiliations] {aff_err}")

    github_contributors_by_repo = {}
    if github_repos:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {}
            for repo in github_repos:
                owner, name = repo["owner_login"], repo["name"]
                if owner and name:
                    futures[pool.submit(sources.get_repo_contributors, owner, name, 25)] = repo["full_name"]
            for future in as_completed(futures):
                full_name = futures[future]
                contributors, err = future.result()
                github_contributors_by_repo[full_name] = contributors
                if err:
                    errors.append(f"[github_contributors:{full_name}] {err}")

    github_users_by_login = {}
    if deep_lookup:
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
        ss_author_affiliations,
    )
    coverage["expanded_terms"] = topics_to_search[1:]
    return profiles, coverage, errors, github_repos, github_contributors_by_repo


def render_evidence(items, formatter):
    for item in items:
        st.markdown(f'<div class="evidence-item">{formatter(item)}</div>', unsafe_allow_html=True)


VELOCITY_LABELS = {"rising": "🚀 Rising", "active": "🟢 Active", "quiet": "🕓 Quiet"}


def render_profile(p):
    stamp_class = f"stamp-{p['confidence']}"
    with st.container(border=True):
        top_l, top_r = st.columns([4, 1])
        with top_l:
            st.markdown(f"### {p['name']}")
            loc_bit = f" · 📍 {p['location']}" if p.get("location") else ""
            st.caption(f"score **{p['score']}** · {p['source_count']} source(s){loc_bit}")
            links = p.get("links", {})
            link_bits = []
            if links.get("github"):
                link_bits.append(f"[GitHub profile]({links['github']})")
            if links.get("huggingface"):
                link_bits.append(f"[Hugging Face profile]({links['huggingface']})")
            if links.get("linkedin_search"):
                link_bits.append(f"[Search LinkedIn]({links['linkedin_search']})")
            if link_bits:
                st.markdown(" · ".join(link_bits))
        with top_r:
            st.markdown(f'<span class="stamp {stamp_class}">{p["confidence"]} signal</span>',
                        unsafe_allow_html=True)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Citations", p["citation_count"])
        m2.metric("Influential citations", p["influential_citation_count"])
        m3.metric("GitHub stars (weighted by contribution share)", p["github_stars"])
        m4.metric("HF downloads", p["hf_downloads"])

        velocity = p.get("velocity")
        if velocity:
            label = VELOCITY_LABELS.get(velocity, velocity)
            st.caption(
                f"{label} — {p['recent_publications']} publication(s) in the last ~2 years "
                f"(latest: {p['latest_publication_year']})"
            )

        for note in p.get("match_notes", []):
            st.markdown(f":warning: *{note}*")

        with st.expander("Show evidence trail"):
            if p["sources"]["arxiv"]:
                st.markdown("**arXiv**")
                render_evidence(p["sources"]["arxiv"], lambda i: (
                    f'<a href="{i["url"]}" target="_blank">{i["title"]}</a>'
                    f'<br><span style="opacity:.6">arXiv · {(i["published"] or "")[:10]}</span>'
                ))
            if p["sources"]["semantic_scholar"]:
                st.markdown("**Semantic Scholar**")
                render_evidence(p["sources"]["semantic_scholar"], lambda i: (
                    f'<a href="{i["url"]}" target="_blank">{i["title"]}</a>'
                    f'<br><span style="opacity:.6">Semantic Scholar · {i["year"] or "n/a"} · {i["citationCount"]} citations</span>'
                ))
            if p["sources"]["github"]:
                st.markdown("**GitHub**")
                render_evidence(p["sources"]["github"], lambda i: (
                    f'<a href="{i["url"]}" target="_blank">{i["repo"]}</a>'
                    f'<br><span style="opacity:.6">GitHub · {i["stars"]}★ repo (full repo total, not weighted) · {i["contributions"]} contributions</span>'
                ))
            if p["sources"]["huggingface"]:
                st.markdown("**Hugging Face**")
                render_evidence(p["sources"]["huggingface"], lambda i: (
                    f'<a href="{i["url"]}" target="_blank">{i["id"]}</a>'
                    f'<br><span style="opacity:.6">Hugging Face · {i["downloads"]} downloads · {i["likes"]} likes</span>'
                ))


if search_clicked and topic.strip():
    st.session_state["last_topic"] = topic.strip()
    st.session_state["last_deep_lookup"] = deep_lookup
    st.session_state["last_expand_related"] = expand_related
elif search_clicked:
    st.warning("Enter a topic first.")

if "last_topic" in st.session_state:
    with st.spinner("Querying arXiv, Semantic Scholar, GitHub, Hugging Face..."):
        profiles, coverage, errors, github_repos, github_contributors_by_repo = run_search(
            st.session_state["last_topic"],
            st.session_state["last_deep_lookup"],
            st.session_state.get("last_expand_related", False),
        )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("arXiv papers", coverage["arxiv_papers_found"])
    c2.metric("S2 papers", coverage["semantic_scholar_papers_found"])
    c3.metric("GitHub repos", coverage["github_repos_found"])
    c4.metric("HF models", coverage["huggingface_models_found"])
    c5.metric("Cross-source matches", coverage["cross_source_matches"])
    st.caption(coverage["note"])
    if coverage.get("expanded_terms"):
        st.caption(f"Also searched related terms: {', '.join(coverage['expanded_terms'])}")

    if errors:
        with st.expander(f"⚠️ {len(errors)} source error(s) — click to view"):
            for e in errors:
                st.text(e)

    if location_filter.strip():
        q = location_filter.strip().lower()
        filtered_profiles = [p for p in profiles if p.get("location") and q in p["location"].lower()]
    else:
        filtered_profiles = profiles

    tab_ranked, tab_contributors = st.tabs(["🏆 Ranked profiles", "👥 Browse contributors by repo"])

    with tab_ranked:
        if location_filter.strip():
            st.caption(f"Showing {len(filtered_profiles)} of {len(profiles)} profiles matching location \"{location_filter.strip()}\"")
        if not filtered_profiles:
            if profiles and location_filter.strip():
                st.info("No profiles have location data matching that filter. Try clearing it.")
            else:
                st.info("No profiles found for this topic. Try a broader term.")
        else:
            st.markdown(f"### {len(filtered_profiles)} profile(s), ranked by score")
            for p in filtered_profiles:
                render_profile(p)

    with tab_contributors:
        st.caption(
            "Unranked, unscored — every contributor GitHub reports for each repo found, "
            "including people with just 1-2 commits. Bot accounts (e.g. dependabot) are "
            "excluded from this list too."
        )
        if not github_repos:
            st.info("No GitHub repos found for this topic.")
        for repo in github_repos:
            contributors = [
                c for c in github_contributors_by_repo.get(repo["full_name"], [])
                if not aggregator.is_bot_login(c.get("login"))
            ]
            with st.expander(f"{repo['full_name']} — {repo['stars']}★ · {len(contributors)} contributor(s) shown"):
                st.markdown(f"[Open repo on GitHub]({repo['url']})")
                if repo.get("description"):
                    st.caption(repo["description"])
                if not contributors:
                    st.caption("No contributor data returned for this repo.")
                for c in contributors:
                    st.markdown(f"- [@{c['login']}]({c['html_url']}) — {c['contributions']} commit(s)")
else:
    st.caption("Enter a topic above and hit Search to get started.")
