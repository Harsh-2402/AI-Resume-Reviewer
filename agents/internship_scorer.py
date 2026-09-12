from models.analysis import (
    AchievementAnalysis,
    CertificationAnalysis,
    EducationAnalysis,
    EvidenceAnalysis,
    ProjectAnalysis,
    SkillsAnalysis,
)
from models.candidate import CandidateProfile
from models.github import GitHubAnalysis
from models.jd import JobProfile
from models.state import CandidateState
from scoring.internship_scorer import score_candidate


def run(state: CandidateState) -> dict:
    scorecard = score_candidate(
        profile=CandidateProfile.model_validate(state["profile"]),
        jd=JobProfile.model_validate(state["jd_profile"]),
        education=EducationAnalysis.model_validate(state.get("education_analysis") or {}),
        skills=SkillsAnalysis.model_validate(state.get("skills_analysis") or {}),
        projects=ProjectAnalysis.model_validate(state.get("project_analysis") or {}),
        certifications=CertificationAnalysis.model_validate(state.get("certification_analysis") or {}),
        achievements=AchievementAnalysis.model_validate(state.get("achievement_analysis") or {}),
        github=GitHubAnalysis.model_validate(state.get("github_analysis") or {}),
        evidence=EvidenceAnalysis.model_validate(state.get("evidence_analysis") or {}),
        weights=(state.get("settings") or {}).get("weights"),
    )
    return {"scorecard": scorecard.model_dump()}
