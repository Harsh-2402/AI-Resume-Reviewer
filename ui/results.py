"""Post-run views: summary, top candidates, full ranking, candidate detail, comparison, processing log."""
import html

import pandas as pd
import streamlit as st

import config
from models.jd import JobProfile
from models.result import STAGE_LABELS, STAGES, CandidateResult
from scoring.weights import classification_order
from ui.styles import CLASS_BADGE, CONF_BADGE, REC_BADGE, badge, medal, score_display


def _esc(text: str) -> str:
    return html.escape(text or "")


def render_summary(results: list[CandidateResult], stats: dict, report_bytes: bytes, report_name: str) -> None:
    ranked = [r for r in results if r.rank]
    st.markdown("## Evaluation complete")
    counts = stats.get("classifications", {})
    cols = st.columns(len(classification_order()) + 1)
    cols[0].metric("Candidates evaluated", stats.get("ranked", len(ranked)))
    short = {"Exceptional Internship Candidate": "Exceptional", "Strong Internship Candidate": "Strong",
             "Good Internship Candidate": "Good", "Potential / Review": "Potential", "Weak Match": "Weak", "Low Match": "Low"}
    for i, label in enumerate(classification_order(), start=1):
        cols[i].metric(short.get(label, label), counts.get(label, 0))
    extra = []
    if stats.get("failed"):
        extra.append(f"✗ {stats['failed']} failed")
    if stats.get("duplicates"):
        extra.append(f"⧉ {stats['duplicates']} duplicates")
    if stats.get("with_warnings"):
        extra.append(f"⚠ {stats['with_warnings']} with warnings")
    if extra:
        st.caption(" · ".join(extra))

    if ranked:
        top = ranked[:3]
        st.markdown(" &nbsp;·&nbsp; ".join(f"{medal(r.rank)} **{_esc(r.name)}** — {r.overall_score:.1f}" for r in top), unsafe_allow_html=True)
    st.download_button("⬇️ Download Excel Report", data=report_bytes, file_name=report_name,
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")


def _candidate_card(r: CandidateResult) -> None:
    s, e = r.scorecard, r.evaluation
    strengths = "".join(f"<li>{_esc(x)}</li>" for x in e.strengths[:6]) or "<li>See detail view</li>"
    st.markdown(
        f"""<div class="card">
<h4>{medal(r.rank)} {_esc(r.name)} <span class="muted">{r.candidate_id}</span></h4>
<span class="score-big">{s.overall_score:.1f}</span>&nbsp;
{badge(s.classification, CLASS_BADGE.get(s.classification, 'badge-gray'))}{badge(s.recommendation, REC_BADGE.get(s.recommendation, 'badge-gray'))}{badge('Evidence: ' + s.evidence_confidence, CONF_BADGE.get(s.evidence_confidence, 'badge-gray'))}
<div class="muted">{_esc(r.profile.degree)}{' · ' + _esc(r.profile.university) if r.profile.university else ''}{' · ' + _esc(r.profile.graduation_year) if r.profile.graduation_year else ''}</div>
<p><b>Key strengths</b></p><ul>{strengths}</ul>
<p><b>Top strength:</b> {_esc(e.top_strength)}<br><b>Primary concern:</b> {_esc(e.primary_concern)}</p>
</div>""",
        unsafe_allow_html=True,
    )


def render_top_candidates(results: list[CandidateResult]) -> None:
    ranked = [r for r in results if r.rank]
    if not ranked:
        st.info("No candidates were ranked.")
        return
    n = st.radio("Show", [5, 10], horizontal=True, format_func=lambda x: f"Top {x}", key="top_n")
    left, right = st.columns(2)
    for i, r in enumerate(ranked[:n]):
        with (left if i % 2 == 0 else right):
            _candidate_card(r)


def ranking_dataframe(results: list[CandidateResult]) -> pd.DataFrame:
    rows = []
    for r in results:
        if not r.rank:
            continue
        s = r.scorecard
        rows.append({
            "Rank": r.rank, "ID": r.candidate_id, "Candidate": r.name, "Overall": s.overall_score,
            "Classification": s.classification, "Recommendation": s.recommendation,
            "Education": s.score_of("education"), "Coursework": s.score_of("coursework"),
            "Skills": s.score_of("technical_skills"), "Projects": s.score_of("projects"), "GitHub": s.score_of("github"),
            "Certs": s.score_of("certifications"), "Achievements": s.score_of("achievements"),
            "JD Match": s.score_of("jd_alignment"), "Learning": s.score_of("learning_potential"),
            "Evidence": s.evidence_confidence, "Warnings": len(r.warnings),
        })
    return pd.DataFrame(rows)


def render_ranking_table(results: list[CandidateResult]) -> None:
    df = ranking_dataframe(results)
    if df.empty:
        st.info("No ranked candidates.")
        return
    num = {c: st.column_config.NumberColumn(format="%.1f") for c in
           ["Overall", "Education", "Coursework", "Skills", "Projects", "GitHub", "Certs", "Achievements", "JD Match", "Learning"]}
    st.dataframe(df, hide_index=True, width="stretch", column_config=num, height=min(600, 60 + 35 * len(df)))


def _list(items: list[str], empty: str = "N/A") -> None:
    if items:
        for x in items:
            st.markdown(f"- {x}")
    else:
        st.caption(empty)


def render_candidate_detail(results: list[CandidateResult], jd: JobProfile) -> None:
    options = [r for r in results if r.rank] + [r for r in results if not r.rank]
    if not options:
        st.info("Nothing to show.")
        return
    labels = {r.candidate_id: f"{'#' + str(r.rank) if r.rank else r.status} · {r.candidate_id} · {r.name}" for r in options}
    cid = st.selectbox("Candidate", [r.candidate_id for r in options], format_func=lambda c: labels[c], key="detail_select")
    r = next(x for x in options if x.candidate_id == cid)
    p, s, e = r.profile, r.scorecard, r.evaluation

    st.markdown(f"### {_esc(r.name)} <span class='muted'>{r.candidate_id} · {_esc(r.resume_file)}</span>", unsafe_allow_html=True)
    if r.status in ("Failed", "Duplicate"):
        st.error(f"Status: {r.status}" + (f" (of {r.duplicate_of})" if r.duplicate_of else ""))
        for err in r.errors:
            st.markdown(f"✗ {err}")
        for w in r.warnings:
            st.markdown(f"⚠ {w}")
        return

    m = st.columns(5)
    m[0].metric("Overall", f"{s.overall_score:.1f}")
    m[1].metric("Rank", f"#{r.rank}")
    m[2].markdown(badge(s.classification, CLASS_BADGE.get(s.classification, "badge-gray")), unsafe_allow_html=True)
    m[3].markdown(badge(s.recommendation, REC_BADGE.get(s.recommendation, "badge-gray")), unsafe_allow_html=True)
    m[4].markdown(badge("Evidence: " + s.evidence_confidence, CONF_BADGE.get(s.evidence_confidence, "badge-gray")), unsafe_allow_html=True)
    if r.warnings:
        with st.expander(f"⚠ {len(r.warnings)} warning(s)"):
            for w in r.warnings:
                st.markdown(f"- {w}")

    st.markdown("#### Score breakdown")
    comp_df = pd.DataFrame([{
        "Component": c.label, "Score": c.score, "Weight": f"{c.applied_weight:.0%}" if c.applied_weight else "N/A",
        "Confidence": c.confidence, "Explanation": c.explanation,
    } for c in s.components])
    st.dataframe(comp_df, hide_index=True, width="stretch",
                 column_config={"Score": st.column_config.NumberColumn(format="%.1f"),
                                "Explanation": st.column_config.TextColumn(width="large")})
    st.caption(s.explanation)

    tabs = st.tabs(["Profile & Education", "Skills", "Projects", "GitHub", "Certifications & Achievements", "Evidence", "Interview"])
    with tabs[0]:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Email:** {_esc(p.email) or 'N/A'}  \n**Phone:** {_esc(p.phone) or 'N/A'}  \n**Location:** {_esc(p.location) or 'N/A'}")
            links = [f"[LinkedIn]({p.linkedin_url})" if p.linkedin_url else "", f"[GitHub]({p.github_url})" if p.github_url else "",
                     f"[Portfolio]({p.portfolio_url})" if p.portfolio_url else ""]
            st.markdown(" · ".join(l for l in links if l) or "No links")
            if p.summary:
                st.caption(p.summary)
        with c2:
            for ed in p.education:
                st.markdown(f"**{_esc(ed.degree)}** {('in ' + _esc(ed.major)) if ed.major else ''}  \n{_esc(ed.university)} · {_esc(ed.graduation_year) or 'year N/A'} · GPA {_esc(ed.gpa) or 'Not Provided'}")
                if ed.honors:
                    st.markdown("Honors: " + ", ".join(ed.honors))
            if not p.education:
                st.caption("No education information")
        st.markdown("**Coursework**")
        cm = {m.course: m.relevance for m in r.education_analysis.coursework_matches}
        st.markdown(", ".join(f"{c} ({cm.get(c, '?')})" for c in p.all_coursework()) or "N/A")
        st.markdown("**Education highlights**")
        _list(r.education_analysis.highlights)
        if r.education_analysis.concerns:
            st.markdown("**Concerns**")
            _list(r.education_analysis.concerns)
        st.caption(r.education_analysis.explanation)
        if p.internships:
            st.markdown("**Internships**")
            for i in p.internships:
                st.markdown(f"- {_esc(i.role)} @ {_esc(i.company)} ({_esc(i.duration)}) — {', '.join(i.technologies)}")
    with tabs[1]:
        matrix = pd.DataFrame([{"JD Skill": m.jd_skill, "Status": m.status, "Covered by": m.matched_by} for m in r.evidence_analysis.jd_skill_matrix])
        if not matrix.empty:
            st.dataframe(matrix, hide_index=True, width="stretch")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Strengths**")
            _list(r.skills_analysis.strengths)
        with c2:
            st.markdown("**Gaps**")
            _list(r.skills_analysis.gaps, "No significant gaps")
        with st.expander("All skills by category"):
            for cat, items in p.technical_skills.category_map().items():
                st.markdown(f"**{cat.replace('_', ' ').title()}:** {', '.join(items)}")
        st.caption(r.skills_analysis.explanation)
    with tabs[2]:
        assess = {a.name.strip().lower(): a for a in r.project_analysis.assessments}
        for pr in p.projects:
            a = assess.get(pr.name.strip().lower())
            with st.expander(f"{pr.name} — {a.depth if a else 'unassessed'} · {a.jd_relevance if a else ''}", expanded=False):
                st.markdown(pr.description or "_No description_")
                st.markdown(f"**Technologies:** {', '.join(pr.technologies) or 'N/A'}  \n**Role:** {pr.role or 'N/A'} · **Team:** {pr.team_size or 'N/A'} · **Duration:** {pr.duration or 'N/A'}")
                links = [f"[GitHub]({pr.github_url})" if pr.github_url else "", f"[Live]({pr.live_url})" if pr.live_url else "", f"[Demo]({pr.demo_url})" if pr.demo_url else ""]
                if any(links):
                    st.markdown(" · ".join(l for l in links if l))
                if a:
                    st.markdown(f"**Complexity:** {a.complexity}/5 · **Ownership:** {a.ownership} · **Implementation evidence:** {a.implementation_evidence}")
                    _list(a.technical_highlights)
                    st.caption(a.comments)
        if not p.projects:
            st.caption("No projects found")
        st.markdown(f"**Progression:** {r.project_analysis.progression}")
        st.caption(r.project_analysis.explanation)
    with tabs[3]:
        g = r.github_analysis
        st.markdown(f"**Status:** {g.status.replace('_', ' ')} · **Score:** {score_display(g.github_score)} · **Confidence:** {g.confidence}")
        if g.url:
            st.markdown(f"[{g.url}]({g.url})")
        if g.status == "analyzed":
            b = g.breakdown
            st.dataframe(pd.DataFrame([{
                "Repo quality": b.repository_quality, "Activity": b.meaningful_activity, "Tech relevance": b.technology_relevance,
                "Complexity": b.project_complexity, "Docs": b.documentation, "Tests/CI": b.testing_ci, "Recency": b.recent_activity,
            }]), hide_index=True, width="stretch")
            st.markdown(f"**Languages:** {', '.join(g.languages) or 'N/A'}  \n**Technology evidence:** {', '.join(g.technology_evidence) or 'none of the JD technologies'}  \n**Last activity:** {g.last_activity[:10] or 'N/A'} · **Meaningful commits sampled:** {g.meaningful_commits}")
            repos = pd.DataFrame([{
                "Repository": x.name, "Relevance": x.relevance, "Language": x.primary_language, "Commits": x.commit_count,
                "README": "Yes" if x.has_readme else "No", "Tests": "Yes" if x.has_tests else "No", "CI": "Yes" if x.has_ci else "No",
                "Docker": "Yes" if x.has_docker else "No", "Quality": x.quality_score, "Complexity": x.complexity_score, "URL": x.url,
            } for x in g.relevant_repos])
            if not repos.empty:
                st.dataframe(repos, hide_index=True, width="stretch", column_config={"URL": st.column_config.LinkColumn()})
        for n in g.notes:
            st.caption(n)
        st.caption(g.explanation)
    with tabs[4]:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Certifications**")
            verify = {v.name: v for v in r.evidence_analysis.certification_verifications}
            for a in r.certification_analysis.assessments:
                v = verify.get(a.name)
                st.markdown(f"- **{a.name}** ({a.cert_type}, relevance {a.jd_relevance}) — {v.status if v else 'No Verification Information'}")
            if not r.certification_analysis.assessments:
                st.caption("None listed")
        with c2:
            st.markdown("**Achievements & hackathons**")
            for a in r.achievement_analysis.assessments:
                st.markdown(f"- **{a.title}** ({a.category}, {a.significance}) {a.rank_or_result}")
            if not r.achievement_analysis.assessments:
                st.caption("None listed")
            if r.achievement_analysis.learning_signals:
                st.markdown("**Learning signals**")
                _list(r.achievement_analysis.learning_signals)
    with tabs[5]:
        ev = r.evidence_analysis
        st.markdown(f"**Technical evidence confidence:** {ev.technical_evidence_confidence}")
        st.caption(ev.explanation)
        se = pd.DataFrame([{"Skill": x.skill, "Projects": "✓" if x.project_evidence else "", "GitHub": "✓" if x.github_evidence else "",
                            "Confidence": x.confidence, "Note": x.note} for x in ev.skill_evidence])
        if not se.empty:
            st.dataframe(se, hide_index=True, width="stretch", height=min(400, 60 + 35 * len(se)))
        if ev.project_link_checks:
            st.markdown("**Link checks**")
            for l in ev.project_link_checks:
                st.markdown(f"- {l.kind}: [{l.url}]({l.url}) — {l.status} ({l.detail})")
        for n in ev.notes:
            st.caption(n)
    with tabs[6]:
        st.markdown(f"**Why interview:** {_esc(e.why_interview)}")
        st.markdown(f"**Evidence summary:** {_esc(e.evidence_summary)}")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Strengths**")
            _list(e.strengths)
            st.markdown("**Technical areas to test**")
            _list(e.technical_areas_to_test)
            st.markdown("**Project areas to discuss**")
            _list(e.project_areas_to_discuss)
        with c2:
            st.markdown("**Concerns**")
            _list(e.concerns, "None identified")
            st.markdown("**GitHub areas to discuss**")
            _list(e.github_areas_to_discuss)
            st.markdown("**Certification areas to discuss**")
            _list(e.certification_areas_to_discuss)
        st.markdown("**Suggested interview questions**")
        for i, q in enumerate(e.interview_questions, 1):
            st.markdown(f"{i}. {q}")


def render_comparison(results: list[CandidateResult]) -> None:
    ranked = [r for r in results if r.rank]
    if len(ranked) < 2:
        st.info("At least two ranked candidates are needed to compare.")
        return
    labels = {r.candidate_id: f"#{r.rank} {r.name}" for r in ranked}
    default = [r.candidate_id for r in ranked[:3]]
    chosen = st.multiselect("Candidates to compare", [r.candidate_id for r in ranked], default=default,
                            format_func=lambda c: labels[c], key="compare_select")
    if not chosen:
        return
    keys = list(config.COMPONENT_LABELS.keys())
    rows = []
    for key, label in [("overall", "Overall Score")] + [(k, config.COMPONENT_LABELS[k]) for k in keys]:
        row = {"Metric": label}
        for cid in chosen:
            r = next(x for x in ranked if x.candidate_id == cid)
            row[labels[cid]] = r.scorecard.overall_score if key == "overall" else r.scorecard.score_of(key)
        rows.append(row)
    for label, attr in [("Classification", "classification"), ("Recommendation", "recommendation"), ("Evidence confidence", "evidence_confidence")]:
        rows.append({"Metric": label, **{labels[c]: getattr(next(x for x in ranked if x.candidate_id == c).scorecard, attr) for c in chosen}})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def render_processing_log(results: list[CandidateResult], zip_summary: str, skipped: list[tuple[str, str]]) -> None:
    st.caption(zip_summary)
    if skipped:
        with st.expander(f"Skipped files ({len(skipped)})"):
            for name, reason in skipped:
                st.markdown(f"- `{name}` — {reason}")
    sym = {"completed": "✓", "warning": "⚠", "failed": "✗", "skipped": "–", "not run": "○"}
    rows = []
    for r in sorted(results, key=lambda x: x.candidate_id):
        row = {"ID": r.candidate_id, "File": r.resume_file, "Name": r.name, "Status": r.status}
        for s in STAGES:
            row[STAGE_LABELS[s].split()[0]] = sym.get(r.stage_status.get(s, "not run"), "?")
        row["Warnings"] = len(r.warnings)
        row["Errors"] = len(r.errors)
        row["Time (s)"] = r.processing_time
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    issues = [(r.candidate_id, "✗", e) for r in results for e in r.errors] + [(r.candidate_id, "⚠", w) for r in results for w in r.warnings]
    if issues:
        with st.expander(f"All warnings and errors ({len(issues)})"):
            for cid, icon, msg in issues:
                st.markdown(f"{icon} **{cid}** {msg}")


def render_job_profile(jd: JobProfile, settings: dict) -> None:
    st.markdown(f"### {_esc(jd.job_title) or 'Job profile'}")
    if jd.summary:
        st.markdown(jd.summary)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Required skills**")
        _list(jd.required_skills)
        st.markdown("**Preferred skills**")
        _list(jd.preferred_skills)
        st.markdown("**Education**")
        _list(jd.education_requirements + jd.preferred_education)
    with c2:
        st.markdown("**Relevant coursework**")
        _list(jd.relevant_coursework)
        st.markdown("**Project expectations**")
        _list(jd.project_expectations)
        st.markdown("**Responsibilities**")
        _list(jd.responsibilities[:8])
    weights = {**config.INTERNSHIP_WEIGHTS, **(settings.get("weights") or {})}
    total = sum(weights.values()) or 1
    st.markdown("**Scoring weights used**")
    st.dataframe(pd.DataFrame([{"Component": config.COMPONENT_LABELS[k], "Weight": f"{v / total:.0%}"} for k, v in weights.items()]),
                 hide_index=True, width="stretch")
