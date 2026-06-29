import os
import re
import json
import tempfile
from typing import TypedDict, List
from pathlib import Path

import streamlit as st
import pandas as pd
from PyPDF2 import PdfReader
from docx import Document
from dotenv import load_dotenv
from google import genai
from langgraph.graph import StateGraph, END

load_dotenv()

# ─── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Resume Reviewer",
    page_icon="📄",
    layout="wide",
)

# ─── Gemini client (cached) ──────────────────────────────────────────────────
@st.cache_resource
def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return None
    return genai.Client(api_key=api_key)

GEMINI_MODEL = "gemini-2.5-flash"

def call_gemini(prompt: str) -> str:
    client = get_gemini_client()
    if client is None:
        st.error("GEMINI_API_KEY not set. Add it to your .env file.")
        st.stop()
    return client.models.generate_content(model=GEMINI_MODEL, contents=prompt).text.strip()

# ─── Shared state ────────────────────────────────────────────────────────────
class ResumeState(TypedDict):
    file_path: str
    job_description: str
    raw_text: str
    candidate_name: str
    email: str
    phone: str
    education: List[str]
    experience: List[str]
    matched_skills: List[str]
    missing_skills: List[str]
    skill_match_pct: float
    ats_score: float
    score_breakdown: dict
    evaluation: str
    quality_label: str
    iteration: int
    suggestions: List[str]
    improved_bullets: List[str]
    final_feedback: str

# ─── Agents ──────────────────────────────────────────────────────────────────
def resume_parser_agent(state: ResumeState) -> ResumeState:
    fp = state["file_path"]
    if fp.endswith(".pdf"):
        reader = PdfReader(fp)
        text = "".join(p.extract_text() or "" for p in reader.pages)
    else:
        doc = Document(fp)
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return {**state, "raw_text": text}


def information_extractor_agent(state: ResumeState) -> ResumeState:
    prompt = f"""You are a resume parsing expert.
Extract information from the resume below and return ONLY valid JSON with these keys:
{{
  "candidate_name": "Full name or Unknown",
  "email": "email or Not Found",
  "phone": "phone number or Not Found",
  "education": ["degree at institution (year)"],
  "experience": ["role at company (duration)"]
}}

Resume:
{state['raw_text'][:4000]}

Return only the JSON, no markdown."""

    raw = re.sub(r"```json|```", "", call_gemini(prompt)).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        t = state["raw_text"]
        em = re.search(r'[\w\.-]+@[\w\.-]+', t)
        ph = re.search(r'(\+?\d[\d\-\s]{8,15})', t)
        data = {
            "candidate_name": "Unknown",
            "email": em.group(0) if em else "Not Found",
            "phone": ph.group(0) if ph else "Not Found",
            "education": [],
            "experience": [],
        }
    return {
        **state,
        "candidate_name": data.get("candidate_name", "Unknown"),
        "email": data.get("email", "Not Found"),
        "phone": data.get("phone", "Not Found"),
        "education": data.get("education", []),
        "experience": data.get("experience", []),
    }


def skills_analyzer_agent(state: ResumeState) -> ResumeState:
    prompt = f"""You are a technical recruiter.
Return ONLY valid JSON with matched and missing skills:
{{
  "matched_skills": ["skills present in BOTH resume and job description"],
  "missing_skills": ["skills required by JD but NOT in resume"]
}}

Job Description:
{state['job_description']}

Resume:
{state['raw_text'][:3000]}

Return only the JSON, no markdown."""

    raw = re.sub(r"```json|```", "", call_gemini(prompt)).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"matched_skills": [], "missing_skills": []}

    matched = data.get("matched_skills", [])
    missing = data.get("missing_skills", [])
    total = len(matched) + len(missing)
    pct = round((len(matched) / total * 100) if total > 0 else 0, 1)
    return {**state, "matched_skills": matched, "missing_skills": missing, "skill_match_pct": pct}


def ats_scorer_agent(state: ResumeState) -> ResumeState:
    bd = {}
    score = 0

    e_pts = 10 if state.get("email", "Not Found") != "Not Found" else 0
    p_pts = 10 if state.get("phone", "Not Found") != "Not Found" else 0
    bd["Email Present"] = e_pts
    bd["Phone Present"] = p_pts
    score += e_pts + p_pts

    edu_pts = min(len(state.get("education", [])) * 8, 15)
    bd["Education"] = edu_pts
    score += edu_pts

    exp_pts = min(len(state.get("experience", [])) * 5, 15)
    bd["Experience"] = exp_pts
    score += exp_pts

    skill_pts = round(state.get("skill_match_pct", 0) * 0.5, 1)
    bd["Skill Match"] = skill_pts
    score += skill_pts

    return {**state, "ats_score": round(min(score, 100), 1), "score_breakdown": bd}


PASS_THRESHOLD = 75
MAX_ITERATIONS = 3

def evaluator_agent(state: ResumeState) -> ResumeState:
    score = state.get("ats_score", 0)
    iteration = state.get("iteration", 0)

    if score >= 80:   quality = "Excellent"
    elif score >= 65: quality = "Good"
    elif score >= 50: quality = "Average"
    else:             quality = "Needs Improvement"

    if score >= PASS_THRESHOLD or iteration >= MAX_ITERATIONS:
        decision = "pass"
    else:
        decision = "improve"

    return {**state, "evaluation": decision, "quality_label": quality, "iteration": iteration + 1}

def route_after_evaluation(state: ResumeState) -> str:
    return state["evaluation"]


def improvement_agent(state: ResumeState) -> ResumeState:
    missing = state.get("missing_skills", [])
    score = state.get("ats_score", 0)
    quality = state.get("quality_label", "Average")
    experience = state.get("experience", [])

    prompt = f"""You are an expert resume coach. A resume scored {score}/100 (quality: {quality}).
Missing skills: {', '.join(missing) if missing else 'None'}
Current experience: {'; '.join(experience) if experience else 'Not extracted'}

Return ONLY valid JSON:
{{
  "suggestions": [
    "Specific suggestion 1",
    "Specific suggestion 2",
    "Specific suggestion 3",
    "Specific suggestion 4",
    "Specific suggestion 5"
  ],
  "improved_bullets": [
    "Achievement bullet with metrics 1",
    "Achievement bullet with metrics 2",
    "Achievement bullet with metrics 3"
  ],
  "overall_feedback": "2-3 sentence priority assessment"
}}
Tailor to the missing skills and score gap. No markdown."""

    raw = re.sub(r"```json|```", "", call_gemini(prompt)).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {
            "suggestions": [
                f"Add missing skills: {', '.join(missing[:3]) if missing else 'review JD'}",
                "Quantify every achievement with numbers",
                "Add a professional summary targeting this role",
                "Include relevant certifications and projects",
                "Ensure name, email and phone are on the first line",
            ],
            "improved_bullets": [
                "Led a team of 8 engineers to deliver a migration 20% ahead of schedule",
                "Reduced API response time by 40% via Redis caching",
                "Increased CI/CD reliability from 78% to 97% with GitHub Actions",
            ],
            "overall_feedback": "Focus on quantifying achievements and closing skill gaps.",
        }

    new_skill_match = min(state.get("skill_match_pct", 0) + 15, 100)
    return {
        **state,
        "suggestions": data.get("suggestions", []),
        "improved_bullets": data.get("improved_bullets", []),
        "final_feedback": data.get("overall_feedback", ""),
        "skill_match_pct": new_skill_match,
    }

# ─── Build LangGraph (cached so it doesn't rebuild on every rerun) ───────────
@st.cache_resource
def build_workflow():
    wf = StateGraph(ResumeState)
    wf.add_node("parser",      resume_parser_agent)
    wf.add_node("extractor",   information_extractor_agent)
    wf.add_node("skills",      skills_analyzer_agent)
    wf.add_node("scorer",      ats_scorer_agent)
    wf.add_node("evaluator",   evaluator_agent)
    wf.add_node("improvement", improvement_agent)

    wf.set_entry_point("parser")
    wf.add_edge("parser",    "extractor")
    wf.add_edge("extractor", "skills")
    wf.add_edge("skills",    "scorer")
    wf.add_edge("scorer",    "evaluator")
    wf.add_conditional_edges("evaluator", route_after_evaluation,
                             {"pass": END, "improve": "improvement"})
    wf.add_edge("improvement", "scorer")
    return wf.compile()

# ─── UI ──────────────────────────────────────────────────────────────────────
st.title("📄 AI Resume Reviewer")
st.caption("Agentic AI system · LangGraph + Google Gemini · 6-agent pipeline with iterative refinement")

st.divider()

col_left, col_right = st.columns([1, 1], gap="large")

with col_left:
    st.subheader("1. Upload Resume")
    uploaded = st.file_uploader("PDF or DOCX", type=["pdf", "docx"])

    st.subheader("2. Job Description")
    jd = st.text_area(
        "Paste the job description",
        height=260,
        placeholder="Senior Software Engineer — Cloud & Backend\n\nRequired Skills:\n- Python, FastAPI\n- AWS, Docker, Kubernetes\n- PostgreSQL, Redis\n- CI/CD pipelines\n...",
    )

    run_btn = st.button("🚀 Analyse Resume", type="primary", disabled=(uploaded is None or not jd.strip()))

with col_right:
    st.subheader("3. Workflow")
    st.markdown("""
```
START
  │
  ▼
Agent 1 · Parser          (PDF/DOCX → text)
  │
  ▼
Agent 2 · Extractor       (Gemini: structured info)
  │
  ▼
Agent 3 · Skills Analyzer (Gemini: matched / missing)
  │
  ▼
Agent 4 · ATS Scorer      (weighted formula → score)
  │
  ▼
Agent 5 · Evaluator ──── score ≥ 75 ──► END
  │
  └── score < 75 ──► Agent 6 · Improvement (Gemini)
                           │
                           └──► Agent 4 (loop, max 3×)
```
""")

st.divider()

# ─── Run workflow ─────────────────────────────────────────────────────────────
if run_btn and uploaded and jd.strip():
    suffix = ".pdf" if uploaded.name.endswith(".pdf") else ".docx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded.read())
        tmp_path = tmp.name

    initial_state: ResumeState = {
        "file_path": tmp_path,
        "job_description": jd,
        "raw_text": "",
        "candidate_name": "",
        "email": "",
        "phone": "",
        "education": [],
        "experience": [],
        "matched_skills": [],
        "missing_skills": [],
        "skill_match_pct": 0.0,
        "ats_score": 0.0,
        "score_breakdown": {},
        "evaluation": "",
        "quality_label": "",
        "iteration": 0,
        "suggestions": [],
        "improved_bullets": [],
        "final_feedback": "",
    }

    agent_labels = [
        ("parser",      "Agent 1 · Parsing resume file"),
        ("extractor",   "Agent 2 · Extracting structured information (Gemini)"),
        ("skills",      "Agent 3 · Analysing skill match (Gemini)"),
        ("scorer",      "Agent 4 · Computing ATS score"),
        ("evaluator",   "Agent 5 · Evaluating quality & routing"),
        ("improvement", "Agent 6 · Generating suggestions (Gemini)"),
    ]

    progress_bar = st.progress(0, text="Starting workflow…")
    status_box   = st.empty()
    step_total   = len(agent_labels)
    step_idx     = [0]

    def make_tracked_agent(fn, label, idx):
        def tracked(state):
            frac = idx / step_total
            progress_bar.progress(frac, text=label)
            status_box.info(f"⚙️  {label}")
            result = fn(state)
            return result
        return tracked

    app = build_workflow()

    # Patch agent functions with progress tracking for this run
    wf = StateGraph(ResumeState)
    for i, (name, label) in enumerate(agent_labels):
        fn_map = {
            "parser":      resume_parser_agent,
            "extractor":   information_extractor_agent,
            "skills":      skills_analyzer_agent,
            "scorer":      ats_scorer_agent,
            "evaluator":   evaluator_agent,
            "improvement": improvement_agent,
        }
        wf.add_node(name, make_tracked_agent(fn_map[name], label, i + 1))

    wf.set_entry_point("parser")
    wf.add_edge("parser",    "extractor")
    wf.add_edge("extractor", "skills")
    wf.add_edge("skills",    "scorer")
    wf.add_edge("scorer",    "evaluator")
    wf.add_conditional_edges("evaluator", route_after_evaluation,
                             {"pass": END, "improve": "improvement"})
    wf.add_edge("improvement", "scorer")
    tracked_app = wf.compile()

    try:
        final = tracked_app.invoke(initial_state)
    except Exception as e:
        st.error(f"Workflow error: {e}")
        st.stop()
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    progress_bar.progress(1.0, text="Complete!")
    status_box.empty()

    # ── Results ───────────────────────────────────────────────────────────────
    st.success("Analysis complete!")

    # Score gauge row
    score  = final["ats_score"]
    label  = final["quality_label"]
    cycles = max(0, final["iteration"] - 1)

    color_map = {
        "Excellent":         "#22c55e",
        "Good":              "#84cc16",
        "Average":           "#f59e0b",
        "Needs Improvement": "#ef4444",
    }
    score_color = color_map.get(label, "#6b7280")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("ATS Score",          f"{score} / 100")
    m2.metric("Quality",            label)
    m3.metric("Skill Match",        f"{final['skill_match_pct']}%")
    m4.metric("Refinement Cycles",  cycles)

    st.divider()

    tab1, tab2, tab3, tab4 = st.tabs(["👤 Profile", "🎯 Skills", "💡 Suggestions", "📊 Score Breakdown"])

    with tab1:
        st.markdown(f"**Name:** {final['candidate_name']}")
        st.markdown(f"**Email:** {final['email']}")
        st.markdown(f"**Phone:** {final['phone']}")

        ec, xc = st.columns(2)
        with ec:
            st.markdown("**Education**")
            for e in final["education"]:
                st.markdown(f"- {e}")
            if not final["education"]:
                st.caption("Not extracted")
        with xc:
            st.markdown("**Experience**")
            for x in final["experience"]:
                st.markdown(f"- {x}")
            if not final["experience"]:
                st.caption("Not extracted")

    with tab2:
        mc, gc = st.columns(2)
        with mc:
            st.markdown(f"**Matched ({len(final['matched_skills'])})**")
            for s in final["matched_skills"]:
                st.markdown(f"✅ {s}")
            if not final["matched_skills"]:
                st.caption("None identified")
        with gc:
            st.markdown(f"**Missing ({len(final['missing_skills'])})**")
            for s in final["missing_skills"]:
                st.markdown(f"❌ {s}")
            if not final["missing_skills"]:
                st.caption("None — great match!")

    with tab3:
        if final.get("final_feedback"):
            st.info(final["final_feedback"])

        if final.get("suggestions"):
            st.markdown("**Actionable Suggestions**")
            for i, s in enumerate(final["suggestions"], 1):
                st.markdown(f"{i}. {s}")

        if final.get("improved_bullets"):
            st.markdown("**Sample Improved Experience Bullets**")
            for b in final["improved_bullets"]:
                st.markdown(f"- {b}")

        if not final.get("suggestions") and not final.get("improved_bullets"):
            st.success("Resume passed without requiring improvement suggestions.")

    with tab4:
        bd = final["score_breakdown"]
        df = pd.DataFrame({
            "Component": list(bd.keys()),
            "Points":    list(bd.values()),
            "Max":       [10, 10, 15, 15, 50],
        })
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.bar_chart(df.set_index("Component")["Points"])
