# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An **AI Internship Candidate Evaluation, Ranking & Reporting Platform**: a Streamlit app that takes a job description plus a ZIP of resumes (PDF/DOCX/TXT), analyzes every candidate through a LangGraph agent pipeline (Gemini for extraction/classification, Python for scoring), ranks them, shows live progress, and exports a multi-sheet Excel report.

Product principle: this is an **internship** evaluator, not an experienced-hire ATS. Score demonstrated potential (education, coursework, projects, certifications, achievements, GitHub evidence, learning progression) — never years of experience, keyword density, commit counts, or university prestige. Missing information is neutral (N/A), never a penalty. No demographic signals.

`AI_Resume_Reviewer_Complete.ipynb` is the original single-resume prototype and is **not** part of the product; leave it alone unless asked.

## Environment & commands

```bash
python -m venv venv && source venv/bin/activate     # the checked-in venv dir is `venv/`
pip install -r requirements.txt
cp .env.example .env                                 # set GEMINI_API_KEY; GITHUB_TOKEN strongly recommended
streamlit run app.py                                 # the app
venv/bin/pytest -q                                   # offline test suite (Gemini/GitHub/HTTP are faked)
venv/bin/pytest -q tests/test_scoring.py -k renormal # single test
venv/bin/python -m compileall -q agents scoring services models utils workflow reports ui tests
```

Gemini model is `gemini-3.6-flash` (`GEMINI_MODEL` env). `gemini-2.5-flash` is retired (404). Free-tier quotas/spend caps surface as `429 RESOURCE_EXHAUSTED`; `services/llm_service.py` retries transient 429/5xx with backoff but does **not** retry spend-cap/billing errors.

`tests/conftest.py` provides `fake_llm` (routes `generate_structured` by schema), `make_pdf(text)` (minimal PDF PyPDF2 can read) and `make_zip(...)`; `tests/fakes.py` provides `FakeSession` for `github_service.session` / `url_service.session`. Every service that does I/O exposes a module-level `session`/function that tests monkeypatch — keep that pattern when adding I/O.

## Architecture

```
app.py (Streamlit)  ──►  workflow/batch_graph.py  (LangGraph, streamed on the main thread)
                              START ─► analyze_jd ─► prepare ─► Send ×N process_candidate ─► rank ─► report ─► END
                                                                         │
                                                        workflow/candidate_graph.py (LangGraph subgraph)
                              parser ─► extractor ─► [education | skills | projects | certifications | achievements | github]
                                                   ─► evidence ─► scoring ─► evaluator ─► END
```

- **Batch graph** fans out with `Send` (one branch per resume, `config={"max_concurrency": settings.max_concurrent_candidates}`); exact-duplicate files (sha256) are emitted as `Duplicate` results in `prepare` without processing. `rank` marks identity duplicates (same email/phone/name → keep the higher score), ranks, and builds stats; `report` builds the Excel bytes into state.
- **Candidate subgraph** runs the six analyzers in parallel after extraction. Every node is wrapped by `workflow/candidate_graph._wrap`: it emits progress events, times the stage, and converts exceptions into warnings (non-critical stages) or a `Failed` candidate (parser/extractor). A candidate can never abort the batch.
- **Live progress** works because nodes call `workflow/events.emit(...)` → LangGraph `get_stream_writer()`, and `stream_batch()` iterates `batch_graph.stream(..., stream_mode=["custom","values"], subgraphs=True)`. `app.py` runs that generator in a worker thread that feeds a `queue.Queue`; the Streamlit main thread polls it with a 1 s timeout, calling `ProgressDashboard.handle(event)` per event and `ProgressDashboard.heartbeat()` on every idle tick (stage timers, "N candidates in progress — stage ×k" status line, ETA, a "… still working" log line after 10 s of silence). Long Gemini calls emit nothing for up to a minute, so without the heartbeat the page looks frozen. Never touch Streamlit or `st.session_state` from the worker thread — pass values in. Event shape: `ProgressEvent(candidate_id ("" = batch), stage, status ∈ started|completed|warning|failed|duplicate, message, data)`. The candidate-level `completed` event carries the score fields the live ranking table needs.
- **State**: `models/state.py`. `CandidateState` keys written by parallel nodes carry reducers (`warnings`/`errors` → `operator.add`, `stage_status`/`timings` → dict merge); every analyzer writes only its own `*_analysis` key. State holds plain dicts (`model_dump()`), agents re-validate into Pydantic models on entry. `BatchState.candidates` is an `operator.add` list; the ranked/ordered copy lives in `ranking`.

### Agents (`agents/`)

| Stage | Module | LLM | Output key |
|---|---|---|---|
| jd | `jd_analyzer.analyze_jd` | yes → `JobProfile` | `jd_profile` (batch) |
| parser | `resume_parser` | no (PyPDF2 / python-docx / text decode, by extension) | `raw_text` |
| extractor | `information_extractor` | yes → `CandidateProfile`, then regex enrichment (email/phone/URLs, GitHub profile derived from repo URLs, `project_links`) | `profile` |
| education | `education_analyzer` | yes → `EducationAnalysis` (degree relevance, academic strength, per-course relevance) | `education_analysis` |
| skills | `skills_analyzer` | yes → `SkillsAnalysis` (per-skill Demonstrated/Claimed, per-JD-skill coverage; deterministic pre-match from `scoring/transferable.py` is passed as hints and back-fills anything the model skips) | `skills_analysis` |
| projects | `project_analyzer` | yes → `ProjectAnalysis` (depth Basic…Highly Advanced, complexity 1-5, relevance, ownership, implementation evidence, progression) | `project_analysis` |
| certifications | `certification_analyzer` | yes → cert type (Professional/Industry/Course/Training/Workshop) + relevance | `certification_analysis` |
| achievements | `achievement_analyzer` | yes → significance/relevance per item + `learning_signals` | `achievement_analysis` |
| github | `github_analyzer` | **no** — GitHub REST via `services/github_service.py` | `github_analysis` |
| evidence | `evidence_validator` | **no** — link checks, credential verification, resume↔GitHub skill cross-check, final JD skill matrix; upgrades project `implementation_evidence` when links/repos verify (never downgrades for broken links) | `evidence_analysis` (+ rewrites `project_analysis`) |
| scoring | `internship_scorer` → `scoring/internship_scorer.py` | **no** | `scorecard` |
| evaluator | `candidate_evaluator` | yes → `CandidateEvaluation` (strengths/concerns/interview questions); deterministic fallback if the LLM fails | `evaluation` |

Prompts live in `agents/prompts.py` (`SYSTEM_PROMPT` carries the fairness/evidence rules). All LLM calls go through `services/llm_service.generate_structured(prompt, PydanticModel)` which uses Gemini `response_schema` (so **analysis models must stay Gemini-schema-compatible: no free-form `dict` fields, use `Literal` enums**), a global semaphore (`GEMINI_MAX_CONCURRENT_REQUESTS`), retry/backoff, and a per-batch prompt cache. ~7 LLM calls per candidate + 1 for the JD.

### Scoring (`scoring/`)

The LLM never emits scores. `internship_scorer.score_candidate` maps classifications to 0–100 component scores with an explanation string each, then computes the weighted overall:

- Weights: `config.INTERNSHIP_WEIGHTS` (education .15, coursework .10, technical_skills .15, projects .25, github .10, certifications .05, achievements .05, jd_alignment .10, learning_potential .05); overridable per run via `settings["weights"]` (UI sliders).
- **N/A handling**: components with no evidence (no GitHub / no certs / no achievements / no coursework / no education info) score `None`, get `applied_weight = 0`, and the remaining weights are **renormalized** — absence is neutral. Projects are the exception: no projects → 15 (it is the primary signal).
- Projects are depth-weighted (best 50% / second 30% / third 20%) so one deep project beats many shallow ones; commit count in GitHub is a capped supporting signal only.
- Classification thresholds and recommendations: `config.CLASSIFICATION_THRESHOLDS` / `RECOMMENDATION_BY_CLASSIFICATION` (90 Exceptional → Strongly Recommend … <50 Low Match → Do Not Prioritize).
- `scoring/ranking.py`: sort by overall desc, tie-breakers projects → technical skills → education+coursework → candidate id; rank == interview priority. Only `Completed`/`Completed with Warnings` candidates are ranked.
- `scoring/transferable.py`: alias + family + group map (AWS↔Azure↔GCP, FastAPI↔Flask↔Django, …) → `Direct Match / Strongly Related / Transferable / Missing`. Coursework counts toward JD "skills" that are fundamentals (Data Structures, Databases…).

### GitHub (`services/github_service.py`, `agents/github_analyzer.py`)

Public REST only; `GITHUB_TOKEN` raises the limit from 60 to 5000 req/h. Per candidate: user + up to `GITHUB_MAX_REPOS` own repos (forks excluded), then deep inspection of the top `GITHUB_MAX_DEEP_REPOS` (resume-referenced repos first, then relevance): languages, README size, tree (tests/CI/Docker/license, code file count), commits (count from the `Link` header + 30 recent messages for a "meaningful commit" heuristic). `GitHubScore` = quality 25 / meaningful activity 20 / tech relevance 20 / complexity 15 / docs 10 / tests-CI 5 / recency 5. Rate limit or 404 → status `rate_limited`/`not_found`, score `None`, warning — never a batch failure. Requests are cached per batch in `services/cache_service.github_cache`.

### Report (`reports/excel_report.py`)

`build_excel_report(results, jd, settings) -> bytes` (openpyxl, in-memory). Sheets: Final Ranking (sorted by Overall Score desc), Candidate Details, Project Analysis (row per project), GitHub Analysis, Skills Matrix (candidate × JD skill: Strong Match/Match/Related/Transferable/Missing/N/A), Education, Certifications (row per cert incl. verification status), Achievements, Interview Recommendations, Processing Log, Job Profile. `_write_sheet` applies frozen header, auto-filter, widths, wrap, hyperlinks, `0.0` number format, 3-color scale on score columns, fills on classification/recommendation/status. Filename `intern_candidate_evaluation_<YYYY-MM-DD>.xlsx`.

### UI (`app.py`, `ui/`)

Phases in `st.session_state["phase"]`: `setup` (sidebar: JD upload/paste, ZIP upload, weights/concurrency, key indicators, Start) → `running` (`ProgressDashboard`: overall bar, current candidate stage checklist ✓●○⚠✗, per-agent counts, summary metrics, live ranking table, log, warnings/errors) → `done` (`ui/results.py`: summary + Excel download, Top 5/10 cards, full ranking table, candidate detail tabs, multi-candidate comparison, processing log, job profile). **New Evaluation** clears session state and the temp dir. ZIP bytes are extracted to a `tempfile.mkdtemp()` dir (`services/zip_service.extract_resumes`: nested dirs ok, accepts `services/pdf_service.RESUME_EXTENSIONS` (pdf/docx/txt/md), skips `__MACOSX`/dotfiles/other types/empty with a reason, zip-slip safe, sha256 duplicates). The parser dispatches by extension via `pdf_service.extract_resume_text`; legacy `.doc` is rejected with a "save as .docx" reason. Use `width="stretch"` (not `use_container_width`) — Streamlit ≥ 1.45. Two Streamlit quirks are worked around deliberately: the setup page is exactly two top-level elements so the blocking `running` phase replaces them in place (otherwise prior-run elements linger until the script ends), and `ui/styles.inject_tab_resize_fix()` dispatches a window `resize` on tab clicks because dataframes inside initially-hidden tabs paint only their first column.

## Configuration (`config.py`, all env-overridable)

`GEMINI_MODEL`, `GEMINI_MAX_CONCURRENT_REQUESTS=4`, `GEMINI_TIMEOUT_SECONDS`, `GEMINI_MAX_RETRIES`, `MAX_CONCURRENT_CANDIDATES=10`, `MAX_RESUME_CHARS=12000`, `MIN_RESUME_CHARS=50` (below → "scanned?" warning), `GITHUB_TOKEN`, `GITHUB_TIMEOUT=15`, `GITHUB_MAX_REPOS=30`, `GITHUB_MAX_DEEP_REPOS=6`, `URL_TIMEOUT=10`, `MAX_PROJECT_LINK_CHECKS`, `MAX_CREDENTIAL_CHECKS`, `INTERNSHIP_WEIGHTS`, `CLASSIFICATION_THRESHOLDS`, `RECOMMENDATION_BY_CLASSIFICATION`.

## Conventions

- Agents are `run(state) -> partial state dict`; keep them free of try/except for I/O failures — the graph wrapper handles that and records warnings. Return `{"warnings": [...]}` for soft issues.
- Deterministic first: anything objective (parsing, matching, scoring, ranking, Excel) is Python; Gemini only interprets/classifies.
- Neutral language about unverifiable claims ("Limited public evidence available…", "could not be independently verified") — never "fake"/"lying".
- When adding a component score: add to `config.INTERNSHIP_WEIGHTS` + `COMPONENT_LABELS`, a `*_score()` in `scoring/internship_scorer.py` returning `ComponentScore` with an explanation, and the Excel/UI columns.
