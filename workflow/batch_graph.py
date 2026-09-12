"""Batch LangGraph: JD analysis → Send fan-out per candidate → ranking → Excel report."""
import time
from typing import Any, Iterator

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

import config
from agents.jd_analyzer import analyze_jd
from models.jd import JobProfile
from models.result import STAGES, CandidateResult
from models.state import BatchState, CandidateInput
from reports.excel_report import build_excel_report, report_filename
from scoring.ranking import classification_counts, mark_identity_duplicates, rank_candidates
from services.cache_service import reset_all
from workflow.candidate_graph import run_candidate
from workflow.events import BATCH, ProgressEvent, emit, parse_event


def _duplicate_result(inp: dict) -> CandidateResult:
    return CandidateResult(
        candidate_id=inp["candidate_id"],
        resume_file=inp.get("resume_file", ""),
        status="Duplicate",
        duplicate_of=inp.get("duplicate_of", ""),
        warnings=[f"Duplicate resume detected (identical file to {inp.get('duplicate_of', '')}); not scored twice"],
        stage_status={s: "skipped" for s in STAGES},
    )


def analyze_jd_node(state: BatchState) -> dict:
    emit(BATCH, "jd", "started", "Analyzing job description")
    jd = analyze_jd(state["jd_text"])
    emit(BATCH, "jd", "completed", f"JD analyzed: {jd.job_title or 'role'} · {len(jd.core_skills())} skills",
         job_title=jd.job_title, skills=jd.core_skills())
    return {"jd_profile": jd.model_dump()}


def prepare_node(state: BatchState) -> dict:
    dups = [_duplicate_result(i).model_dump() for i in state.get("candidate_inputs", []) if i.get("duplicate_of")]
    for d in dups:
        emit(d["candidate_id"], "candidate", "duplicate", f"Duplicate of {d['duplicate_of']} — skipped", duplicate_of=d["duplicate_of"])
    return {"candidates": dups}


def fan_out(state: BatchState):
    sends = [
        Send("process_candidate", {
            "candidate_id": i["candidate_id"], "resume_file": i.get("resume_file", ""), "file_path": i["file_path"],
            "jd_profile": state["jd_profile"], "settings": state.get("settings") or {},
        })
        for i in state.get("candidate_inputs", []) if not i.get("duplicate_of")
    ]
    return sends or "rank"


def process_candidate(inp: CandidateInput) -> dict:
    cid = inp["candidate_id"]
    emit(cid, "candidate", "started", f"Processing {inp.get('resume_file', cid)}", resume_file=inp.get("resume_file", ""))
    try:
        result = run_candidate(inp)
    except Exception as exc:  # noqa: BLE001 — a candidate must never terminate the batch
        result = CandidateResult(candidate_id=cid, resume_file=inp.get("resume_file", ""), status="Failed",
                                 errors=[f"Unexpected error: {str(exc)[:160]}"], stage_status={s: "skipped" for s in STAGES})
    if result.status == "Failed":
        emit(cid, "candidate", "failed", result.errors[0] if result.errors else "Failed", name=result.name)
    else:
        emit(cid, "candidate", "completed",
             f"Score calculated: {result.overall_score:.1f} ({result.scorecard.classification})",
             name=result.name, overall_score=result.overall_score, classification=result.scorecard.classification,
             recommendation=result.scorecard.recommendation, warnings=len(result.warnings),
             projects=result.scorecard.score_of("projects"), github=result.scorecard.score_of("github"),
             jd_alignment=result.scorecard.score_of("jd_alignment"), candidate_status=result.status,
             processing_time=result.processing_time)
    return {"candidates": [result.model_dump()]}


def rank_node(state: BatchState) -> dict:
    emit(BATCH, "ranking", "started", "Ranking candidates")
    results = [CandidateResult.model_validate(c) for c in state.get("candidates", [])]
    mark_identity_duplicates(results)
    ranked = rank_candidates(results)
    others = [r for r in results if r.rank is None]
    others.sort(key=lambda r: r.candidate_id)
    ordered = ranked + others
    stats = {
        "total": len(results),
        "ranked": len(ranked),
        "failed": sum(1 for r in results if r.status == "Failed"),
        "duplicates": sum(1 for r in results if r.status == "Duplicate"),
        "with_warnings": sum(1 for r in results if r.status == "Completed with Warnings"),
        "classifications": classification_counts(results),
        "top": [{"candidate_id": r.candidate_id, "name": r.name, "score": r.overall_score} for r in ranked[:10]],
    }
    emit(BATCH, "ranking", "completed", f"Ranked {len(ranked)} candidates", **{k: v for k, v in stats.items() if k != "top"})
    return {"ranking": [r.model_dump() for r in ordered], "stats": stats}


def report_node(state: BatchState) -> dict:
    emit(BATCH, "report", "started", "Generating Excel report")
    results = [CandidateResult.model_validate(c) for c in state.get("ranking", [])]
    jd = JobProfile.model_validate(state.get("jd_profile") or {})
    data = build_excel_report(results, jd, state.get("settings") or {})
    name = report_filename()
    emit(BATCH, "report", "completed", f"Excel report ready: {name}", filename=name, size=len(data))
    return {"report_bytes": data, "report_filename": name}


def build_batch_graph():
    g = StateGraph(BatchState)
    g.add_node("analyze_jd", analyze_jd_node)
    g.add_node("prepare", prepare_node)
    g.add_node("process_candidate", process_candidate)
    g.add_node("rank", rank_node)
    g.add_node("report", report_node)
    g.add_edge(START, "analyze_jd")
    g.add_edge("analyze_jd", "prepare")
    g.add_conditional_edges("prepare", fan_out, ["process_candidate", "rank"])
    g.add_edge("process_candidate", "rank")
    g.add_edge("rank", "report")
    g.add_edge("report", END)
    return g.compile()


batch_graph = build_batch_graph()


def stream_batch(jd_text: str, candidate_inputs: list[dict], settings: dict[str, Any]) -> Iterator[ProgressEvent | dict]:
    """Yield ProgressEvents as they happen; the final item is the batch state dict."""
    reset_all()
    init: BatchState = {
        "jd_text": jd_text, "settings": settings, "candidate_inputs": candidate_inputs,
        "candidates": [], "ranking": [], "stats": {},
    }
    run_config = {"max_concurrency": int(settings.get("max_concurrent_candidates") or config.MAX_CONCURRENT_CANDIDATES)}
    final: dict = {}
    emit_start = ProgressEvent(BATCH, "batch", "started", f"Starting evaluation of {len(candidate_inputs)} resumes")
    yield emit_start
    for namespace, mode, chunk in batch_graph.stream(init, run_config, stream_mode=["custom", "values"], subgraphs=True):
        if mode == "custom":
            event = parse_event(chunk)
            if event:
                yield event
        elif mode == "values" and not namespace:
            final = chunk
    yield ProgressEvent(BATCH, "batch", "completed", "Evaluation complete", timestamp=time.time())
    yield final


def run_batch(jd_text: str, candidate_inputs: list[dict], settings: dict[str, Any]) -> dict:
    final: dict = {}
    for item in stream_batch(jd_text, candidate_inputs, settings):
        if isinstance(item, dict):
            final = item
    return final
