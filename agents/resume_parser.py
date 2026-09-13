from models.state import CandidateState
from services.pdf_service import extract_resume_text


def run(state: CandidateState) -> dict:
    text, warnings = extract_resume_text(state["file_path"])
    return {"raw_text": text, "warnings": warnings}
