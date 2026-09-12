from agents.prompts import SYSTEM_PROMPT, achievements_prompt
from models.analysis import AchievementAnalysis
from models.candidate import CandidateProfile
from models.jd import JobProfile
from models.state import CandidateState
from services import llm_service as llm


def has_achievement_data(profile: CandidateProfile) -> bool:
    return bool(
        profile.achievements or profile.hackathons or profile.competitions or profile.awards
        or profile.publications or profile.open_source or any(e.honors for e in profile.education)
    )


def run(state: CandidateState) -> dict:
    jd = JobProfile.model_validate(state["jd_profile"])
    profile = CandidateProfile.model_validate(state["profile"])
    if not has_achievement_data(profile):
        analysis = AchievementAnalysis(explanation="No achievements, hackathons or awards listed.", confidence="N/A")
        return {"achievement_analysis": analysis.model_dump()}

    analysis = llm.generate_structured(achievements_prompt(jd, profile), AchievementAnalysis, system=SYSTEM_PROMPT)
    return {"achievement_analysis": analysis.model_dump()}
