from agents.prompts import SYSTEM_PROMPT, skills_prompt
from models.analysis import JDSkillCoverage, SkillsAnalysis
from models.candidate import CandidateProfile
from models.jd import JobProfile
from models.state import CandidateState
from scoring.transferable import build_skill_matrix
from services import llm_service as llm
from utils.text import dedupe_preserve


def candidate_skill_pool(profile: CandidateProfile) -> list[str]:
    pool = profile.technical_skills.all_skills()
    for project in profile.projects:
        pool += project.technologies
    for internship in profile.internships + profile.work_experience:
        pool += internship.technologies
    for cert in profile.certifications:
        if cert.technology:
            pool.append(cert.technology)
    return dedupe_preserve(pool)


def run(state: CandidateState) -> dict:
    jd = JobProfile.model_validate(state["jd_profile"])
    profile = CandidateProfile.model_validate(state["profile"])
    pool = candidate_skill_pool(profile)
    prematch = build_skill_matrix(jd.core_skills(), pool + profile.all_coursework())

    if not pool:
        analysis = SkillsAnalysis(
            jd_coverage=[JDSkillCoverage(jd_skill=s, status="Missing") for s in jd.core_skills()],
            explanation="No technical skills could be identified in the resume.",
            confidence="Low",
        )
        return {"skills_analysis": analysis.model_dump(), "warnings": ["No technical skills identified"]}

    analysis = llm.generate_structured(skills_prompt(jd, profile, prematch), SkillsAnalysis, system=SYSTEM_PROMPT)

    covered = {c.jd_skill.strip().lower() for c in analysis.jd_coverage}
    for skill, status, by in prematch:
        if skill.strip().lower() not in covered:
            analysis.jd_coverage.append(
                JDSkillCoverage(jd_skill=skill, status=status, covered_by=by, note="deterministic match")
            )
    return {"skills_analysis": analysis.model_dump()}
