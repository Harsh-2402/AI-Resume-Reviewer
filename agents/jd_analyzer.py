from agents.prompts import SYSTEM_PROMPT, jd_prompt
from models.jd import JobProfile
from services import llm_service as llm
from utils.text import truncate


def analyze_jd(jd_text: str) -> JobProfile:
    profile = llm.generate_structured(jd_prompt(truncate(jd_text, 15000)), JobProfile, system=SYSTEM_PROMPT)
    if not profile.required_skills and profile.all_technologies():
        profile.required_skills = profile.all_technologies()[:12]
    return profile
