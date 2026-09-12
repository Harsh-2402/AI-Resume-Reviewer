from agents import information_extractor, jd_analyzer
from models.candidate import CandidateProfile, Certification, Education, Project
from models.jd import JobProfile
from services import llm_service
from tests.conftest import SAMPLE_RESUME


def _state(raw_text: str) -> dict:
    return {"candidate_id": "CAND-001", "raw_text": raw_text, "jd_profile": {}, "settings": {}}


def test_extractor_enriches_profile_from_regex(fake_llm):
    fake_llm.responses[CandidateProfile] = CandidateProfile(
        candidate_name="Jane Doe",
        education=[Education(degree="B.S. Computer Science", university="State University", gpa="3.7/4.0",
                             graduation_year="2025", coursework=["Data Structures", "Databases"])],
        projects=[Project(name="RAG Chatbot", technologies=["LangChain", "FastAPI"], github_url="github.com/janedoe/rag-bot")],
        certifications=[Certification(name="AWS Certified Cloud Practitioner", credential_url="https://www.credly.com/badges/abc123")],
    )
    out = information_extractor.run(_state(SAMPLE_RESUME))
    profile = CandidateProfile.model_validate(out["profile"])
    assert profile.email == "jane.doe@example.com"
    assert "555" in profile.phone
    assert profile.github_url == "https://github.com/janedoe"
    assert profile.github_username == "janedoe"
    assert profile.linkedin_url.startswith("https://linkedin.com/in/janedoe")
    assert profile.projects[0].github_url == "https://github.com/janedoe/rag-bot"
    assert "https://github.com/janedoe/rag-bot" in profile.project_links
    assert "https://tasks.janedoe.dev" in profile.project_links
    assert profile.degree == "B.S. Computer Science" and profile.gpa == "3.7/4.0"
    assert fake_llm.count(CandidateProfile) == 1


def test_extractor_derives_github_profile_from_repo_url(fake_llm):
    fake_llm.responses[CandidateProfile] = CandidateProfile(candidate_name="X")
    out = information_extractor.run(_state("X\nProject: https://github.com/someuser/cool-repo"))
    assert out["profile"]["github_url"] == "https://github.com/someuser"


def test_extractor_falls_back_to_regex_on_parse_error(fake_llm):
    def boom(prompt):
        raise llm_service.LLMParseError("bad json")

    fake_llm.factories[CandidateProfile] = boom
    out = information_extractor.run(_state(SAMPLE_RESUME))
    assert out["profile"]["email"] == "jane.doe@example.com"
    assert out["profile"]["candidate_name"] == "Unknown"
    assert any("fallback" in w for w in out["warnings"])


def test_extractor_handles_empty_text(fake_llm):
    out = information_extractor.run(_state(""))
    assert out["profile"]["candidate_name"] == "Unknown"
    assert fake_llm.count(CandidateProfile) == 0
    assert out["warnings"]


def test_jd_analyzer_fills_required_skills(fake_llm):
    fake_llm.responses[JobProfile] = JobProfile(job_title="Backend Intern", programming_languages=["Python"],
                                                 frameworks=["FastAPI"], databases=["PostgreSQL"])
    jd = jd_analyzer.analyze_jd("some jd text")
    assert jd.required_skills == ["Python", "FastAPI", "PostgreSQL"]
    assert jd.core_skills() == ["Python", "FastAPI", "PostgreSQL"]
