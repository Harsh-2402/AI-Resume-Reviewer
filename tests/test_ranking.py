from models.candidate import CandidateProfile
from models.result import CandidateResult
from models.scoring import ComponentScore, ScoreCard
from scoring.ranking import classification_counts, mark_identity_duplicates, rank_candidates


def _result(cid, overall, projects=50.0, technical=50.0, status="Completed", email="", name=""):
    card = ScoreCard(
        overall_score=overall,
        classification="Good Internship Candidate" if overall >= 70 else "Weak Match",
        components=[ComponentScore(key="projects", label="Projects", score=projects),
                    ComponentScore(key="technical_skills", label="Technical Skills", score=technical),
                    ComponentScore(key="education", label="Education", score=60.0)],
    )
    return CandidateResult(candidate_id=cid, status=status, scorecard=card,
                           profile=CandidateProfile(candidate_name=name, email=email))


def test_rank_one_is_highest_and_failed_excluded():
    results = [_result("CAND-001", 70), _result("CAND-002", 91.4), _result("CAND-003", 82, status="Failed"),
               _result("CAND-004", 82, status="Completed with Warnings")]
    ranked = rank_candidates(results)
    assert [r.candidate_id for r in ranked] == ["CAND-002", "CAND-004", "CAND-001"]
    assert ranked[0].rank == 1 and ranked[0].interview_priority == 1
    assert next(r for r in results if r.candidate_id == "CAND-003").rank is None


def test_tie_breakers_projects_then_technical():
    results = [_result("CAND-001", 80, projects=60, technical=90), _result("CAND-002", 80, projects=70, technical=50),
               _result("CAND-003", 80, projects=60, technical=95)]
    ranked = rank_candidates(results)
    assert [r.candidate_id for r in ranked] == ["CAND-002", "CAND-003", "CAND-001"]


def test_identity_duplicates_keep_higher_score():
    results = [_result("CAND-001", 70, email="a@x.com", name="Sam Lee"), _result("CAND-002", 85, email="A@X.com", name="Sam Lee"),
               _result("CAND-003", 60, name="Other Person")]
    mark_identity_duplicates(results)
    dup = next(r for r in results if r.candidate_id == "CAND-001")
    assert dup.status == "Duplicate" and dup.duplicate_of == "CAND-002"
    ranked = rank_candidates(results)
    assert [r.candidate_id for r in ranked] == ["CAND-002", "CAND-003"]


def test_classification_counts():
    counts = classification_counts([_result("CAND-001", 75), _result("CAND-002", 55), _result("CAND-003", 75, status="Failed")])
    assert counts["Good Internship Candidate"] == 1 and counts["Weak Match"] == 1
