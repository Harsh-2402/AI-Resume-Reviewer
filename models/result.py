from typing import Literal

from pydantic import BaseModel, Field

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
from models.scoring import ScoreCard

CandidateStatus = Literal[
    "Queued", "Processing", "Completed", "Completed with Warnings", "Failed", "Duplicate",
]

STAGES: list[str] = [
    "parser", "extractor", "education", "skills", "projects",
    "certifications", "achievements", "github", "evidence", "scoring", "evaluator",
]

STAGE_LABELS: dict[str, str] = {
    "parser": "Resume Parser",
    "extractor": "Information Extractor",
    "education": "Education Analyzer",
    "skills": "Skills Analyzer",
    "projects": "Project Analyzer",
    "certifications": "Certification Analyzer",
    "achievements": "Achievement Analyzer",
    "github": "GitHub Analyzer",
    "evidence": "Evidence Validator",
    "scoring": "Internship Scorer",
    "evaluator": "Candidate Evaluator",
}


class CandidateResult(BaseModel):
    candidate_id: str
    resume_file: str = ""
    status: CandidateStatus = "Queued"
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    stage_status: dict[str, str] = Field(default_factory=dict)
    processing_time: float = 0.0
    duplicate_of: str = ""

    raw_text: str = ""
    profile: CandidateProfile = Field(default_factory=CandidateProfile)
    education_analysis: EducationAnalysis = Field(default_factory=EducationAnalysis)
    skills_analysis: SkillsAnalysis = Field(default_factory=SkillsAnalysis)
    project_analysis: ProjectAnalysis = Field(default_factory=ProjectAnalysis)
    certification_analysis: CertificationAnalysis = Field(default_factory=CertificationAnalysis)
    achievement_analysis: AchievementAnalysis = Field(default_factory=AchievementAnalysis)
    github_analysis: GitHubAnalysis = Field(default_factory=GitHubAnalysis)
    evidence_analysis: EvidenceAnalysis = Field(default_factory=EvidenceAnalysis)
    scorecard: ScoreCard = Field(default_factory=ScoreCard)
    evaluation: CandidateEvaluation = Field(default_factory=CandidateEvaluation)

    rank: int | None = None
    interview_priority: int | None = None

    @property
    def name(self) -> str:
        return self.profile.candidate_name or "Unknown"

    @property
    def overall_score(self) -> float:
        return self.scorecard.overall_score

    @property
    def is_ranked(self) -> bool:
        return self.status in ("Completed", "Completed with Warnings")
