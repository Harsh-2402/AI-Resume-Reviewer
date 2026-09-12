from agents.prompts import SYSTEM_PROMPT, education_prompt
from models.analysis import CourseworkMatch, EducationAnalysis
from models.candidate import CandidateProfile
from models.jd import JobProfile
from models.state import CandidateState
from services import llm_service as llm


def run(state: CandidateState) -> dict:
    jd = JobProfile.model_validate(state["jd_profile"])
    profile = CandidateProfile.model_validate(state["profile"])
    if not profile.education and not profile.all_coursework():
        analysis = EducationAnalysis(
            explanation="No education information was found in the resume.", confidence="N/A",
        )
        return {"education_analysis": analysis.model_dump(), "warnings": ["No education information found"]}

    analysis = llm.generate_structured(education_prompt(jd, profile), EducationAnalysis, system=SYSTEM_PROMPT)

    listed = {c.lower() for c in profile.all_coursework()}
    assessed = {m.course.lower() for m in analysis.coursework_matches}
    for course in profile.all_coursework():
        if course.lower() not in assessed and course.lower() in listed:
            analysis.coursework_matches.append(CourseworkMatch(course=course, note="not assessed"))
    return {"education_analysis": analysis.model_dump()}
