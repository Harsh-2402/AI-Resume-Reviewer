from datetime import datetime, timezone

import pytest
import requests

from agents.github_analyzer import analyze_github
from models.candidate import CandidateProfile, Project
from models.jd import JobProfile
from services import github_service
from tests.fakes import FakeResponse, FakeSession, commits, repo

NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)
JD = JobProfile(required_skills=["Python", "FastAPI", "PostgreSQL", "Docker"], programming_languages=["Python"],
                frameworks=["FastAPI"], databases=["PostgreSQL"], devops=["Docker"])


@pytest.fixture
def gh(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(github_service, "session", session)
    return session


def _profile(url="https://github.com/janedoe", projects=None):
    return CandidateProfile(candidate_name="Jane Doe", github_url=url, projects=projects or [])


def test_no_github_is_not_provided(gh):
    analysis, warnings = analyze_github(CandidateProfile(candidate_name="X"), JD, now=NOW)
    assert analysis.status == "not_provided" and analysis.github_score is None and warnings == []
    assert gh.calls == []


def test_profile_not_found(gh):
    analysis, warnings = analyze_github(_profile("https://github.com/ghost"), JD, now=NOW)
    assert analysis.status == "not_found" and analysis.github_score is None
    assert warnings and "not found" in warnings[0]


def test_rate_limited(gh):
    gh.route("/users/janedoe", FakeResponse(403, {"message": "API rate limit exceeded"}, {"X-RateLimit-Remaining": "0"}))
    analysis, warnings = analyze_github(_profile(), JD, now=NOW)
    assert analysis.status == "rate_limited" and analysis.github_score is None
    assert any("GITHUB_TOKEN" in w for w in warnings)


def test_timeout_is_error_not_crash(gh):
    gh.route("/users/janedoe", requests.exceptions.Timeout())
    analysis, warnings = analyze_github(_profile(), JD, now=NOW)
    assert analysis.status == "error" and warnings


def test_full_analysis_scores_relevant_repo(gh):
    gh.route("/users/janedoe/repos", FakeResponse(200, [
        repo("rag-bot", description="FastAPI + PostgreSQL retrieval service in Docker", topics=["fastapi"]),
        repo("dotfiles", language="Shell", pushed="2024-01-01T00:00:00Z"),
        repo("forked-thing", fork=True),
    ]))
    gh.route("/users/janedoe", FakeResponse(200, {"login": "janedoe", "public_repos": 3}))
    gh.route("/repos/janedoe/rag-bot/languages", FakeResponse(200, {"Python": 9000, "Dockerfile": 200}))
    gh.route("/repos/janedoe/rag-bot/readme", FakeResponse(200, {"size": 2400}))
    gh.route("/repos/janedoe/rag-bot/git/trees/main", FakeResponse(200, {"tree": [
        {"path": "app/main.py", "type": "blob"}, {"path": "app/db.py", "type": "blob"},
        {"path": "tests/test_api.py", "type": "blob"}, {"path": ".github/workflows/ci.yml", "type": "blob"},
        {"path": "Dockerfile", "type": "blob"}, {"path": "LICENSE", "type": "blob"},
    ] + [{"path": f"app/mod{i}.py", "type": "blob"} for i in range(20)]}))
    gh.route("/repos/janedoe/rag-bot/commits", FakeResponse(200, commits(30), {"Link": '<x?page=2>; rel="next", <x?page=3>; rel="last"'}))
    gh.route("/repos/janedoe/dotfiles/languages", FakeResponse(200, {"Shell": 100}))
    gh.route("/repos/janedoe/dotfiles/readme", FakeResponse(404, {"message": "Not Found"}))
    gh.route("/repos/janedoe/dotfiles/git/trees/main", FakeResponse(200, {"tree": [{"path": ".bashrc", "type": "blob"}]}))
    gh.route("/repos/janedoe/dotfiles/commits", FakeResponse(200, commits(2, meaningful=False)))

    profile = _profile(projects=[Project(name="RAG Bot", github_url="https://github.com/janedoe/rag-bot")])
    analysis, warnings = analyze_github(profile, JD, now=NOW)
    assert analysis.status == "analyzed" and warnings == []
    assert analysis.public_repos == 3 and analysis.analyzed_repos == 2
    assert "1 forked repositories excluded" in analysis.notes
    top = analysis.relevant_repos[0]
    assert top.name == "rag-bot" and top.inspected and top.has_tests and top.has_ci and top.has_docker and top.has_license
    assert top.commit_count > 30 and top.relevance == "Direct"
    assert set(analysis.technology_evidence) >= {"FastAPI", "PostgreSQL", "Docker", "Python"}
    assert analysis.active_last_6_months is True
    assert analysis.github_score is not None and 55 <= analysis.github_score <= 100
    assert analysis.breakdown.testing_ci == 100.0
    assert analysis.confidence == "Medium"


def test_commit_count_is_supporting_not_dominant(gh):
    """A repo with 1000 trivial commits must not outscore a well-built one with 40 meaningful commits."""
    def setup(name, n_link_pages, meaningful, has_tests):
        gh.route(f"/repos/janedoe/{name}/languages", FakeResponse(200, {"Python": 1}))
        gh.route(f"/repos/janedoe/{name}/readme", FakeResponse(200, {"size": 2000}))
        tree = [{"path": "main.py", "type": "blob"}] + ([{"path": "tests/test_x.py", "type": "blob"}, {"path": ".github/workflows/ci.yml", "type": "blob"}] if has_tests else [])
        gh.route(f"/repos/janedoe/{name}/git/trees/main", FakeResponse(200, {"tree": tree}))
        gh.route(f"/repos/janedoe/{name}/commits", FakeResponse(200, commits(30, meaningful), {"Link": f'<x?page={n_link_pages}>; rel="last"'}))

    gh.route("/users/janedoe/repos", FakeResponse(200, [repo("many-commits"), repo("solid")]))
    gh.route("/users/janedoe", FakeResponse(200, {"login": "janedoe", "public_repos": 2}))
    setup("many-commits", 34, meaningful=False, has_tests=False)
    setup("solid", 2, meaningful=True, has_tests=True)
    analysis, _ = analyze_github(_profile(), JD, now=NOW)
    by = {r.name: r for r in analysis.relevant_repos}
    assert by["many-commits"].commit_count > 900
    assert by["solid"].quality_score > by["many-commits"].quality_score


def test_cache_prevents_repeat_requests(gh):
    gh.route("/users/janedoe/repos", FakeResponse(200, []))
    gh.route("/users/janedoe", FakeResponse(200, {"login": "janedoe", "public_repos": 0}))
    analyze_github(_profile(), JD, now=NOW)
    analyze_github(_profile(), JD, now=NOW)
    assert len(gh.calls) == 2
