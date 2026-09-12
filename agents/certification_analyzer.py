from agents.prompts import SYSTEM_PROMPT, certifications_prompt
from models.analysis import CertificationAnalysis, CertificationAssessment
from models.candidate import CandidateProfile
from models.jd import JobProfile
from models.state import CandidateState
from services import llm_service as llm


def run(state: CandidateState) -> dict:
    jd = JobProfile.model_validate(state["jd_profile"])
    profile = CandidateProfile.model_validate(state["profile"])
    if not profile.certifications:
        analysis = CertificationAnalysis(explanation="No certifications listed.", confidence="N/A")
        return {"certification_analysis": analysis.model_dump()}

    analysis = llm.generate_structured(
        certifications_prompt(jd, profile), CertificationAnalysis, system=SYSTEM_PROMPT,
    )
    assessed = {a.name.strip().lower() for a in analysis.assessments}
    for cert in profile.certifications:
        if cert.name and cert.name.strip().lower() not in assessed:
            analysis.assessments.append(
                CertificationAssessment(name=cert.name, issuer=cert.issuer, technology=cert.technology)
            )
    return {"certification_analysis": analysis.model_dump()}
