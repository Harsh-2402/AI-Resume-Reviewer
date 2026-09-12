from agents.prompts import SYSTEM_PROMPT, extraction_prompt
from models.candidate import CandidateProfile
from models.state import CandidateState
from services import llm_service as llm
from utils.text import (
    dedupe_preserve,
    ensure_scheme,
    extract_email,
    extract_phone,
    extract_urls,
    github_repo_from_url,
    github_username_from_url,
    truncate,
)
import config


def _regex_fallback(raw_text: str) -> CandidateProfile:
    return CandidateProfile(
        candidate_name="Unknown",
        email=extract_email(raw_text),
        phone=extract_phone(raw_text),
    )


def enrich_with_regex(profile: CandidateProfile, raw_text: str) -> CandidateProfile:
    """Fill contact fields / URLs the LLM missed, from deterministic regexes over the raw text."""
    if not profile.email:
        profile.email = extract_email(raw_text)
    if not profile.phone:
        profile.phone = extract_phone(raw_text)

    urls = extract_urls(raw_text)
    repo_urls: list[str] = []
    for url in urls:
        low = url.lower()
        if "github.com" in low:
            if github_repo_from_url(url):
                repo_urls.append(ensure_scheme(url))
            elif not profile.github_url and github_username_from_url(url):
                profile.github_url = ensure_scheme(url)
        elif "linkedin.com" in low:
            if not profile.linkedin_url:
                profile.linkedin_url = ensure_scheme(url)
        elif "@" in url:
            continue
        else:
            profile.other_urls.append(ensure_scheme(url))

    if not profile.github_url:
        for repo in repo_urls:
            owner = github_repo_from_url(repo)
            if owner:
                profile.github_url = f"https://github.com/{owner[0]}"
                break
    elif profile.github_url:
        profile.github_url = ensure_scheme(profile.github_url)
    if profile.linkedin_url:
        profile.linkedin_url = ensure_scheme(profile.linkedin_url)
    if profile.portfolio_url:
        profile.portfolio_url = ensure_scheme(profile.portfolio_url)

    for project in profile.projects:
        for attr in ("github_url", "live_url", "demo_url"):
            val = getattr(project, attr)
            if val:
                setattr(project, attr, ensure_scheme(val))

    project_links = list(profile.project_links)
    project_links += repo_urls
    project_links += [p.github_url for p in profile.projects if p.github_url]
    project_links += [p.live_url for p in profile.projects if p.live_url]
    project_links += [p.demo_url for p in profile.projects if p.demo_url]
    project_links += [u for u in profile.other_urls if u != profile.portfolio_url]
    profile.project_links = dedupe_preserve([ensure_scheme(u) for u in project_links])
    profile.other_urls = dedupe_preserve(profile.other_urls)
    return profile


def run(state: CandidateState) -> dict:
    raw_text = state.get("raw_text", "")
    warnings: list[str] = []
    if not raw_text.strip():
        profile = _regex_fallback(raw_text)
        warnings.append("Resume text was empty; profile could not be extracted")
        return {"profile": profile.model_dump(), "warnings": warnings}

    try:
        profile = llm.generate_structured(
            extraction_prompt(truncate(raw_text, config.MAX_RESUME_CHARS)),
            CandidateProfile,
            system=SYSTEM_PROMPT,
        )
    except llm.LLMParseError as exc:
        profile = _regex_fallback(raw_text)
        warnings.append(f"Structured extraction failed; using regex fallback ({str(exc)[:80]})")

    profile = enrich_with_regex(profile, raw_text)
    if not profile.candidate_name:
        profile.candidate_name = "Unknown"
    if not profile.projects:
        warnings.append("No projects were found in the resume")
    return {"profile": profile.model_dump(), "warnings": warnings}
