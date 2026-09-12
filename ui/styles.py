import streamlit as st

CSS = """
<style>
.block-container { padding-top: 1.2rem; }
.stage-list { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.9rem; line-height: 1.7; }
.stage-ok { color: #16a34a; } .stage-run { color: #2563eb; font-weight: 600; } .stage-wait { color: #9ca3af; }
.stage-warn { color: #d97706; } .stage-fail { color: #dc2626; } .stage-skip { color: #9ca3af; }
.log-box { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.78rem; line-height: 1.5;
           background: #0f172a; color: #e2e8f0; padding: 0.75rem 1rem; border-radius: 8px; max-height: 320px; overflow-y: auto; white-space: pre; }
.card { border: 1px solid #e5e7eb; border-radius: 10px; padding: 0.9rem 1.1rem; margin-bottom: 0.75rem; background: #fff; }
.card h4 { margin: 0 0 0.25rem 0; }
.badge { display: inline-block; padding: 0.15rem 0.55rem; border-radius: 999px; font-size: 0.78rem; font-weight: 600; margin-right: 0.35rem; }
.badge-green { background: #dcfce7; color: #166534; } .badge-lime { background: #ecfccb; color: #3f6212; }
.badge-yellow { background: #fef9c3; color: #854d0e; } .badge-orange { background: #ffedd5; color: #9a3412; }
.badge-red { background: #fee2e2; color: #991b1b; } .badge-gray { background: #f3f4f6; color: #374151; }
.muted { color: #6b7280; font-size: 0.85rem; }
.score-big { font-size: 2rem; font-weight: 700; line-height: 1; }
</style>
"""

CLASS_BADGE = {
    "Exceptional Internship Candidate": "badge-green",
    "Strong Internship Candidate": "badge-lime",
    "Good Internship Candidate": "badge-yellow",
    "Potential / Review": "badge-orange",
    "Weak Match": "badge-red",
    "Low Match": "badge-red",
}
REC_BADGE = {
    "Strongly Recommend": "badge-green", "Recommend": "badge-lime", "Consider": "badge-yellow",
    "Needs Review": "badge-orange", "Do Not Prioritize": "badge-red",
}
CONF_BADGE = {"High": "badge-green", "Medium": "badge-yellow", "Low": "badge-orange", "N/A": "badge-gray"}


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def badge(text: str, cls: str) -> str:
    return f'<span class="badge {cls}">{text}</span>'


def score_display(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1f}"


def medal(rank: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")
