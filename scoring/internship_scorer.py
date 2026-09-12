"""Deterministic internship scoring. Inputs are LLM classifications + evidence; outputs are explained numbers.

Missing areas (no GitHub, no certifications, ...) score None and are excluded by renormalizing the
remaining weights, so absence is neutral rather than a penalty (spec §25, §77).
"""
from models.analysis import (
    AchievementAnalysis,
    CertificationAnalysis,
    EducationAnalysis,
    EvidenceAnalysis,
    ProjectAnalysis,
    SkillsAnalysis,
    TransferableMatch,
)
from models.candidate import CandidateProfile
from models.github import GitHubAnalysis
from models.jd import JobProfile
from models.scoring import ComponentScore, ScoreCard
from scoring.weights import classify, default_weights, recommend
from utils.text import gpa_on_4_scale

import config

_DEGREE_BASE = {"Direct": 85, "Related": 72, "Transferable": 60, "Unrelated": 45, "Unknown": 60}
_STRENGTH_ADJ = {"Exceptional": 12, "Strong": 7, "Adequate": 0, "Limited": -8, "Unknown": 0}
_DEPTH_BASE = {"Basic": 30, "Beginner": 42, "Intermediate": 60, "Advanced": 80, "Highly Advanced": 95}
_REL_MULT = {"Direct": 1.0, "Strongly Related": 0.92, "Transferable": 0.8, "Not Relevant": 0.6}
_OWN_ADJ = {"Strong": 4, "Moderate": 0, "Weak": -4, "Unknown": 0}
_IMPL_ADJ = {"Strong": 8, "Moderate": 4, "Weak": 0, "None": -4}
_COV_WEIGHT = {"Direct Match": 1.0, "Strongly Related": 0.75, "Transferable": 0.5, "Missing": 0.0}
_CERT_BASE = {"Professional Certification": 90, "Industry Certification": 80, "Course Certificate": 55,
              "Training Certificate": 45, "Workshop Certificate": 35}
_CERT_REL = {"High": 1.0, "Medium": 0.75, "Low": 0.5, "None": 0.3}
_VERIFY_BONUS = {"Verified": 6, "Evidence Found": 3, "Not Verifiable": 0, "No Verification Information": 0}
_ACH_BASE = {"Exceptional": 95, "Strong": 80, "Moderate": 60, "Minor": 40}
_ACH_REL = {"High": 1.0, "Medium": 0.85, "Low": 0.65}
_PROJ_REL_SCORE = {"Direct": 100, "Strongly Related": 85, "Transferable": 65, "Not Relevant": 30}
_DEGREE_REL_SCORE = {"Direct": 100, "Related": 80, "Transferable": 60, "Unrelated": 35, "Unknown": 60}


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)


def _component(key: str, score: float | None, explanation: str, confidence: str) -> ComponentScore:
    return ComponentScore(key=key, label=config.COMPONENT_LABELS[key], score=None if score is None else _clamp(score),
                          explanation=explanation, confidence=confidence)


# ─── Components ──────────────────────────────────────────────────────────────
def education_score(profile: CandidateProfile, edu: EducationAnalysis) -> ComponentScore:
    if not profile.education and edu.confidence == "N/A":
        return _component("education", None, "No education information found (N/A — excluded from the weighted score).", "N/A")
    base = _DEGREE_BASE.get(edu.degree_relevance, 60)
    parts = [f"degree relevance {edu.degree_relevance} ({base})"]
    adj = _STRENGTH_ADJ.get(edu.academic_strength, 0)
    if adj:
        parts.append(f"academic strength {edu.academic_strength} ({adj:+d})")
    score = base + adj
    gpa = gpa_on_4_scale(profile.gpa)
    if gpa is not None:
        bonus = 5 if gpa >= 3.7 else 3 if gpa >= 3.3 else -3 if gpa < 2.5 else 0
        score += bonus
        parts.append(f"GPA {profile.gpa} ({bonus:+d})")
    else:
        parts.append("GPA not provided (neutral)")
    honors = len(edu.academic_achievements) + sum(len(e.honors) for e in profile.education)
    if honors:
        b = min(honors * 2, 6)
        score += b
        parts.append(f"{honors} academic honors/achievements (+{b})")
    return _component("education", score, "; ".join(parts) + ". " + edu.explanation, edu.confidence)


def coursework_score(profile: CandidateProfile, edu: EducationAnalysis) -> ComponentScore:
    courses = profile.all_coursework()
    if not courses and not edu.coursework_matches:
        return _component("coursework", None, "No coursework listed (N/A — excluded from the weighted score).", "N/A")
    direct = sum(1 for m in edu.coursework_matches if m.relevance == "Direct")
    related = sum(1 for m in edu.coursework_matches if m.relevance == "Related")
    if direct + related == 0:
        score = 30.0
    else:
        score = 35 + 12 * direct + 6 * related
    conf = edu.confidence if edu.confidence != "N/A" else "Medium"
    names = [m.course for m in edu.coursework_matches if m.relevance == "Direct"][:5]
    expl = f"{direct} directly relevant and {related} related courses out of {max(len(courses), len(edu.coursework_matches))}"
    if names:
        expl += f" (e.g. {', '.join(names)})"
    return _component("coursework", score, expl + ".", conf)


def technical_skills_score(skills: SkillsAnalysis, profile: CandidateProfile) -> ComponentScore:
    if not profile.technical_skills.all_skills() and not skills.assessments:
        return _component("technical_skills", 10, "No technical skills identified in the resume.", "Low")
    if skills.jd_coverage:
        cov = sum(_COV_WEIGHT.get(c.status, 0) for c in skills.jd_coverage) / len(skills.jd_coverage)
    else:
        cov = 0.7
    relevant = [a for a in skills.assessments if a.jd_match != "Not Relevant"]
    demonstrated = [a for a in relevant if a.depth == "Demonstrated"]
    depth = (len(demonstrated) / len(relevant)) if relevant else 0.5
    score = 100 * (0.65 * cov + 0.35 * depth)
    bonus = 5 if len(demonstrated) >= 5 else 0
    score += bonus
    direct = sum(1 for c in skills.jd_coverage if c.status == "Direct Match")
    missing = [c.jd_skill for c in skills.jd_coverage if c.status == "Missing"]
    expl = (f"JD coverage {cov * 100:.0f}% ({direct}/{len(skills.jd_coverage)} direct matches); "
            f"{len(demonstrated)}/{len(relevant)} relevant skills demonstrated in projects/internships")
    if bonus:
        expl += f"; breadth bonus +{bonus}"
    if missing:
        expl += f". Missing: {', '.join(missing[:6])}"
    return _component("technical_skills", score, expl + ". " + skills.explanation, skills.confidence)


def project_score(projects: ProjectAnalysis) -> ComponentScore:
    if not projects.assessments:
        return _component("projects", 15, "No projects found — this is the primary internship signal, so the score is low.", "Low")
    scored: list[tuple[float, str]] = []
    for a in projects.assessments:
        s = _DEPTH_BASE.get(a.depth, 30) * _REL_MULT.get(a.jd_relevance, 0.6)
        s += _OWN_ADJ.get(a.ownership, 0) + _IMPL_ADJ.get(a.implementation_evidence, 0)
        scored.append((_clamp(s), a.name))
    scored.sort(reverse=True)
    top = [s for s, _ in scored[:3]]
    weights = {1: [1.0], 2: [0.6, 0.4], 3: [0.5, 0.3, 0.2]}[len(top)]
    score = sum(s * w for s, w in zip(top, weights))
    extra = min(max(len(scored) - 3, 0) * 2, 6)
    growth = {"Clear Growth": 4, "Some Growth": 2}.get(projects.progression, 0)
    score += extra + growth
    expl = (f"{len(scored)} projects; strongest: " + ", ".join(f"{n} ({s:.0f})" for s, n in scored[:3])
            + f"; depth-weighted (50/30/20)" + (f"; breadth +{extra}" if extra else "")
            + (f"; progression {projects.progression} +{growth}" if growth else "") + ". " + projects.explanation)
    return _component("projects", score, expl, projects.confidence)


def github_score(github: GitHubAnalysis) -> ComponentScore:
    if github.status == "analyzed" and github.github_score is not None:
        bd = github.breakdown
        expl = (f"quality {bd.repository_quality:.0f}, activity {bd.meaningful_activity:.0f}, relevance {bd.technology_relevance:.0f}, "
                f"complexity {bd.project_complexity:.0f}, docs {bd.documentation:.0f}, tests/CI {bd.testing_ci:.0f}, recency {bd.recent_activity:.0f}. "
                + github.explanation)
        return _component("github", github.github_score, expl, github.confidence)
    reason = {
        "not_provided": "No GitHub profile provided",
        "not_found": "GitHub profile not found",
        "rate_limited": "GitHub rate limit reached",
        "error": "GitHub lookup failed",
        "no_public_repos": "No original public repositories",
    }.get(github.status, "GitHub unavailable")
    return _component("github", None, f"{reason} (N/A — excluded from the weighted score).", "N/A")


def certification_score(certs: CertificationAnalysis, evidence: EvidenceAnalysis) -> ComponentScore:
    if not certs.assessments:
        return _component("certifications", None, "No certifications listed (N/A — excluded from the weighted score).", "N/A")
    verify = {v.name.strip().lower(): v.status for v in evidence.certification_verifications}
    scored: list[tuple[float, str]] = []
    for a in certs.assessments:
        s = _CERT_BASE.get(a.cert_type, 55) * _CERT_REL.get(a.jd_relevance, 0.5)
        s += _VERIFY_BONUS.get(verify.get(a.name.strip().lower(), ""), 0)
        scored.append((_clamp(s), a.name))
    scored.sort(reverse=True)
    values = [s for s, _ in scored]
    score = 0.6 * values[0] + 0.4 * (sum(values) / len(values))
    relevant_extra = sum(1 for a in certs.assessments if a.jd_relevance in ("High", "Medium")) - 1
    bonus = min(max(relevant_extra, 0) * 3, 9)
    score += bonus
    verified = sum(1 for s in verify.values() if s in ("Verified", "Evidence Found"))
    expl = (f"{len(scored)} certifications; strongest: " + ", ".join(f"{n} ({s:.0f})" for s, n in scored[:3])
            + f"; {verified} with public evidence" + (f"; +{bonus} for additional relevant certifications" if bonus else "")
            + ". " + certs.explanation)
    return _component("certifications", score, expl, certs.confidence)


def achievement_score(ach: AchievementAnalysis) -> ComponentScore:
    if not ach.assessments:
        return _component("achievements", None, "No achievements, hackathons or awards listed (N/A — excluded from the weighted score).", "N/A")
    scored = sorted((_clamp(_ACH_BASE.get(a.significance, 60) * _ACH_REL.get(a.relevance, 0.85)), a.title) for a in ach.assessments)
    scored.reverse()
    values = [s for s, _ in scored]
    score = 0.6 * values[0] + 0.4 * (sum(values) / len(values)) + min(max(len(values) - 1, 0) * 3, 9)
    expl = (f"{len(scored)} achievements; strongest: " + ", ".join(f"{t} ({s:.0f})" for s, t in scored[:3])
            + ". " + ach.explanation)
    return _component("achievements", score, expl, ach.confidence)


def jd_alignment_score(jd: JobProfile, skills: SkillsAnalysis, projects: ProjectAnalysis, edu: EducationAnalysis,
                       evidence: EvidenceAnalysis) -> ComponentScore:
    matrix = evidence.jd_skill_matrix or [
        TransferableMatch(jd_skill=c.jd_skill, status=c.status, matched_by=c.covered_by) for c in skills.jd_coverage
    ]
    required = {s.strip().lower() for s in jd.required_skills}
    rows = [m for m in matrix if m.jd_skill.strip().lower() in required] or list(matrix)
    coverage = (sum(_COV_WEIGHT.get(m.status, 0) for m in rows) / len(rows) * 100) if rows else 60.0
    proj_rel = (sum(_PROJ_REL_SCORE.get(a.jd_relevance, 30) for a in projects.assessments) / len(projects.assessments)) if projects.assessments else 40.0
    degree_rel = _DEGREE_REL_SCORE.get(edu.degree_relevance, 60)
    cm = edu.coursework_matches
    course_rel = (sum(1 for m in cm if m.relevance in ("Direct", "Related")) / len(cm) * 100) if cm else 50.0
    score = 0.5 * coverage + 0.25 * proj_rel + 0.15 * degree_rel + 0.10 * course_rel
    missing = [m.jd_skill for m in rows if m.status == "Missing"]
    expl = (f"required-skill coverage {coverage:.0f}%, project relevance {proj_rel:.0f}, degree relevance {degree_rel:.0f}, "
            f"coursework relevance {course_rel:.0f}" + (f". Missing required: {', '.join(missing[:6])}" if missing else "") + ".")
    conf = "High" if skills.confidence == "High" and projects.confidence in ("High", "Medium") else "Medium"
    return _component("jd_alignment", score, expl, conf)


def learning_potential_score(profile: CandidateProfile, projects: ProjectAnalysis, ach: AchievementAnalysis,
                             github: GitHubAnalysis) -> ComponentScore:
    score = 40.0
    signals: list[str] = []
    growth = {"Clear Growth": 15, "Some Growth": 8}.get(projects.progression, 0)
    if growth:
        score += growth
        signals.append(f"project progression: {projects.progression}")
    categories = len(profile.technical_skills.category_map())
    if categories >= 6:
        score += 12
        signals.append(f"breadth across {categories} technology areas")
    elif categories >= 4:
        score += 8
        signals.append(f"breadth across {categories} technology areas")
    if profile.certifications:
        score += 6 + (3 if len(profile.certifications) >= 2 else 0)
        signals.append(f"{len(profile.certifications)} certification(s)")
    if profile.all_hackathons():
        score += 6
        signals.append("hackathon/competition participation")
    if profile.open_source or profile.publications:
        score += 6
        signals.append("open-source or research activity")
    if github.status == "analyzed" and github.active_last_6_months:
        score += 8
        signals.append("recent GitHub activity")
    if any(a.depth in ("Advanced", "Highly Advanced") for a in projects.assessments):
        score += 6
        signals.append("at least one advanced project")
    if ach.learning_signals:
        score += min(len(ach.learning_signals) * 2, 6)
        signals.extend(ach.learning_signals[:3])
    expl = "Observable learning signals: " + ("; ".join(signals) if signals else "none beyond baseline") + "."
    return _component("learning_potential", score, expl, "Medium" if signals else "Low")


# ─── Aggregate ───────────────────────────────────────────────────────────────
def _evidence_confidence(components: list[ComponentScore], evidence: EvidenceAnalysis) -> str:
    levels = {"High": 3, "Medium": 2, "Low": 1}
    vals = [levels[c.confidence] for c in components if c.confidence in levels]
    vals.append(levels.get(evidence.technical_evidence_confidence, 1) * 2)  # evidence counts double
    avg = sum(vals) / (len(vals) + 1) if vals else 1
    return "High" if avg >= 2.5 else "Medium" if avg >= 1.7 else "Low"


def score_candidate(
    *,
    profile: CandidateProfile,
    jd: JobProfile,
    education: EducationAnalysis,
    skills: SkillsAnalysis,
    projects: ProjectAnalysis,
    certifications: CertificationAnalysis,
    achievements: AchievementAnalysis,
    github: GitHubAnalysis,
    evidence: EvidenceAnalysis,
    weights: dict[str, float] | None = None,
) -> ScoreCard:
    weights = {**default_weights(), **(weights or {})}
    components = [
        education_score(profile, education),
        coursework_score(profile, education),
        technical_skills_score(skills, profile),
        project_score(projects),
        github_score(github),
        certification_score(certifications, evidence),
        achievement_score(achievements),
        jd_alignment_score(jd, skills, projects, education, evidence),
        learning_potential_score(profile, projects, achievements, github),
    ]
    for c in components:
        c.weight = float(weights.get(c.key, 0.0))
    available = [c for c in components if c.score is not None and c.weight > 0]
    total_weight = sum(c.weight for c in available)
    overall = 0.0
    for c in components:
        c.applied_weight = round(c.weight / total_weight, 4) if (c in available and total_weight > 0) else 0.0
        if c.score is not None:
            overall += c.score * c.applied_weight
    overall = round(overall, 1)
    classification = classify(overall)
    excluded = [c.label for c in components if c.score is None]
    explanation = (
        f"Weighted average of {len(available)} scored components"
        + (f" (excluded as N/A: {', '.join(excluded)}; weights renormalized)" if excluded else "")
        + f" → {overall:.1f} → {classification}."
    )
    return ScoreCard(
        components=components,
        overall_score=overall,
        classification=classification,
        recommendation=recommend(classification),
        evidence_confidence=_evidence_confidence(components, evidence),
        explanation=explanation,
    )
