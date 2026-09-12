"""Per-candidate LangGraph: parser → extractor → 6 parallel analyzers → evidence → scoring → evaluator."""
import time
from typing import Callable

from langgraph.graph import END, START, StateGraph

from agents import (
    achievement_analyzer,
    candidate_evaluator,
    certification_analyzer,
    education_analyzer,
    evidence_validator,
    github_analyzer,
    information_extractor,
    internship_scorer,
    project_analyzer,
    resume_parser,
    skills_analyzer,
)
from models.result import STAGE_LABELS, STAGES, CandidateResult
from models.state import CandidateInput, CandidateState
from workflow.events import emit

ANALYZERS = ["education", "skills", "projects", "certifications", "achievements", "github"]

_AGENTS: dict[str, Callable[[CandidateState], dict]] = {
    "parser": resume_parser.run,
    "extractor": information_extractor.run,
    "education": education_analyzer.run,
    "skills": skills_analyzer.run,
    "projects": project_analyzer.run,
    "certifications": certification_analyzer.run,
    "achievements": achievement_analyzer.run,
    "github": github_analyzer.run,
    "evidence": evidence_validator.run,
    "scoring": internship_scorer.run,
    "evaluator": candidate_evaluator.run,
}
_CRITICAL = {"parser", "extractor"}


def _wrap(stage: str, fn: Callable[[CandidateState], dict]) -> Callable[[CandidateState], dict]:
    label = STAGE_LABELS[stage]

    def node(state: CandidateState) -> dict:
        cid = state["candidate_id"]
        emit(cid, stage, "started", f"{label} started")
        t0 = time.perf_counter()
        try:
            out = fn(state) or {}
        except Exception as exc:  # noqa: BLE001 — any agent failure must not kill the candidate/batch
            elapsed = round(time.perf_counter() - t0, 2)
            msg = f"{label} failed: {str(exc)[:160]}"
            if stage in _CRITICAL:
                emit(cid, stage, "failed", msg)
                return {"failed": True, "errors": [msg], "stage_status": {stage: "failed"}, "timings": {stage: elapsed}}
            emit(cid, stage, "warning", msg)
            return {"warnings": [msg], "stage_status": {stage: "warning"}, "timings": {stage: elapsed}}
        elapsed = round(time.perf_counter() - t0, 2)
        warnings = list(out.get("warnings") or [])
        for w in warnings:
            emit(cid, stage, "warning", w)
        emit(cid, stage, "completed", f"{label} completed", elapsed=elapsed)
        return {**out, "warnings": warnings, "stage_status": {stage: "warning" if warnings else "completed"}, "timings": {stage: elapsed}}

    return node


def _after_parser(state: CandidateState) -> str:
    return END if state.get("failed") else "extractor"


def _after_extractor(state: CandidateState):
    return END if state.get("failed") else ANALYZERS


def build_candidate_graph():
    g = StateGraph(CandidateState)
    for stage in STAGES:
        g.add_node(stage, _wrap(stage, _AGENTS[stage]))
    g.add_edge(START, "parser")
    g.add_conditional_edges("parser", _after_parser, [END, "extractor"])
    g.add_conditional_edges("extractor", _after_extractor, [END, *ANALYZERS])
    g.add_edge(ANALYZERS, "evidence")
    g.add_edge("evidence", "scoring")
    g.add_edge("scoring", "evaluator")
    g.add_edge("evaluator", END)
    return g.compile()


candidate_graph = build_candidate_graph()


def initial_state(inp: CandidateInput) -> CandidateState:
    return {**inp, "failed": False, "warnings": [], "errors": [], "stage_status": {}, "timings": {}}


def to_result(final: CandidateState, elapsed: float) -> CandidateResult:
    stage_status = dict(final.get("stage_status") or {})
    failed = bool(final.get("failed"))
    for stage in STAGES:
        stage_status.setdefault(stage, "skipped" if failed else "not run")
    warnings = list(final.get("warnings") or [])
    errors = list(final.get("errors") or [])
    status = "Failed" if failed else ("Completed with Warnings" if warnings else "Completed")
    return CandidateResult(
        candidate_id=final["candidate_id"],
        resume_file=final.get("resume_file", ""),
        status=status,
        warnings=warnings,
        errors=errors,
        stage_status=stage_status,
        processing_time=round(elapsed, 2),
        raw_text=final.get("raw_text", ""),
        profile=final.get("profile") or {},
        education_analysis=final.get("education_analysis") or {},
        skills_analysis=final.get("skills_analysis") or {},
        project_analysis=final.get("project_analysis") or {},
        certification_analysis=final.get("certification_analysis") or {},
        achievement_analysis=final.get("achievement_analysis") or {},
        github_analysis=final.get("github_analysis") or {},
        evidence_analysis=final.get("evidence_analysis") or {},
        scorecard=final.get("scorecard") or {},
        evaluation=final.get("evaluation") or {},
    )


def run_candidate(inp: CandidateInput, config: dict | None = None) -> CandidateResult:
    t0 = time.perf_counter()
    final = candidate_graph.invoke(initial_state(inp), config)
    return to_result(final, time.perf_counter() - t0)
