"""Live progress dashboard driven by ProgressEvents from the batch graph (main-thread rendering)."""
import html
import math
import time
from collections import Counter, deque

import pandas as pd
import streamlit as st

import config
from models.result import STAGE_LABELS, STAGES
from workflow.events import ProgressEvent

SYMBOL = {"completed": "✓", "warning": "⚠", "failed": "✗", "started": "●", "waiting": "○", "skipped": "–"}
CSS_CLASS = {"completed": "stage-ok", "warning": "stage-warn", "failed": "stage-fail", "started": "stage-run",
             "waiting": "stage-wait", "skipped": "stage-skip"}
LLM_STAGES = {"extractor", "education", "skills", "projects", "certifications", "achievements", "evaluator"}
HEARTBEAT_LOG_EVERY = 10.0  # seconds of silence before a "still working" line is logged


def _new_candidate(cid: str, file: str = "") -> dict:
    return {
        "id": cid, "file": file, "name": "", "status": "Queued", "stages": {s: "waiting" for s in STAGES},
        "stage_started": {}, "score": None, "row": None, "warnings": 0, "last_update": 0.0, "started_at": 0.0,
    }


class ProgressDashboard:
    def __init__(self, container, candidate_inputs: list[dict], jd_source: str, zip_summary: str,
                 max_concurrent: int = config.MAX_CONCURRENT_CANDIDATES) -> None:
        self.total = sum(1 for c in candidate_inputs if not c.get("duplicate_of"))
        self.max_concurrent = max(1, max_concurrent)
        self.candidates: dict[str, dict] = {}
        for c in candidate_inputs:
            cand = _new_candidate(c["candidate_id"], c.get("resume_file", ""))
            if c.get("duplicate_of"):
                cand["status"] = "Duplicate"
            self.candidates[c["candidate_id"]] = cand
        self.jd_source = jd_source
        self.zip_summary = zip_summary
        self.jd_status = "pending"
        self.jd_started_at = 0.0
        self.agent_counts = {s: 0 for s in STAGES}
        self.log: deque[str] = deque(maxlen=400)
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.batch_message = "Starting…"
        self.started_at = time.time()
        self.first_candidate_at = 0.0
        self.completion_times: list[float] = []
        self.last_event_at = self.started_at
        self.last_heartbeat_log = self.started_at
        self._last_render = 0.0

        with container:
            self.header = st.empty()
            self.progress = st.empty()
            self.status_line = st.empty()
            col_left, col_right = st.columns([1, 1], gap="large")
            with col_left:
                st.markdown("#### Current candidate")
                self.current = st.empty()
            with col_right:
                st.markdown("#### Agent progress")
                self.agents = st.empty()
            self.summary = st.empty()
            st.markdown("#### Live candidate ranking")
            self.ranking = st.empty()
            st.markdown("#### Processing log")
            self.logbox = st.empty()
            self.issues = st.empty()
        self.render(force=True)

    # ── event handling ───────────────────────────────────────────────────────
    def handle(self, event: ProgressEvent) -> None:
        cid, stage, status = event.candidate_id, event.stage, event.status
        who = cid or "BATCH"
        self.last_event_at = self.last_heartbeat_log = time.time()
        if status != "started" or stage in ("jd", "ranking", "report", "batch", "candidate"):
            self.log.append(f"{event.time_str}  {who:<9} {event.message}")

        if not cid:
            if stage == "jd":
                self.jd_status = "done" if status == "completed" else "running"
                if status == "started":
                    self.jd_started_at = event.timestamp
            if stage in ("batch", "ranking", "report", "jd"):
                self.batch_message = event.message
            self.render(force=True)
            return

        cand = self.candidates.setdefault(cid, _new_candidate(cid))
        cand["last_update"] = event.timestamp
        if stage == "candidate":
            if status == "started":
                cand["status"] = "Processing"
                cand["started_at"] = event.timestamp
                self.first_candidate_at = self.first_candidate_at or event.timestamp
            elif status == "completed":
                cand["status"] = event.data.get("candidate_status", "Completed")
                cand["name"] = event.data.get("name", cand["name"])
                cand["score"] = event.data.get("overall_score")
                self.completion_times.append(event.timestamp)
                cand["row"] = {
                    "Candidate": f"{cid} · {cand['name'] or 'Unknown'}", "Score": event.data.get("overall_score"),
                    "Classification": event.data.get("classification", ""), "Projects": event.data.get("projects"),
                    "GitHub": event.data.get("github"), "JD Match": event.data.get("jd_alignment"),
                    "Status": cand["status"], "Time (s)": event.data.get("processing_time"),
                }
            elif status == "failed":
                cand["status"] = "Failed"
                self.completion_times.append(event.timestamp)
                if "failed" not in cand["stages"].values():  # stage-level failure was already recorded
                    self.errors.append(f"{cid}: {event.message}")
                for s, st_ in cand["stages"].items():
                    if st_ in ("waiting", "started"):
                        cand["stages"][s] = "skipped"
            elif status == "duplicate":
                cand["status"] = "Duplicate"
                self.warnings.append(f"{cid}: {event.message}")
            self.render(force=True)
            return

        if stage in cand["stages"]:
            prev = cand["stages"][stage]
            if status == "started":
                cand["stages"][stage] = "started"
                cand["stage_started"][stage] = event.timestamp
            elif status == "completed":
                if prev != "warning":
                    cand["stages"][stage] = "completed"
                self.agent_counts[stage] += 1
            elif status == "warning":
                cand["stages"][stage] = "warning"
                cand["warnings"] += 1
                self.warnings.append(f"{cid}: {event.message}")
            elif status == "failed":
                cand["stages"][stage] = "failed"
                self.errors.append(f"{cid}: {event.message}")
                self.agent_counts[stage] += 1
        self.render()

    def heartbeat(self) -> None:
        """Called by the UI loop when no event arrived for a second: keep timers ticking and reassure the user."""
        now = time.time()
        if now - self.last_heartbeat_log >= HEARTBEAT_LOG_EVERY:
            self.last_heartbeat_log = now
            running = self._running_stage_counts()
            if self.jd_status == "running":
                detail = "Gemini is analyzing the job description"
            elif running:
                detail = "still working — " + ", ".join(f"{STAGE_LABELS[s]} ×{n}" for s, n in running.most_common(3))
            else:
                detail = self.batch_message
            self.log.append(f"{time.strftime('%H:%M:%S', time.localtime(now))}  {'BATCH':<9} … {detail}")
        self.render(force=True)

    # ── rendering ────────────────────────────────────────────────────────────
    def _counts(self) -> dict[str, int]:
        c = {"Completed": 0, "Processing": 0, "Queued": 0, "Failed": 0, "Duplicate": 0}
        for cand in self.candidates.values():
            s = cand["status"]
            key = "Completed" if s.startswith("Completed") else s
            c[key] = c.get(key, 0) + 1
        return c

    def _running_stage_counts(self) -> Counter:
        return Counter(s for c in self.candidates.values() if c["status"] == "Processing"
                       for s, st_ in c["stages"].items() if st_ == "started")

    def _eta_text(self, done: int, now: float) -> str:
        remaining = self.total - done
        if remaining <= 0 or not self.first_candidate_at:
            return ""
        if done == 0:
            # No completions yet: candidates finish in waves of `max_concurrent`; a wave is ~1-2 min of LLM calls.
            return "first results in ~1–2 min"
        elapsed = now - self.first_candidate_at
        per_wave = elapsed / max(1, math.ceil(done / self.max_concurrent))
        seconds = per_wave * math.ceil(remaining / self.max_concurrent)
        return f"~{max(1, round(seconds / 60))} min remaining" if seconds >= 60 else "under a minute remaining"

    def _status_text(self, done: int, now: float) -> str:
        if self.jd_status == "running":
            secs = int(now - self.jd_started_at) if self.jd_started_at else 0
            return f"⏳ Analyzing the job description with Gemini · {secs}s"
        running = self._running_stage_counts()
        active = sum(1 for c in self.candidates.values() if c["status"] == "Processing")
        if not running and done >= self.total and self.total:
            return f"⏳ {html.escape(self.batch_message)}"
        if not running:
            return "⏳ Starting candidate processing…"
        parts = [f"{STAGE_LABELS[s]} ×{n}" for s, n in running.most_common(4)]
        text = f"⏳ {active} candidates in progress — " + ", ".join(parts)
        llm_running = sum(n for s, n in running.items() if s in LLM_STAGES)
        if llm_running:
            text += (f" &nbsp;<span class='muted'>· Gemini calls take 10–60 s each and run "
                     f"{config.GEMINI_MAX_CONCURRENT_REQUESTS} at a time, so stages can look idle while they wait</span>")
        eta = self._eta_text(done, now)
        if eta:
            text += f" &nbsp;<span class='muted'>· {eta}</span>"
        return text

    def render(self, force: bool = False) -> None:
        now = time.time()
        if not force and now - self._last_render < 0.35:
            return
        self._last_render = now
        counts = self._counts()
        done = counts["Completed"] + counts["Failed"]
        frac = (done / self.total) if self.total else 1.0

        jd_icon = {"pending": "○", "running": "●", "done": "✓"}[self.jd_status]
        self.header.markdown(
            f"**Job description** {jd_icon} {html.escape(self.jd_source)} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"**Resume batch** ✓ {html.escape(self.zip_summary)} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<span class='muted'>{html.escape(self.batch_message)} · {int(now - self.started_at)}s elapsed</span>",
            unsafe_allow_html=True,
        )
        self.progress.progress(min(max(frac, 0.0), 1.0), text=f"{done} / {self.total} candidates · {frac * 100:.0f}% complete")
        self.status_line.markdown(self._status_text(done, now), unsafe_allow_html=True)

        active = [c for c in self.candidates.values() if c["status"] == "Processing"]
        active.sort(key=lambda c: -c["last_update"])
        if active:
            cur = active[0]
            lines = [f"**{cur['id']}** &nbsp; {html.escape(cur['name'] or cur['file'] or '')}"
                     f" <span class='muted'>· {int(now - cur['started_at'])}s</span>"]
            if len(active) > 1:
                lines.append(f"<span class='muted'>+{len(active) - 1} more in progress: {', '.join(c['id'] for c in active[1:6])}</span>")
            rows = []
            for s in STAGES:
                st_ = cur["stages"][s]
                label = STAGE_LABELS[s]
                if st_ == "started":
                    secs = int(now - cur["stage_started"].get(s, now))
                    label += f" · {secs}s" + (" (Gemini)" if s in LLM_STAGES else " (GitHub API)" if s == "github" else "")
                rows.append(f"<span class='{CSS_CLASS[st_]}'>{SYMBOL[st_]} {label}</span>")
            self.current.markdown("<br>".join(lines) + "<div class='stage-list'>" + "<br>".join(rows) + "</div>",
                                  unsafe_allow_html=True)
        elif done >= self.total and self.total:
            self.current.markdown("<span class='muted'>All candidates processed — finalizing…</span>", unsafe_allow_html=True)
        else:
            self.current.markdown("<span class='muted'>Waiting for the first candidate…</span>", unsafe_allow_html=True)

        running = self._running_stage_counts()
        agent_df = pd.DataFrame({
            "Agent": [STAGE_LABELS[s] for s in STAGES],
            "Running": [running.get(s, 0) for s in STAGES],
            "Done": [f"{self.agent_counts[s]}/{self.total}" for s in STAGES],
            "Progress": [self.agent_counts[s] / self.total if self.total else 0.0 for s in STAGES],
        })
        self.agents.dataframe(
            agent_df, hide_index=True, width="stretch",
            column_config={"Running": st.column_config.NumberColumn(format="%d", width="small"),
                           "Progress": st.column_config.ProgressColumn("Progress", min_value=0, max_value=1, format="%.0f%%")},
        )

        with self.summary.container():
            m = st.columns(6)
            m[0].metric("Completed", counts["Completed"])
            m[1].metric("Processing", counts["Processing"])
            m[2].metric("Queued", counts["Queued"])
            m[3].metric("Failed", counts["Failed"])
            m[4].metric("Duplicates", counts["Duplicate"])
            m[5].metric("Warnings", len(self.warnings))

        rows = [c["row"] for c in self.candidates.values() if c["row"]]
        if rows:
            df = pd.DataFrame(rows).sort_values("Score", ascending=False).reset_index(drop=True)
            df.insert(0, "Rank", range(1, len(df) + 1))
            self.ranking.dataframe(
                df, hide_index=True, width="stretch",
                column_config={
                    "Score": st.column_config.NumberColumn(format="%.1f"), "Projects": st.column_config.NumberColumn(format="%.0f"),
                    "GitHub": st.column_config.NumberColumn(format="%.0f"), "JD Match": st.column_config.NumberColumn(format="%.0f"),
                    "Time (s)": st.column_config.NumberColumn(format="%.0f"),
                },
            )
        else:
            self.ranking.markdown("<span class='muted'>Candidates will appear here as they finish.</span>", unsafe_allow_html=True)

        tail = list(self.log)[-40:]
        self.logbox.markdown("<div class='log-box'>" + html.escape("\n".join(tail) or "…") + "</div>", unsafe_allow_html=True)

        with self.issues.container():
            if self.warnings or self.errors:
                with st.expander(f"⚠ Warnings: {len(self.warnings)} · ✗ Errors: {len(self.errors)}", expanded=False):
                    for e in self.errors[-50:]:
                        st.markdown(f"✗ {html.escape(e)}")
                    for w in self.warnings[-100:]:
                        st.markdown(f"⚠ {html.escape(w)}")
