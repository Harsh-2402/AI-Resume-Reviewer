from agents.prompts import SYSTEM_PROMPT, projects_prompt
from models.analysis import ProjectAnalysis, ProjectAssessment
from models.candidate import CandidateProfile
from models.jd import JobProfile
from models.state import CandidateState
from services import llm_service as llm


def run(state: CandidateState) -> dict:
    jd = JobProfile.model_validate(state["jd_profile"])
    profile = CandidateProfile.model_validate(state["profile"])
    if not profile.projects and not profile.internships and not profile.all_hackathons():
        analysis = ProjectAnalysis(
            overall_assessment="No projects, internships or hackathon work were found.",
            explanation="No project evidence available.",
            confidence="N/A",
        )
        return {"project_analysis": analysis.model_dump()}

    analysis = llm.generate_structured(projects_prompt(jd, profile), ProjectAnalysis, system=SYSTEM_PROMPT)

    assessed = {a.name.strip().lower() for a in analysis.assessments}
    for project in profile.projects:
        if project.name and project.name.strip().lower() not in assessed:
            analysis.assessments.append(
                ProjectAssessment(name=project.name, comments="Not assessed by the model; scored conservatively.")
            )
    return {"project_analysis": analysis.model_dump()}
