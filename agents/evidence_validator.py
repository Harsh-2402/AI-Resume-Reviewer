"""Deterministic cross-check of resume claims against public evidence. No LLM."""
from concurrent.futures import ThreadPoolExecutor

import config
from agents.skills_analyzer import candidate_skill_pool
from models.analysis import (
    CertificationVerification,
    EvidenceAnalysis,
    LinkCheck,
    ProjectAnalysis,
    SkillEvidence,
    SkillsAnalysis,
    TransferableMatch,
)
from models.candidate import CandidateProfile
from models.github import GitHubAnalysis
from models.jd import JobProfile
from models.state import CandidateState
from scoring.transferable import canonical, classify_match
from services import url_service
from utils.text import dedupe_preserve, github_repo_from_url

_MATCH_ORDER = {"Direct Match": 3, "Strongly Related": 2, "Transferable": 1, "Missing": 0}
_EVIDENCE_UP = {"None": "Weak", "Weak": "Moderate", "Moderate": "Strong", "Strong": "Strong"}


def _skill_evidence(profile: CandidateProfile, github: GitHubAnalysis, jd: JobProfile) -> list[SkillEvidence]:
    project_techs = {canonical(t) for p in profile.projects for t in p.technologies}
    project_techs |= {canonical(t) for i in profile.internships + profile.work_experience for t in i.technologies}
    github_techs = {canonical(t) for t in github.technology_evidence} | {canonical(l) for l in github.languages}
    jd_techs = {canonical(t) for t in jd.all_technologies()}

    out: list[SkillEvidence] = []
    for skill in candidate_skill_pool(profile):
        c = canonical(skill)
        in_projects = c in project_techs or any(classify_match(skill, [t])[0] == "Direct Match" for t in project_techs)
        in_github = github.status == "analyzed" and (
            c in github_techs or any(classify_match(skill, [t])[0] == "Direct Match" for t in github_techs)
        )
        confidence = "High" if (in_projects and in_github) else "Medium" if (in_projects or in_github) else "Low"
        note = ""
        if not in_projects and not in_github:
            note = "Limited public evidence available for this claimed skill."
        elif github.status != "analyzed" and in_projects:
            note = "Supported by project descriptions; no GitHub evidence available."
        out.append(SkillEvidence(
            skill=skill, github_evidence=in_github, project_evidence=in_projects,
            confidence=confidence, note=note,
        ))
    # JD-relevant skills first
    out.sort(key=lambda s: (0 if canonical(s.skill) in jd_techs else 1, s.skill.lower()))
    return out


def _check_links(profile: CandidateProfile) -> list[LinkCheck]:
    targets: list[tuple[str, str]] = []
    for p in profile.projects:
        if p.github_url:
            targets.append((p.github_url, f"github:{p.name}"))
        if p.live_url:
            targets.append((p.live_url, f"live:{p.name}"))
        if p.demo_url:
            targets.append((p.demo_url, f"demo:{p.name}"))
    known = {u for u, _ in targets}
    for url in profile.project_links:
        if url not in known:
            targets.append((url, "link"))
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for url, kind in targets:
        if url not in seen:
            seen.add(url)
            unique.append((url, kind))
    unique = unique[: config.MAX_PROJECT_LINK_CHECKS]
    if not unique:
        return []

    def check(item: tuple[str, str]) -> LinkCheck:
        url, kind = item
        status, detail, _ = url_service.check_url(url)
        return LinkCheck(url=url, kind=kind, status=status, detail=detail)

    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(check, unique))


def _verify_certs(profile: CandidateProfile) -> list[CertificationVerification]:
    out: list[CertificationVerification] = []
    checked = 0
    for cert in profile.certifications:
        if cert.credential_url and checked < config.MAX_CREDENTIAL_CHECKS:
            checked += 1
            status, detail = url_service.verify_credential(
                cert.credential_url, cert_name=cert.name, issuer=cert.issuer, candidate_name=profile.candidate_name,
            )
        elif cert.credential_url or cert.credential_id:
            status, detail = "Not Verifiable", "credential could not be independently verified from available public information"
        else:
            status, detail = "No Verification Information", "no credential URL or ID provided"
        out.append(CertificationVerification(name=cert.name, credential_url=cert.credential_url, status=status, detail=detail))
    return out


def _jd_matrix(jd: JobProfile, profile: CandidateProfile, skills: SkillsAnalysis) -> list[TransferableMatch]:
    # coursework counts as coverage for fundamentals the JD lists as skills (e.g. "Data Structures")
    pool = candidate_skill_pool(profile) + profile.all_coursework()
    llm = {c.jd_skill.strip().lower(): c for c in skills.jd_coverage}
    out: list[TransferableMatch] = []
    for skill in jd.core_skills():
        det_status, det_by = classify_match(skill, pool)
        llm_cov = llm.get(skill.strip().lower())
        if llm_cov and _MATCH_ORDER.get(llm_cov.status, 0) >= _MATCH_ORDER[det_status]:
            out.append(TransferableMatch(jd_skill=skill, status=llm_cov.status, matched_by=llm_cov.covered_by or det_by))
        else:
            out.append(TransferableMatch(jd_skill=skill, status=det_status, matched_by=det_by))
    return out


def _apply_link_evidence(project_analysis: ProjectAnalysis, profile: CandidateProfile, checks: list[LinkCheck], github: GitHubAnalysis) -> list[str]:
    notes: list[str] = []
    status_by_url = {c.url: c.status for c in checks}
    repo_names = {r.name.lower() for r in github.relevant_repos}
    by_name = {a.name.strip().lower(): a for a in project_analysis.assessments}
    for p in profile.projects:
        a = by_name.get(p.name.strip().lower())
        if not a:
            continue
        urls = [u for u in (p.github_url, p.live_url, p.demo_url) if u]
        accessible = [u for u in urls if status_by_url.get(u) == "accessible"]
        broken = [u for u in urls if status_by_url.get(u) in ("broken",)]
        repo = github_repo_from_url(p.github_url) if p.github_url else None
        on_github = bool(repo and repo[1].lower() in repo_names)
        if accessible:
            a.implementation_evidence = _EVIDENCE_UP[a.implementation_evidence]
        if on_github:
            a.implementation_evidence = _EVIDENCE_UP[a.implementation_evidence]
            if a.ownership in ("Unknown", "Weak"):
                a.ownership = "Moderate"
        if accessible or on_github:
            a.comments = (a.comments + " Public link/repository verified.").strip()
        if broken:
            notes.append(f"Project '{p.name}': link no longer reachable ({', '.join(broken)}) — not penalized")
            a.comments = (a.comments + " Link currently unreachable.").strip()
    return notes


def run(state: CandidateState) -> dict:
    profile = CandidateProfile.model_validate(state["profile"])
    jd = JobProfile.model_validate(state["jd_profile"])
    skills = SkillsAnalysis.model_validate(state.get("skills_analysis") or {})
    projects = ProjectAnalysis.model_validate(state.get("project_analysis") or {})
    github = GitHubAnalysis.model_validate(state.get("github_analysis") or {})

    skill_evidence = _skill_evidence(profile, github, jd)
    links = _check_links(profile)
    certs = _verify_certs(profile)
    matrix = _jd_matrix(jd, profile, skills)
    notes = _apply_link_evidence(projects, profile, links, github)

    jd_canon = {canonical(t) for t in jd.all_technologies()}
    relevant = [s for s in skill_evidence if canonical(s.skill) in jd_canon] or skill_evidence
    evidenced = sum(1 for s in relevant if s.project_evidence or s.github_evidence)
    ratio = evidenced / len(relevant) if relevant else 0.0
    has_public = github.status == "analyzed" or any(l.status == "accessible" for l in links)
    if ratio >= 0.6 and has_public:
        overall = "High"
    elif ratio >= 0.3 or (ratio >= 0.6 and not has_public):
        overall = "Medium"
    else:
        overall = "Low"

    unsupported = [s.skill for s in relevant if not (s.project_evidence or s.github_evidence)]
    if unsupported:
        notes.append("Limited public evidence for claimed skills: " + ", ".join(dedupe_preserve(unsupported)[:8]))
    if github.status == "not_provided":
        notes.append("No GitHub profile provided — evidence relies on resume project descriptions and links")
    elif github.status in ("rate_limited", "error", "not_found"):
        notes.append(f"GitHub evidence unavailable ({github.status.replace('_', ' ')})")

    explanation = (
        f"{evidenced}/{len(relevant)} JD-relevant skills are supported by project or GitHub evidence; "
        f"{sum(1 for l in links if l.status == 'accessible')}/{len(links)} project links reachable; "
        f"{sum(1 for c in certs if c.status in ('Verified', 'Evidence Found'))}/{len(certs)} certifications with public evidence."
    )
    evidence = EvidenceAnalysis(
        skill_evidence=skill_evidence,
        technical_evidence_confidence=overall,
        project_link_checks=links,
        certification_verifications=certs,
        jd_skill_matrix=matrix,
        notes=notes,
        explanation=explanation,
    )
    return {"evidence_analysis": evidence.model_dump(), "project_analysis": projects.model_dump()}
