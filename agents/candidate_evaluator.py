"""Final recruiter-facing narrative + interview questions (LLM). Scores are inputs, never outputs."""
from agents.prompts import SYSTEM_PROMPT, evaluator_prompt
from models.analysis import (
    AchievementAnalysis,
    CandidateEvaluation,
    CertificationAnalysis,
    EducationAnalysis,
    EvidenceAnalysis,
    ProjectAnalysis,
    SkillsAnalysis,
)
from models.candidate import CandidateProfile
from models.github import GitHubAnalysis
from models.jd import JobProfile
from models.scoring import ScoreCard
from models.state import CandidateState
from services import llm_service as llm


def build_summary(profile: CandidateProfile, scorecard: ScoreCard, education: EducationAnalysis, skills: SkillsAnalysis,
                  projects: ProjectAnalysis, certs: CertificationAnalysis, achievements: AchievementAnalysis,
                  github: GitHubAnalysis, evidence: EvidenceAnalysis) -> dict:
    return {
        "candidate_id_note": "identity fields intentionally omitted",
        "degree": profile.degree, "major": profile.major, "graduation_year": profile.graduation_year, "gpa": profile.gpa or "Not Provided",
        "coursework": profile.all_coursework()[:15],
        "scores": {c.label: {"score": c.display, "explanation": c.explanation[:300]} for c in scorecard.components},
        "overall": {"score": scorecard.overall_score, "classification": scorecard.classification,
                    "recommendation": scorecard.recommendation, "evidence_confidence": scorecard.evidence_confidence},
        "education": {"degree_relevance": education.degree_relevance, "academic_strength": education.academic_strength,
                      "highlights": education.highlights[:4], "concerns": education.concerns[:3]},
        "skills": {"strengths": skills.strengths[:5], "gaps": skills.gaps[:5],
                   "coverage": [{"skill": m.jd_skill, "status": m.status, "by": m.matched_by} for m in evidence.jd_skill_matrix[:15]]},
        "projects": [{"name": a.name, "depth": a.depth, "relevance": a.jd_relevance, "ownership": a.ownership,
                      "evidence": a.implementation_evidence, "highlights": a.technical_highlights[:3],
                      "technologies": next((p.technologies for p in profile.projects if p.name == a.name), [])}
                     for a in projects.assessments[:6]],
        "project_progression": projects.progression,
        "certifications": [{"name": a.name, "type": a.cert_type, "relevance": a.jd_relevance,
                            "verification": next((v.status for v in evidence.certification_verifications if v.name == a.name), "")}
                           for a in certs.assessments[:6]],
        "achievements": [{"title": a.title, "category": a.category, "significance": a.significance, "result": a.rank_or_result}
                         for a in achievements.assessments[:6]],
        "github": {"status": github.status, "score": github.github_score, "repos_inspected": github.analyzed_repos,
                   "technology_evidence": github.technology_evidence[:10], "languages": github.languages[:8],
                   "active_last_6_months": github.active_last_6_months,
                   "top_repos": [{"name": r.name, "relevance": r.relevance, "tests": r.has_tests, "ci": r.has_ci,
                                  "commits": r.commit_count} for r in github.relevant_repos[:4]]},
        "evidence": {"technical_evidence_confidence": evidence.technical_evidence_confidence,
                     "notes": evidence.notes[:5],
                     "links": [{"url": l.url, "status": l.status} for l in evidence.project_link_checks[:6]]},
        "internships": [{"role": i.role, "company": i.company, "technologies": i.technologies} for i in profile.internships[:4]],
    }


def fallback_evaluation(profile: CandidateProfile, scorecard: ScoreCard, projects: ProjectAnalysis,
                        skills: SkillsAnalysis, evidence: EvidenceAnalysis) -> CandidateEvaluation:
    best = sorted(scorecard.components, key=lambda c: -(c.score or 0))
    scored = [c for c in best if c.score is not None]
    strengths = [f"{c.label}: {c.explanation.split('.')[0]}" for c in scored[:4]]
    concerns = [f"{c.label}: {c.explanation.split('.')[0]}" for c in reversed(scored[-2:])]
    questions: list[str] = []
    for a in projects.assessments[:3]:
        questions.append(f"Walk me through the architecture of '{a.name}' and the hardest technical decision you made.")
        questions.append(f"How did you test and deploy '{a.name}', and what would you change if you rebuilt it?")
    for gap in skills.gaps[:2]:
        questions.append(f"The role uses {gap}. What related technology have you used, and how would you ramp up?")
    return CandidateEvaluation(
        top_strength=strengths[0] if strengths else "See component scores",
        primary_concern=concerns[0] if concerns else "Verify project ownership in interview",
        strengths=strengths,
        concerns=concerns,
        evidence_summary=evidence.explanation,
        why_interview=f"{scorecard.classification} with {scorecard.evidence_confidence.lower()} evidence confidence.",
        technical_areas_to_test=skills.gaps[:4],
        project_areas_to_discuss=[a.name for a in projects.assessments[:4]],
        interview_questions=questions[:8],
    )


def run(state: CandidateState) -> dict:
    profile = CandidateProfile.model_validate(state["profile"])
    jd = JobProfile.model_validate(state["jd_profile"])
    scorecard = ScoreCard.model_validate(state.get("scorecard") or {})
    education = EducationAnalysis.model_validate(state.get("education_analysis") or {})
    skills = SkillsAnalysis.model_validate(state.get("skills_analysis") or {})
    projects = ProjectAnalysis.model_validate(state.get("project_analysis") or {})
    certs = CertificationAnalysis.model_validate(state.get("certification_analysis") or {})
    achievements = AchievementAnalysis.model_validate(state.get("achievement_analysis") or {})
    github = GitHubAnalysis.model_validate(state.get("github_analysis") or {})
    evidence = EvidenceAnalysis.model_validate(state.get("evidence_analysis") or {})

    summary = build_summary(profile, scorecard, education, skills, projects, certs, achievements, github, evidence)
    try:
        evaluation = llm.generate_structured(evaluator_prompt(jd, profile, summary), CandidateEvaluation, system=SYSTEM_PROMPT)
        warnings: list[str] = []
        if not evaluation.interview_questions:
            evaluation.interview_questions = fallback_evaluation(profile, scorecard, projects, skills, evidence).interview_questions
    except llm.LLMError as exc:
        evaluation = fallback_evaluation(profile, scorecard, projects, skills, evidence)
        warnings = [f"Narrative evaluation used a deterministic fallback ({str(exc)[:80]})"]
    return {"evaluation": evaluation.model_dump(), "warnings": warnings}
