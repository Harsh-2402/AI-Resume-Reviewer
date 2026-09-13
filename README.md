<div align="center">

# 🎓 AI Internship Candidate Evaluation & Ranking Platform

**Evidence-based, explainable intern hiring — powered by LangGraph, Google Gemini & Streamlit**

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.x-1C1C1C?style=for-the-badge&logo=langchain&logoColor=white)](https://github.com/langchain-ai/langgraph)
[![Gemini](https://img.shields.io/badge/Gemini_3.6_Flash-Google-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://aistudio.google.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

Upload a job description + a ZIP of resumes (PDF / DOCX / TXT) → every candidate is analyzed, scored, ranked → download a 10-sheet Excel report.

</div>

---

## ✨ What it does

- 📦 **Batch input** — a JD (PDF/DOCX/TXT or pasted) and a ZIP of resumes in PDF, DOCX or TXT (nested folders OK; junk files skipped; duplicates detected)
- 🔍 **Deep per-candidate analysis** — education, coursework, technical skills, projects, certifications, achievements & hackathons, GitHub repositories, live project links
- 🧾 **Evidence cross-checks** — resume claims vs. public GitHub evidence, reachable project links, credential pages (neutral wording, never accusations)
- 🧮 **Deterministic internship scoring** — Gemini classifies, Python scores; every number has a written reason; missing areas are excluded, not penalized
- 🏆 **Ranking + interview guidance** — classification, recommendation, interview priority, candidate-specific interview questions
- 📈 **Live Streamlit dashboard** — per-candidate stage checklist, per-agent progress, live ranking table, log, warnings/errors
- 📊 **Professional Excel report** — Final Ranking (sorted by score) plus 9 evidence sheets, formatted with filters, color scales and hyperlinks
- 🛡️ **Resilient** — an invalid PDF, a missing GitHub profile, a broken link, a GitHub rate limit or a Gemini hiccup never stops the batch

### The product principle

This is an **internship** evaluator. Students are scored on *demonstrated potential* — projects, coursework, certifications, GitHub, learning progression — not years of experience, keyword counts, commit counts, or university prestige. A student with strong projects and zero jobs can rank first.

---

## 🏗️ Architecture

```
START ─► JD Analyzer ─► ZIP Extractor ─► Send ×N (parallel, independent candidates)
                                                 │
   per candidate:  Parser ─► Extractor ─► ┬ Education & Coursework Analyzer   (Gemini)
                                          ├ Skills Analyzer                   (Gemini)
                                          ├ Project Analyzer                  (Gemini)
                                          ├ Certification Analyzer            (Gemini)
                                          ├ Achievement Analyzer              (Gemini)
                                          └ GitHub Analyzer                   (GitHub REST, no LLM)
                                          ─► Evidence Validator (links, credentials, resume↔GitHub)
                                          ─► Internship Scorer  (deterministic, weighted, renormalized)
                                          ─► Candidate Evaluator (Gemini: strengths, concerns, questions)
                                                 │
                                       Ranking Engine ─► Excel Report Generator ─► END
```

Two LangGraph graphs: a **batch graph** that fans out with `Send` (bounded by `max_concurrency`) and a **candidate subgraph** whose six analyzers run in parallel. Nodes stream progress events to the Streamlit main thread, which is what makes the live dashboard possible.

### Scoring model

| Component | Default weight | Source |
|---|:---:|---|
| Education | 15% | degree relevance, academic strength, GPA (if given), honors |
| Coursework | 10% | courses directly/related to the role |
| Technical skills | 15% | JD coverage (direct / strongly related / transferable) × demonstrated depth |
| Projects | 25% | depth, complexity, relevance, ownership, implementation evidence — depth-weighted, not counted |
| GitHub | 10% | repo quality 25 · meaningful activity 20 · tech relevance 20 · complexity 15 · docs 10 · tests/CI 5 · recency 5 |
| Certifications | 5% | type (professional → workshop) × relevance + verification |
| Achievements | 5% | significance × relevance |
| JD alignment | 10% | required-skill coverage, project/degree/coursework relevance |
| Learning potential | 5% | observable signals only (progression, breadth, certs, hackathons, recent activity) |

Weights are adjustable in the sidebar. Components with no evidence (no GitHub, no certifications…) are **N/A** and the remaining weights are renormalized.

| Score | Classification | Recommendation |
|:---:|---|---|
| 90–100 | Exceptional Internship Candidate | Strongly Recommend |
| 80–89 | Strong Internship Candidate | Recommend |
| 70–79 | Good Internship Candidate | Consider |
| 60–69 | Potential / Review | Needs Review |
| 50–59 | Weak Match | Do Not Prioritize |
| 0–49 | Low Match | Do Not Prioritize |

---

## 🚀 Quick start

```bash
git clone https://github.com/Harsh-2402/AI-Resume-Reviewer.git
cd AI-Resume-Reviewer
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # add GEMINI_API_KEY (and ideally GITHUB_TOKEN)
streamlit run app.py
```

> 🔑 Free Gemini key: [Google AI Studio](https://aistudio.google.com/app/apikey). A `GITHUB_TOKEN` (public repo read) lifts GitHub's limit from 60 to 5,000 requests/hour — recommended for batches.

Then in the app: upload the JD → upload the resume ZIP → (optionally tune weights/concurrency) → **Start Evaluation** → watch the dashboard → **Download Excel Report**. **New Evaluation** resets everything without restarting.

---

## 📊 Excel report

`intern_candidate_evaluation_<date>.xlsx` — Final Ranking · Candidate Details · Project Analysis · GitHub Analysis · Skills Matrix · Education · Certifications · Achievements · Interview Recommendations · Processing Log · Job Profile. Sheet 1 is the recruiter summary sorted by overall score; the rest preserve the evidence behind every number.

---

## 🧪 Tests

```bash
venv/bin/pytest -q
```

The suite runs offline: Gemini, GitHub and HTTP are faked. It covers ZIP handling (nested, junk, duplicates, zip-slip), PDF/DOCX extraction, profile enrichment, GitHub (404 / rate limit / timeout / no profile / cache), evidence validation, deterministic scoring & renormalization, ranking & tie-breakers, an end-to-end batch with a corrupt PDF and a duplicate, and Excel structure.

---

## ⚙️ Configuration

All values in [`config.py`](config.py) can be overridden via `.env`: `GEMINI_MODEL` (default `gemini-3.6-flash`), `GEMINI_MAX_CONCURRENT_REQUESTS`, `MAX_CONCURRENT_CANDIDATES`, `GITHUB_TOKEN`, `GITHUB_TIMEOUT`, `URL_TIMEOUT`, scoring weights, classification thresholds.

---

## 📁 Project structure

```
app.py            Streamlit entry point           workflow/   batch & candidate LangGraph graphs, events
agents/           one module per agent + prompts  scoring/    weights, deterministic scorer, ranking, transferable tech map
models/           Pydantic models & graph state   services/   Gemini, GitHub, PDF, ZIP, URL checks, cache
reports/          Excel report builder            ui/         progress dashboard, results views, styles
utils/            text/regex, retry, validation   tests/      offline pytest suite
AI_Resume_Reviewer_Complete.ipynb   legacy single-resume prototype (not used by the app)
```

---

## 🛠️ Tech stack

LangGraph 1.x (orchestration) · Google GenAI SDK / Gemini 3.6 Flash (structured JSON output) · Streamlit · Pydantic v2 · PyPDF2 / python-docx · requests (GitHub REST) · openpyxl · pytest

---

## 📜 License

MIT — see [`LICENSE`](LICENSE).
