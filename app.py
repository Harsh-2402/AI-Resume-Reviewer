"""AI Internship Candidate Evaluation & Ranking Platform — Streamlit entry point."""
import shutil
import tempfile

import streamlit as st

import config
from models.jd import JobProfile
from models.result import CandidateResult
from services import github_service, llm_service
from services.pdf_service import DocumentExtractionError, extract_document_text
from services.zip_service import ZipError, extract_resumes
from ui.progress import ProgressDashboard
from ui.results import (
    render_candidate_detail,
    render_comparison,
    render_job_profile,
    render_processing_log,
    render_ranking_table,
    render_summary,
    render_top_candidates,
)
from ui.styles import inject_css, inject_tab_resize_fix
from utils.validation import validate_batch_inputs
from workflow.batch_graph import stream_batch
from workflow.events import ProgressEvent

st.set_page_config(page_title="AI Internship Candidate Evaluator", page_icon="🎓", layout="wide")
inject_css()

DEFAULTS = {
    "phase": "setup",            # setup | running | done
    "jd_text": "",
    "jd_source": "",
    "zip_bytes": None,
    "zip_name": "",
    "extraction": None,
    "workdir": "",
    "settings": {},
    "final": None,
    "run_error": "",
}
for key, value in DEFAULTS.items():
    st.session_state.setdefault(key, value)


def reset_evaluation() -> None:
    if st.session_state.get("workdir"):
        shutil.rmtree(st.session_state["workdir"], ignore_errors=True)
    for key, value in DEFAULTS.items():
        st.session_state[key] = value
    for key in ("top_n", "detail_select", "compare_select"):
        st.session_state.pop(key, None)


# ─── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🎓 Internship Evaluator")
    st.caption("LangGraph · Gemini · evidence-based ranking")
    running = st.session_state["phase"] == "running"

    st.subheader("1 · Job description")
    jd_file = st.file_uploader("Upload JD (PDF / DOCX / TXT)", type=["pdf", "docx", "txt"], disabled=running)
    jd_paste = st.text_area("…or paste the JD", height=160, disabled=running, placeholder="Software Engineering Intern — Backend\nRequired: Python, FastAPI, PostgreSQL, Docker…")
    jd_text, jd_source = "", ""
    if jd_file is not None:
        try:
            jd_text = extract_document_text(jd_file.getvalue(), jd_file.name)
            jd_source = jd_file.name
        except DocumentExtractionError as exc:
            st.error(f"Could not read JD: {exc}")
    elif jd_paste.strip():
        jd_text, jd_source = jd_paste.strip(), "pasted text"
    if jd_text:
        st.caption(f"✓ JD loaded ({len(jd_text):,} characters)")

    st.subheader("2 · Resume batch")
    zip_file = st.file_uploader("Upload ZIP of PDF resumes", type=["zip"], disabled=running)
    pdf_count = 0
    if zip_file is not None:
        if st.session_state["zip_name"] != zip_file.name or st.session_state["zip_bytes"] is None:
            st.session_state["zip_bytes"] = zip_file.getvalue()
            st.session_state["zip_name"] = zip_file.name
        try:
            import io
            import zipfile

            with zipfile.ZipFile(io.BytesIO(st.session_state["zip_bytes"])) as zf:
                names = [n for n in zf.namelist() if not n.endswith("/")]
            pdfs = [n for n in names if n.lower().endswith(".pdf") and not any(p.startswith(".") or p == "__MACOSX" for p in n.split("/"))]
            pdf_count = len(pdfs)
            st.caption(f"✓ {len(names)} files found · {pdf_count} PDF resumes · {len(names) - pdf_count} will be skipped")
        except zipfile.BadZipFile:
            st.error("The uploaded file is not a valid ZIP archive.")

    st.subheader("3 · Evaluation settings")
    with st.expander("Scoring weights & concurrency", expanded=False):
        st.caption("Weights are renormalized to 100%. Areas with no evidence (e.g. no GitHub) are excluded per candidate.")
        weights = {}
        for key, default in config.INTERNSHIP_WEIGHTS.items():
            weights[key] = st.slider(config.COMPONENT_LABELS[key], 0.0, 0.5, float(default), 0.01, key=f"w_{key}", disabled=running)
        total = sum(weights.values()) or 1.0
        st.caption("Effective: " + " · ".join(f"{config.COMPONENT_LABELS[k][:6]} {v / total:.0%}" for k, v in weights.items()))
        max_conc = st.slider("Candidates processed concurrently", 1, 20, config.MAX_CONCURRENT_CANDIDATES, disabled=running)
    st.caption(("✓ Gemini key configured" if llm_service.is_configured() else "✗ GEMINI_API_KEY missing — add it to .env")
               + "  \n" + ("✓ GitHub token configured" if github_service.has_token() else "○ No GITHUB_TOKEN (60 requests/hour limit)"))

    start = st.button("🚀 Start Evaluation", type="primary", disabled=running or st.session_state["phase"] == "done", width="stretch")
    if st.button("🆕 New Evaluation", disabled=running, width="stretch"):
        reset_evaluation()
        st.rerun()

# ─── Start ───────────────────────────────────────────────────────────────────
if start and st.session_state["phase"] == "setup":
    errors = validate_batch_inputs(jd_text, pdf_count, weights)
    if not llm_service.is_configured():
        errors.append("GEMINI_API_KEY is not set. Add it to your .env file.")
    if errors:
        for e in errors:
            st.error(e)
        st.stop()
    workdir = tempfile.mkdtemp(prefix="intern_eval_")
    try:
        extraction = extract_resumes(st.session_state["zip_bytes"], workdir)
    except ZipError as exc:
        st.error(str(exc))
        st.stop()
    if extraction.valid_count == 0:
        st.error("No valid PDF resumes were found in the ZIP.")
        st.stop()
    st.session_state.update({
        "phase": "running", "jd_text": jd_text, "jd_source": jd_source, "workdir": workdir, "extraction": extraction,
        "settings": {"weights": weights, "max_concurrent_candidates": max_conc}, "final": None, "run_error": "",
    })
    st.rerun()

# ─── Main area ───────────────────────────────────────────────────────────────
phase = st.session_state["phase"]
# One placeholder for the whole main area so a phase change replaces the previous content immediately
# (Streamlit otherwise leaves stale elements visible until the blocking evaluation run finishes).
main = st.empty().container()

if phase == "setup":
  with main:
    # Kept to exactly two top-level elements: the running phase writes its title + dashboard into the same
    # two slots, so nothing from this page lingers on screen while the evaluation blocks the script.
    st.markdown("""# AI Internship Candidate Evaluation & Ranking

Upload a **job description** and a **ZIP of PDF resumes**. Every candidate is analyzed independently by a
LangGraph pipeline — education, coursework, skills, projects, certifications, achievements, GitHub evidence —
then scored deterministically, ranked, and exported to a multi-sheet Excel report.

<div style="display:flex;gap:1.5rem;flex-wrap:wrap;margin:0.5rem 0 1rem 0">
<div style="flex:1;min-width:200px"><b>Evidence over experience</b><br>Students are scored on demonstrated potential: projects, coursework, certifications, GitHub — not years of experience.</div>
<div style="flex:1;min-width:200px"><b>Explainable &amp; fair</b><br>Every score has a written reason. Missing information is neutral, never a penalty. No demographic signals are used.</div>
<div style="flex:1;min-width:200px"><b>Resilient batches</b><br>Invalid PDFs, broken links, missing GitHub profiles or API limits never stop the batch.</div>
</div>

```
START ─► JD Analyzer ─► ZIP Extractor ─► Send ×N (parallel, independent)
   per candidate: Parser ─► Extractor ─► [Education | Skills | Projects | Certifications | Achievements | GitHub]
                                       ─► Evidence Validator ─► Internship Scorer ─► Candidate Evaluator
                                                ─► Ranking Engine ─► Excel Report ─► END
```
""", unsafe_allow_html=True)
    st.info("Fill in the sidebar and click **Start Evaluation**.")

elif phase == "running":
  with main:
    st.title("Evaluating candidates…")
    extraction = st.session_state["extraction"]
    inputs = [{"candidate_id": f.candidate_id, "resume_file": f.filename, "file_path": f.path, "duplicate_of": f.duplicate_of}
              for f in extraction.files]
    dashboard = ProgressDashboard(st.container(), inputs, st.session_state["jd_source"], extraction.summary)
    final = None
    try:
        for item in stream_batch(st.session_state["jd_text"], inputs, st.session_state["settings"]):
            if isinstance(item, ProgressEvent):
                dashboard.handle(item)
            else:
                final = item
    except Exception as exc:  # noqa: BLE001 — surface, never hang
        st.session_state["run_error"] = f"{type(exc).__name__}: {exc}"
    dashboard.render(force=True)
    if final is None and not st.session_state["run_error"]:
        st.session_state["run_error"] = "The workflow ended without producing results."
    st.session_state["final"] = final
    st.session_state["phase"] = "done"
    st.rerun()

elif phase == "done":
  with main:
    final = st.session_state["final"]
    if st.session_state["run_error"] or not final:
        st.title("Evaluation failed")
        st.error(st.session_state["run_error"] or "No results were produced.")
        st.info("Click **New Evaluation** in the sidebar to start over.")
    else:
        results = [CandidateResult.model_validate(c) for c in final.get("ranking", [])]
        jd = JobProfile.model_validate(final.get("jd_profile") or {})
        stats = final.get("stats", {})
        render_summary(results, stats, final.get("report_bytes", b""), final.get("report_filename", "report.xlsx"))
        inject_tab_resize_fix()
        tabs = st.tabs(["🏆 Top candidates", "📊 All rankings", "🔍 Candidate details", "⚖️ Compare", "🧾 Processing log", "📋 Job profile"])
        with tabs[0]:
            render_top_candidates(results)
        with tabs[1]:
            render_ranking_table(results)
        with tabs[2]:
            render_candidate_detail(results, jd)
        with tabs[3]:
            render_comparison(results)
        with tabs[4]:
            extraction = st.session_state["extraction"]
            render_processing_log(results, extraction.summary if extraction else "", extraction.skipped if extraction else [])
        with tabs[5]:
            render_job_profile(jd, st.session_state["settings"])
