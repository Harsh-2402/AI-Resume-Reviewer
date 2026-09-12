from models.analysis import (
    AchievementAnalysis, AchievementAssessment, CertificationAnalysis, CertificationAssessment,
    CourseworkMatch, EducationAnalysis, EvidenceAnalysis, JDSkillCoverage, ProjectAnalysis,
    ProjectAssessment, SkillAssessment, SkillsAnalysis, TransferableMatch,
)
from models.candidate import CandidateProfile, Education, Project, TechnicalSkills
from models.github import GitHubAnalysis
from models.jd import JobProfile
from scoring.internship_scorer import project_score, score_candidate
from scoring.weights import classify, recommend

JD = JobProfile(required_skills=["Python", "FastAPI", "PostgreSQL"])


def _strong_profile():
    return CandidateProfile(
        candidate_name="A",
        education=[Education(degree="B.S. CS", gpa="3.8", coursework=["Databases", "Distributed Systems"])],
        technical_skills=TechnicalSkills(programming_languages=["Python"], frameworks=["FastAPI"], databases=["PostgreSQL"], devops=["Docker"]),
        projects=[Project(name="P1", technologies=["Python", "FastAPI"]), Project(name="P2")],
    )


def _strong_inputs():
    return dict(
        education=EducationAnalysis(degree_relevance="Direct", academic_strength="Strong",
                                    coursework_matches=[CourseworkMatch(course="Databases", relevance="Direct"),
                                                        CourseworkMatch(course="Distributed Systems", relevance="Related")], confidence="High"),
        skills=SkillsAnalysis(assessments=[SkillAssessment(skill="Python", jd_match="Direct", depth="Demonstrated"),
                                           SkillAssessment(skill="FastAPI", jd_match="Direct", depth="Demonstrated"),
                                           SkillAssessment(skill="PostgreSQL", jd_match="Direct", depth="Claimed")],
                              jd_coverage=[JDSkillCoverage(jd_skill="Python", status="Direct Match"),
                                           JDSkillCoverage(jd_skill="FastAPI", status="Direct Match"),
                                           JDSkillCoverage(jd_skill="PostgreSQL", status="Direct Match")], confidence="High"),
        projects=ProjectAnalysis(assessments=[ProjectAssessment(name="P1", depth="Advanced", jd_relevance="Direct", ownership="Strong", implementation_evidence="Strong"),
                                              ProjectAssessment(name="P2", depth="Intermediate", jd_relevance="Strongly Related")],
                                 progression="Clear Growth", confidence="High"),
        certifications=CertificationAnalysis(assessments=[CertificationAssessment(name="AWS CCP", cert_type="Professional Certification", jd_relevance="High")], confidence="High"),
        achievements=AchievementAnalysis(assessments=[AchievementAssessment(title="Hackathon 2nd", category="Hackathon", significance="Strong", relevance="High")], confidence="High"),
        github=GitHubAnalysis(status="analyzed", github_score=78.0, confidence="High", active_last_6_months=True),
        evidence=EvidenceAnalysis(technical_evidence_confidence="High",
                                  jd_skill_matrix=[TransferableMatch(jd_skill=s, status="Direct Match") for s in JD.required_skills]),
    )


def test_strong_candidate_scores_high_and_is_explained():
    card = score_candidate(profile=_strong_profile(), jd=JD, **_strong_inputs())
    assert card.overall_score >= 80
    assert card.classification in ("Strong Internship Candidate", "Exceptional Internship Candidate")
    assert card.recommendation in ("Recommend", "Strongly Recommend")
    assert all(c.explanation for c in card.components)
    assert abs(sum(c.applied_weight for c in card.components) - 1.0) < 1e-6
    assert card.evidence_confidence == "High"


def test_missing_github_and_certs_are_neutral_via_renormalization():
    inputs = _strong_inputs()
    with_all = score_candidate(profile=_strong_profile(), jd=JD, **inputs)

    inputs["github"] = GitHubAnalysis(status="not_provided")
    inputs["certifications"] = CertificationAnalysis()
    inputs["achievements"] = AchievementAnalysis()
    without = score_candidate(profile=_strong_profile(), jd=JD, **inputs)

    assert without.score_of("github") is None and without.score_of("certifications") is None
    assert without.component("github").applied_weight == 0.0
    assert abs(sum(c.applied_weight for c in without.components) - 1.0) < 1e-6
    # Removing N/A areas must not crater the score (< ~10 points drift, driven only by learning-potential signals)
    assert with_all.overall_score - without.overall_score < 10
    assert "renormalized" in without.explanation


def test_zero_experience_student_can_rank_highly():
    """No internships/work history anywhere in the inputs, yet strong projects+coursework → high score."""
    card = score_candidate(profile=_strong_profile(), jd=JD, **_strong_inputs())
    assert card.overall_score >= 80


def test_project_depth_beats_project_count():
    many_shallow = ProjectAnalysis(assessments=[ProjectAssessment(name=f"p{i}", depth="Basic", jd_relevance="Direct") for i in range(6)])
    one_deep = ProjectAnalysis(assessments=[ProjectAssessment(name="deep", depth="Highly Advanced", jd_relevance="Direct", ownership="Strong", implementation_evidence="Strong")])
    assert project_score(one_deep).score > project_score(many_shallow).score


def test_no_projects_scores_low_but_not_none():
    comp = project_score(ProjectAnalysis())
    assert comp.score == 15 and "No projects" in comp.explanation


def test_weights_override_changes_result():
    inputs = _strong_inputs()
    base = score_candidate(profile=_strong_profile(), jd=JD, **inputs)
    heavy_projects = score_candidate(profile=_strong_profile(), jd=JD, weights={"projects": 0.9}, **inputs)
    assert heavy_projects.overall_score != base.overall_score
    assert heavy_projects.component("projects").applied_weight > 0.5


def test_classification_thresholds_and_recommendations():
    assert classify(95) == "Exceptional Internship Candidate" and recommend(classify(95)) == "Strongly Recommend"
    assert classify(80) == "Strong Internship Candidate" and recommend(classify(80)) == "Recommend"
    assert classify(74.9) == "Good Internship Candidate" and recommend(classify(74.9)) == "Consider"
    assert classify(60) == "Potential / Review" and recommend(classify(60)) == "Needs Review"
    assert classify(55) == "Weak Match" and classify(10) == "Low Match"
    assert recommend(classify(10)) == "Do Not Prioritize"


def test_scoring_is_deterministic():
    a = score_candidate(profile=_strong_profile(), jd=JD, **_strong_inputs())
    b = score_candidate(profile=_strong_profile(), jd=JD, **_strong_inputs())
    assert a.model_dump() == b.model_dump()
