"""LangGraph state definitions. Parallel candidate-graph nodes write disjoint keys;
the list/dict keys below carry reducers so concurrent writes accumulate."""
import operator
from typing import Annotated, TypedDict


def merge_dicts(left: dict | None, right: dict | None) -> dict:
    return {**(left or {}), **(right or {})}


class CandidateState(TypedDict, total=False):
    candidate_id: str
    resume_file: str
    file_path: str
    jd_profile: dict
    settings: dict

    raw_text: str
    profile: dict
    education_analysis: dict
    skills_analysis: dict
    project_analysis: dict
    certification_analysis: dict
    achievement_analysis: dict
    github_analysis: dict
    evidence_analysis: dict
    scorecard: dict
    evaluation: dict

    failed: bool
    warnings: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]
    stage_status: Annotated[dict[str, str], merge_dicts]
    timings: Annotated[dict[str, float], merge_dicts]


class CandidateInput(TypedDict):
    candidate_id: str
    resume_file: str
    file_path: str
    jd_profile: dict
    settings: dict


class BatchState(TypedDict, total=False):
    jd_text: str
    jd_profile: dict
    settings: dict
    candidate_inputs: list[dict]
    candidates: Annotated[list[dict], operator.add]
    ranking: list[dict]
    report_bytes: bytes
    report_filename: str
    stats: dict
