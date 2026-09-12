import pytest

from agents import evidence_validator
from models.analysis import JDSkillCoverage, ProjectAnalysis, ProjectAssessment, SkillsAnalysis
from models.candidate import CandidateProfile, Certification, Project, TechnicalSkills
from models.github import GitHubAnalysis, RepoAnalysis
from models.jd import JobProfile
from services import url_service
from tests.fakes import FakeResponse, FakeSession


@pytest.fixture
def http(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(url_service, "session", session)
    return session


def _state(profile, github=None, projects=None, skills=None):
    jd = JobProfile(required_skills=["Python", "FastAPI", "PostgreSQL", "Kubernetes"])
    return {
        "profile": profile.model_dump(), "jd_profile": jd.model_dump(),
        "github_analysis": (github or GitHubAnalysis()).model_dump(),
        "project_analysis": (projects or ProjectAnalysis()).model_dump(),
        "skills_analysis": (skills or SkillsAnalysis()).model_dump(),
    }


def test_evidence_cross_checks_github_and_links(http):
    http.route("https://demo.example.com", FakeResponse(200, text="<html>Task app</html>", headers={"Content-Type": "text/html"}))
    http.route("https://gone.example.com", FakeResponse(404))
    http.route("credly.com/badges/abc", FakeResponse(200, text="AWS Certified Cloud Practitioner issued to Jane Doe", headers={"Content-Type": "text/html"}))
    profile = CandidateProfile(
        candidate_name="Jane Doe",
        technical_skills=TechnicalSkills(programming_languages=["Python"], frameworks=["FastAPI"], databases=["PostgreSQL"], devops=["Docker"]),
        projects=[Project(name="API", technologies=["Python", "FastAPI"], github_url="https://github.com/janedoe/api", live_url="https://demo.example.com"),
                  Project(name="Old", technologies=["Docker"], live_url="https://gone.example.com")],
        certifications=[Certification(name="AWS Certified Cloud Practitioner", issuer="AWS", credential_url="https://www.credly.com/badges/abc"),
                        Certification(name="Intro to SQL", issuer="Coursera")],
    )
    github = GitHubAnalysis(status="analyzed", technology_evidence=["Python", "FastAPI"], languages=["Python"],
                            relevant_repos=[RepoAnalysis(name="api")])
    projects = ProjectAnalysis(assessments=[ProjectAssessment(name="API", implementation_evidence="Weak", ownership="Unknown"),
                                            ProjectAssessment(name="Old", implementation_evidence="Moderate")])
    skills = SkillsAnalysis(jd_coverage=[JDSkillCoverage(jd_skill="Python", status="Missing")])  # LLM missed it; deterministic should win

    out = evidence_validator.run(_state(profile, github, projects, skills))
    ev = out["evidence_analysis"]
    by_skill = {s["skill"]: s for s in ev["skill_evidence"]}
    assert by_skill["Python"]["github_evidence"] and by_skill["Python"]["project_evidence"] and by_skill["Python"]["confidence"] == "High"
    assert by_skill["PostgreSQL"]["confidence"] == "Low" and "Limited public evidence" in by_skill["PostgreSQL"]["note"]
    statuses = {c["url"]: c["status"] for c in ev["project_link_checks"]}
    assert statuses["https://demo.example.com"] == "accessible" and statuses["https://gone.example.com"] == "broken"
    certs = {c["name"]: c["status"] for c in ev["certification_verifications"]}
    assert certs["AWS Certified Cloud Practitioner"] == "Verified"
    assert certs["Intro to SQL"] == "No Verification Information"
    matrix = {m["jd_skill"]: m["status"] for m in ev["jd_skill_matrix"]}
    assert matrix["Python"] == "Direct Match" and matrix["Kubernetes"] == "Transferable"
    updated = {a["name"]: a for a in out["project_analysis"]["assessments"]}
    assert updated["API"]["implementation_evidence"] == "Strong"  # Weak → Moderate (live link) → Strong (repo on GitHub)
    assert updated["API"]["ownership"] == "Moderate"
    assert updated["Old"]["implementation_evidence"] == "Moderate"  # broken link never downgrades
    assert any("not penalized" in n for n in ev["notes"])
    assert ev["technical_evidence_confidence"] in ("Medium", "High")


def test_no_github_and_no_links_yields_low_or_medium(http):
    profile = CandidateProfile(candidate_name="X", technical_skills=TechnicalSkills(programming_languages=["Python"]))
    out = evidence_validator.run(_state(profile))
    ev = out["evidence_analysis"]
    assert ev["technical_evidence_confidence"] == "Low"
    assert any("No GitHub profile" in n for n in ev["notes"])
    assert http.calls == []
