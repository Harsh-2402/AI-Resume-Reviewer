"""End-to-end batch run with faked LLM/HTTP: one invalid PDF, one duplicate, one GitHub failure — batch continues."""
import pytest

from models.analysis import (
    CandidateEvaluation, EducationAnalysis, JDSkillCoverage, ProjectAnalysis, ProjectAssessment, SkillsAnalysis,
)
from models.candidate import CandidateProfile, Education, Project, TechnicalSkills
from models.jd import JobProfile
from models.result import CandidateResult
from services import github_service, url_service, zip_service
from tests.conftest import make_pdf, make_zip
from tests.fakes import FakeSession
from workflow.batch_graph import run_batch, stream_batch
from workflow.events import ProgressEvent


@pytest.fixture
def batch_env(monkeypatch, fake_llm, tmp_path):
    monkeypatch.setattr(github_service, "session", FakeSession())  # every GitHub call → 404
    monkeypatch.setattr(url_service, "session", FakeSession())
    fake_llm.responses[JobProfile] = JobProfile(job_title="Backend Intern", required_skills=["Python", "FastAPI", "PostgreSQL"])

    def profile_factory(prompt):
        name = "Alice Strong" if "Alice" in prompt else "Bob Basic"
        return CandidateProfile(
            candidate_name=name, email=f"{name.split()[0].lower()}@x.com",
            github_url="https://github.com/ghostuser" if name.startswith("Alice") else "",
            education=[Education(degree="B.S. CS", gpa="3.8" if name.startswith("Alice") else "", coursework=["Databases"])],
            technical_skills=TechnicalSkills(programming_languages=["Python"], frameworks=["FastAPI"] if name.startswith("Alice") else []),
            projects=[Project(name=f"{name} Project", technologies=["Python", "FastAPI"], github_url="https://github.com/ghostuser/proj")],
        )

    fake_llm.factories[CandidateProfile] = profile_factory
    fake_llm.factories[ProjectAnalysis] = lambda prompt: ProjectAnalysis(assessments=[ProjectAssessment(
        name=("Alice Strong Project" if "Alice" in prompt else "Bob Basic Project"),
        depth="Advanced" if "Alice" in prompt else "Basic", jd_relevance="Direct", confidence="High")])
    fake_llm.responses[EducationAnalysis] = EducationAnalysis(degree_relevance="Direct", academic_strength="Strong", confidence="High")
    fake_llm.responses[SkillsAnalysis] = SkillsAnalysis(jd_coverage=[JDSkillCoverage(jd_skill="Python", status="Direct Match")], confidence="High")
    fake_llm.responses[CandidateEvaluation] = CandidateEvaluation(top_strength="Projects", interview_questions=["Q1"])

    zip_bytes = make_zip({
        "alice.pdf": make_pdf("Alice Strong\nalice@x.com\nB.S. CS GPA 3.8\nProjects: Alice Strong Project"),
        "bob.pdf": make_pdf("Bob Basic\nbob@x.com\nProjects: Bob Basic Project"),
        "bob_copy.pdf": make_pdf("Bob Basic\nbob@x.com\nProjects: Bob Basic Project"),
        "broken.pdf": b"%PDF-1.4 garbage garbage",
    })
    extraction = zip_service.extract_resumes(zip_bytes, str(tmp_path))
    inputs = [{"candidate_id": f.candidate_id, "resume_file": f.filename, "file_path": f.path, "duplicate_of": f.duplicate_of}
              for f in extraction.files]
    return inputs


def test_batch_continues_past_failures_and_ranks(batch_env):
    events: list[ProgressEvent] = []
    final = {}
    for item in stream_batch("Backend intern JD text long enough to pass validation", batch_env, {"max_concurrent_candidates": 2}):
        if isinstance(item, ProgressEvent):
            events.append(item)
        else:
            final = item

    results = {r["candidate_id"]: CandidateResult.model_validate(r) for r in final["ranking"]}
    assert len(results) == 4
    assert results["CAND-001"].status in ("Completed", "Completed with Warnings")  # alice
    assert results["CAND-002"].status in ("Completed", "Completed with Warnings")  # bob
    assert results["CAND-003"].status == "Duplicate" and results["CAND-003"].duplicate_of == "CAND-002"
    assert results["CAND-004"].status == "Failed" and results["CAND-004"].errors

    ranked = [r for r in final["ranking"] if r["rank"]]
    assert [r["candidate_id"] for r in ranked] == ["CAND-001", "CAND-002"]
    assert ranked[0]["scorecard"]["overall_score"] > ranked[1]["scorecard"]["overall_score"]
    alice = results["CAND-001"]
    assert alice.github_analysis.status == "not_found"
    assert alice.scorecard.score_of("github") is None
    assert any("not found" in w for w in alice.warnings)
    assert alice.evaluation.interview_questions == ["Q1"]

    assert final["stats"]["failed"] == 1 and final["stats"]["duplicates"] == 1 and final["stats"]["ranked"] == 2
    assert final["report_bytes"][:2] == b"PK" and final["report_filename"].endswith(".xlsx")

    stages_alice = {e.stage for e in events if e.candidate_id == "CAND-001" and e.status == "completed"}
    assert {"parser", "extractor", "education", "skills", "projects", "github", "evidence", "scoring", "evaluator", "candidate"} <= stages_alice
    assert any(e.candidate_id == "CAND-004" and e.stage == "parser" and e.status == "failed" for e in events)
    assert any(e.candidate_id == "CAND-003" and e.status == "duplicate" for e in events)
    batch_stages = [e.stage for e in events if e.candidate_id == ""]
    assert batch_stages[0] == "batch" and "jd" in batch_stages and "ranking" in batch_stages and "report" in batch_stages
    assert events[-1].stage == "batch" and events[-1].status == "completed"


def test_run_batch_returns_final_state(batch_env):
    final = run_batch("Backend intern JD text long enough to pass validation", batch_env[:2], {})
    assert final["stats"]["ranked"] == 2 and len(final["ranking"]) == 2
