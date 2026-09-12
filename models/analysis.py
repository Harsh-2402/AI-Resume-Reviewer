"""LLM analysis outputs. The LLM classifies; Python (scoring/) converts to numbers."""
from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["High", "Medium", "Low", "N/A"]
Relevance = Literal["Direct", "Strongly Related", "Transferable", "Not Relevant"]
MatchStatus = Literal["Direct Match", "Strongly Related", "Transferable", "Missing"]
ProjectDepth = Literal["Basic", "Beginner", "Intermediate", "Advanced", "Highly Advanced"]
EvidenceLevel = Literal["Strong", "Moderate", "Weak", "None"]
CertType = Literal[
    "Professional Certification",
    "Industry Certification",
    "Course Certificate",
    "Training Certificate",
    "Workshop Certificate",
]


# ─── Education & coursework ──────────────────────────────────────────────────
class CourseworkMatch(BaseModel):
    course: str = ""
    relevance: Literal["Direct", "Related", "Not Relevant"] = "Not Relevant"
    note: str = ""


class EducationAnalysis(BaseModel):
    degree_relevance: Literal["Direct", "Related", "Transferable", "Unrelated", "Unknown"] = "Unknown"
    academic_strength: Literal["Exceptional", "Strong", "Adequate", "Limited", "Unknown"] = "Unknown"
    gpa_assessment: str = ""
    coursework_matches: list[CourseworkMatch] = Field(default_factory=list)
    academic_projects: list[str] = Field(default_factory=list)
    academic_achievements: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    explanation: str = ""
    confidence: Confidence = "Medium"


# ─── Skills ──────────────────────────────────────────────────────────────────
class SkillAssessment(BaseModel):
    skill: str = ""
    category: str = ""
    jd_match: Relevance = "Not Relevant"
    depth: Literal["Demonstrated", "Claimed"] = "Claimed"
    evidence: str = ""


class JDSkillCoverage(BaseModel):
    jd_skill: str = ""
    status: MatchStatus = "Missing"
    covered_by: str = ""
    note: str = ""


class SkillsAnalysis(BaseModel):
    assessments: list[SkillAssessment] = Field(default_factory=list)
    jd_coverage: list[JDSkillCoverage] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    explanation: str = ""
    confidence: Confidence = "Medium"


# ─── Projects ────────────────────────────────────────────────────────────────
class ProjectAssessment(BaseModel):
    name: str = ""
    depth: ProjectDepth = "Basic"
    complexity: int = Field(default=1, ge=1, le=5)
    jd_relevance: Relevance = "Not Relevant"
    ownership: Literal["Strong", "Moderate", "Weak", "Unknown"] = "Unknown"
    implementation_evidence: EvidenceLevel = "Weak"
    technical_highlights: list[str] = Field(default_factory=list)
    comments: str = ""


class ProjectAnalysis(BaseModel):
    assessments: list[ProjectAssessment] = Field(default_factory=list)
    progression: Literal["Clear Growth", "Some Growth", "Flat", "Unknown"] = "Unknown"
    overall_assessment: str = ""
    explanation: str = ""
    confidence: Confidence = "Medium"


# ─── Certifications ──────────────────────────────────────────────────────────
class CertificationAssessment(BaseModel):
    name: str = ""
    issuer: str = ""
    cert_type: CertType = "Course Certificate"
    technology: str = ""
    jd_relevance: Literal["High", "Medium", "Low", "None"] = "Low"
    comments: str = ""


class CertificationAnalysis(BaseModel):
    assessments: list[CertificationAssessment] = Field(default_factory=list)
    explanation: str = ""
    confidence: Confidence = "Medium"


# ─── Achievements / hackathons ───────────────────────────────────────────────
class AchievementAssessment(BaseModel):
    title: str = ""
    category: Literal[
        "Academic", "Competition", "Hackathon", "Research",
        "Leadership", "Open Source", "Scholarship", "Other",
    ] = "Other"
    rank_or_result: str = ""
    organization: str = ""
    date: str = ""
    significance: Literal["Exceptional", "Strong", "Moderate", "Minor"] = "Moderate"
    relevance: Literal["High", "Medium", "Low"] = "Medium"
    evidence: str = ""
    comments: str = ""


class AchievementAnalysis(BaseModel):
    assessments: list[AchievementAssessment] = Field(default_factory=list)
    learning_signals: list[str] = Field(default_factory=list)
    explanation: str = ""
    confidence: Confidence = "Medium"


# ─── Evidence validation (deterministic) ─────────────────────────────────────
class SkillEvidence(BaseModel):
    skill: str = ""
    claimed: bool = True
    github_evidence: bool = False
    project_evidence: bool = False
    confidence: Confidence = "Low"
    note: str = ""


class LinkCheck(BaseModel):
    url: str = ""
    kind: str = ""
    status: Literal["accessible", "inaccessible", "broken", "unknown"] = "unknown"
    detail: str = ""


class CertificationVerification(BaseModel):
    name: str = ""
    credential_url: str = ""
    status: Literal["Verified", "Evidence Found", "Not Verifiable", "No Verification Information"] = (
        "No Verification Information"
    )
    detail: str = ""


class TransferableMatch(BaseModel):
    jd_skill: str = ""
    status: MatchStatus = "Missing"
    matched_by: str = ""


class EvidenceAnalysis(BaseModel):
    skill_evidence: list[SkillEvidence] = Field(default_factory=list)
    technical_evidence_confidence: Confidence = "Low"
    project_link_checks: list[LinkCheck] = Field(default_factory=list)
    certification_verifications: list[CertificationVerification] = Field(default_factory=list)
    jd_skill_matrix: list[TransferableMatch] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    explanation: str = ""


# ─── Final narrative evaluation (LLM) ────────────────────────────────────────
class CandidateEvaluation(BaseModel):
    top_strength: str = ""
    primary_concern: str = ""
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    evidence_summary: str = ""
    why_interview: str = ""
    technical_areas_to_test: list[str] = Field(default_factory=list)
    project_areas_to_discuss: list[str] = Field(default_factory=list)
    github_areas_to_discuss: list[str] = Field(default_factory=list)
    certification_areas_to_discuss: list[str] = Field(default_factory=list)
    interview_questions: list[str] = Field(default_factory=list)
