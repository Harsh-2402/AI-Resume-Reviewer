"""Deterministic GitHub evidence analysis. No LLM. Public data only."""
from datetime import datetime, timedelta, timezone

import config
from models.candidate import CandidateProfile
from models.github import GitHubAnalysis, GitHubScoreBreakdown, RepoAnalysis
from models.jd import JobProfile
from models.state import CandidateState
from scoring.transferable import canonical, classify_match, technologies_in_text
from services import github_service as gh
from utils.text import github_repo_from_url, github_username_from_url

GITHUB_WEIGHTS = {
    "repository_quality": 0.25,
    "meaningful_activity": 0.20,
    "technology_relevance": 0.20,
    "project_complexity": 0.15,
    "documentation": 0.10,
    "testing_ci": 0.05,
    "recent_activity": 0.05,
}

_TRIVIAL_COMMIT = ("initial commit", "update readme", "readme", "merge", "first commit", "init", "update", "fix typo", ".gitignore")
_TEST_HINTS = ("test", "spec", "__tests__")
_CI_HINTS = (".github/workflows/", ".gitlab-ci.yml", "jenkinsfile", ".circleci/", ".travis.yml", "azure-pipelines.yml", "bitbucket-pipelines.yml")
_DOCKER_HINTS = ("dockerfile", "docker-compose", "compose.yml", "compose.yaml")
_LICENSE_HINTS = ("license", "licence")
_CODE_EXT = (".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".cpp", ".c", ".cs", ".kt", ".swift", ".rb", ".php", ".scala", ".sql", ".ipynb", ".r", ".m", ".dart")


def _is_test_path(path: str) -> bool:
    segments = path.split("/")
    dirs, filename = segments[:-1], segments[-1]
    if any(d in ("test", "tests", "spec", "specs", "__tests__", "testing") for d in dirs):
        return True
    stem = filename.rsplit(".", 1)[0]
    return stem.startswith("test_") or stem.endswith(("_test", ".test", ".spec", "_spec")) or stem in ("test", "tests", "conftest")


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _resolve_username(profile: CandidateProfile) -> str:
    if profile.github_username:
        return profile.github_username
    for url in [p.github_url for p in profile.projects] + profile.project_links:
        parts = github_repo_from_url(url)
        if parts:
            return parts[0]
        user = github_username_from_url(url)
        if user:
            return user
    return ""


def _relevance_for(matched: list[str], primary_language: str, jd_techs: list[str]) -> str:
    if len(matched) >= 2:
        return "Direct"
    if len(matched) == 1:
        return "Strongly Related"
    if primary_language:
        for tech in jd_techs:
            status, _ = classify_match(tech, [primary_language])
            if status == "Direct Match":
                return "Strongly Related"
            if status in ("Strongly Related", "Transferable"):
                return "Transferable"
    return "Not Relevant"


def _base_repo(repo: dict, jd_techs: list[str]) -> RepoAnalysis:
    name = repo.get("name", "")
    description = repo.get("description") or ""
    topics = repo.get("topics") or []
    primary = repo.get("language") or ""
    text = " ".join([name.replace("-", " ").replace("_", " "), description, " ".join(topics), primary])
    matched = technologies_in_text(text, jd_techs)
    return RepoAnalysis(
        name=name,
        url=repo.get("html_url", ""),
        description=description[:300],
        primary_language=primary,
        languages=[primary] if primary else [],
        topics=topics,
        stars=int(repo.get("stargazers_count", 0) or 0),
        forks=int(repo.get("forks_count", 0) or 0),
        is_fork=bool(repo.get("fork")),
        created_at=repo.get("created_at", "") or "",
        pushed_at=repo.get("pushed_at", "") or "",
        matched_technologies=matched,
        relevance=_relevance_for(matched, primary, jd_techs),
    )


def _inspect_repo(owner: str, analysis: RepoAnalysis, default_branch: str, jd_techs: list[str]) -> int:
    """Deep-inspect one repo in place. Returns the number of sampled meaningful commits."""
    langs = gh.get_languages(owner, analysis.name)
    if langs:
        analysis.languages = list(langs.keys())
    analysis.readme_length = gh.get_readme_size(owner, analysis.name)
    analysis.has_readme = analysis.readme_length > 0

    paths, _truncated = gh.get_tree_paths(owner, analysis.name, default_branch or "HEAD")
    lower_paths = [p.lower() for p in paths]
    analysis.file_count = sum(1 for p in lower_paths if p.endswith(_CODE_EXT))
    analysis.has_tests = any(_is_test_path(p) for p in lower_paths)
    analysis.has_ci = any(any(p.startswith(h) or h in p for h in _CI_HINTS) for p in lower_paths)
    analysis.has_docker = any(any(h in p.rsplit("/", 1)[-1] for h in _DOCKER_HINTS) for p in lower_paths)
    analysis.has_license = any(p.rsplit("/", 1)[-1].split(".")[0] in _LICENSE_HINTS for p in lower_paths)

    total, recent = gh.get_commits(owner, analysis.name)
    analysis.commit_count = total
    meaningful = 0
    for c in recent:
        msg = ((c.get("commit") or {}).get("message") or "").strip().lower().split("\n")[0]
        if len(msg) >= 12 and not any(msg.startswith(t) for t in _TRIVIAL_COMMIT):
            meaningful += 1

    extra = technologies_in_text(" ".join(analysis.languages + [p for p in paths[:400]]), jd_techs)
    for tech in extra:
        if tech not in analysis.matched_technologies:
            analysis.matched_technologies.append(tech)
    analysis.relevance = _relevance_for(analysis.matched_technologies, analysis.primary_language, jd_techs)

    complexity = 0.0
    fc = analysis.file_count
    complexity += 30 if fc >= 100 else 22 if fc >= 40 else 14 if fc >= 15 else 8 if fc >= 5 else 3
    complexity += min(len(analysis.languages), 3) * 5
    complexity += 15 if analysis.has_tests else 0
    complexity += 15 if analysis.has_ci else 0
    complexity += 10 if analysis.has_docker else 0
    complexity += 10 if analysis.readme_length > 1500 else 5 if analysis.readme_length > 400 else 0
    complexity += 5 if total >= 30 else 0
    analysis.complexity_score = min(100.0, complexity)

    quality = 0.0
    quality += 20 if analysis.readme_length > 1500 else 12 if analysis.readme_length > 400 else 5 if analysis.has_readme else 0
    quality += 20 if analysis.has_tests else 0
    quality += 15 if analysis.has_ci else 0
    quality += 5 if analysis.has_license else 0
    quality += 10 if analysis.description else 0
    quality += min(analysis.stars, 10) * 2
    quality += 20 if total >= 50 else 14 if total >= 20 else 8 if total >= 8 else 4 if total >= 3 else 0
    quality += 10 if meaningful >= 10 else 5 if meaningful >= 4 else 0
    analysis.quality_score = min(100.0, quality)
    analysis.inspected = True
    return meaningful


def _score(analysis: GitHubAnalysis, jd_techs: list[str], now: datetime) -> None:
    inspected = [r for r in analysis.relevant_repos if r.inspected]
    pool = inspected or analysis.relevant_repos
    if not pool:
        return
    bd = GitHubScoreBreakdown()
    bd.repository_quality = sum(r.quality_score for r in pool) / len(pool) if inspected else 20.0

    substantive = sum(1 for r in pool if r.commit_count >= 5 or (not r.inspected and r.pushed_at))
    bd.meaningful_activity = min(100.0, substantive * 15 + min(analysis.meaningful_commits, 40) * 1.5)

    evidenced = {canonical(t) for t in analysis.technology_evidence}
    target = max(1, min(len(jd_techs), 8))
    bd.technology_relevance = min(100.0, len(evidenced) / target * 100)

    complexities = sorted((r.complexity_score for r in pool), reverse=True)
    bd.project_complexity = 0.6 * complexities[0] + 0.4 * (sum(complexities) / len(complexities)) if inspected else 15.0

    doc_scores = [100 if r.readme_length > 1500 else 65 if r.readme_length > 400 else 30 if r.has_readme else 0 for r in pool]
    bd.documentation = sum(doc_scores) / len(doc_scores) if inspected else 0.0

    any_tests, any_ci = any(r.has_tests for r in pool), any(r.has_ci for r in pool)
    bd.testing_ci = 100.0 if (any_tests and any_ci) else 60.0 if (any_tests or any_ci) else 0.0

    last = _parse_dt(analysis.last_activity)
    if last:
        age = now - last
        bd.recent_activity = 100.0 if age <= timedelta(days=90) else 70.0 if age <= timedelta(days=180) else 40.0 if age <= timedelta(days=365) else 10.0
        analysis.active_last_6_months = age <= timedelta(days=180)
    analysis.breakdown = bd
    analysis.github_score = round(sum(getattr(bd, k) * w for k, w in GITHUB_WEIGHTS.items()), 1)


def analyze_github(profile: CandidateProfile, jd: JobProfile, *, now: datetime | None = None) -> tuple[GitHubAnalysis, list[str]]:
    now = now or datetime.now(timezone.utc)
    warnings: list[str] = []
    username = _resolve_username(profile)
    if not username:
        return GitHubAnalysis(status="not_provided", explanation="No GitHub profile provided — GitHub evidence is N/A."), warnings

    analysis = GitHubAnalysis(username=username, url=f"https://github.com/{username}")
    jd_techs = jd.all_technologies()
    try:
        user = gh.get_user(username)
        repos = gh.get_repos(username)
    except gh.GitHubNotFound:
        analysis.status = "not_found"
        analysis.explanation = f"GitHub profile '{username}' was not found."
        warnings.append(f"GitHub profile '{username}' not found")
        return analysis, warnings
    except gh.GitHubRateLimited:
        analysis.status = "rate_limited"
        analysis.explanation = "GitHub API rate limit reached; GitHub evidence unavailable for this run."
        warnings.append("GitHub API rate limit reached — set GITHUB_TOKEN for higher limits")
        return analysis, warnings
    except gh.GitHubError as exc:
        analysis.status = "error"
        analysis.explanation = f"GitHub lookup failed: {exc}"
        warnings.append(f"GitHub lookup failed: {str(exc)[:80]}")
        return analysis, warnings

    analysis.public_repos = int(user.get("public_repos", len(repos)) or 0)
    own = [r for r in repos if not r.get("fork")]
    forks = len(repos) - len(own)
    if forks:
        analysis.notes.append(f"{forks} forked repositories excluded")
    if not own:
        analysis.status = "no_public_repos"
        analysis.explanation = "GitHub profile exists but has no original public repositories."
        analysis.confidence = "Low"
        return analysis, warnings

    resume_repos = {github_repo_from_url(u)[1].lower() for u in [p.github_url for p in profile.projects] + profile.project_links if github_repo_from_url(u)}
    ranked: list[RepoAnalysis] = []
    for repo in own:
        ra = _base_repo(repo, jd_techs)
        ranked.append(ra)
    order = {"Direct": 0, "Strongly Related": 1, "Transferable": 2, "Not Relevant": 3}
    # resume-referenced repos first, then by relevance; within a tier the API's pushed-desc order is kept
    ranked.sort(key=lambda r: (0 if r.name.lower() in resume_repos else 1, order[r.relevance]))

    branch_by_name = {r.get("name", ""): r.get("default_branch", "") for r in own}
    meaningful_total = 0
    partial = False
    for ra in ranked[: config.GITHUB_MAX_DEEP_REPOS]:
        try:
            meaningful_total += _inspect_repo(username, ra, branch_by_name.get(ra.name, ""), jd_techs)
        except gh.GitHubRateLimited:
            partial = True
            break
        except gh.GitHubError as exc:
            analysis.notes.append(f"Could not fully inspect {ra.name}: {str(exc)[:60]}")

    analysis.relevant_repos = ranked[: max(config.GITHUB_MAX_DEEP_REPOS, 10)]
    analysis.analyzed_repos = sum(1 for r in ranked if r.inspected)
    analysis.meaningful_commits = meaningful_total
    analysis.total_commits_sampled = sum(r.commit_count for r in ranked if r.inspected)

    langs: list[str] = []
    techs: list[str] = []
    for r in ranked:
        for lang in r.languages:
            if lang not in langs:
                langs.append(lang)
        for t in r.matched_technologies:
            if t not in techs:
                techs.append(t)
    for lang in langs:
        for tech in jd_techs:
            if classify_match(tech, [lang])[0] == "Direct Match" and tech not in techs:
                techs.append(tech)
    analysis.languages = langs
    analysis.technology_evidence = techs
    analysis.last_activity = max((r.pushed_at for r in ranked if r.pushed_at), default="")

    _score(analysis, jd_techs, now)
    analysis.status = "analyzed"
    if partial:
        analysis.notes.append("GitHub rate limit reached during inspection — analysis is partial")
        warnings.append("GitHub rate limit reached mid-analysis; GitHub evidence is partial")
        analysis.confidence = "Low"
    else:
        analysis.confidence = "High" if analysis.analyzed_repos >= 3 else "Medium" if analysis.analyzed_repos >= 1 else "Low"
    relevant = sum(1 for r in ranked if r.relevance in ("Direct", "Strongly Related"))
    analysis.explanation = (
        f"{len(own)} original public repositories; {analysis.analyzed_repos} inspected in depth; "
        f"{relevant} relevant to the role. Evidence for: {', '.join(techs[:8]) or 'none of the JD technologies'}. "
        f"Last activity {analysis.last_activity[:10] or 'unknown'}."
    )
    return analysis, warnings


def run(state: CandidateState) -> dict:
    profile = CandidateProfile.model_validate(state["profile"])
    jd = JobProfile.model_validate(state["jd_profile"])
    analysis, warnings = analyze_github(profile, jd)
    return {"github_analysis": analysis.model_dump(), "warnings": warnings}
