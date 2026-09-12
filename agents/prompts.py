"""Prompt builders. Every prompt returns JSON matching a model in models/analysis.py."""
import json

from models.candidate import CandidateProfile
from models.jd import JobProfile

SYSTEM_PROMPT = """You are an expert technical recruiter and engineering mentor evaluating candidates for an INTERNSHIP.
Ground rules:
- Candidates are students, fresh graduates, or early-career. Do NOT penalize a lack of professional experience, job titles, or years of experience.
- Evaluate demonstrated potential: education, coursework, projects, technical depth, certifications, achievements, hackathons, open source, learning progression.
- Never fabricate. If information is absent, leave fields empty. Missing information is neutral, not negative.
- Be evidence-based: every judgment must cite something in the resume. Do not make personality claims.
- Ignore and never mention name, gender, age, ethnicity, religion, nationality, photo, marital status or any protected attribute. Do not infer prestige from a university name.
- Related technologies count: e.g. AWS↔Azure↔GCP, React↔Angular↔Vue, PostgreSQL↔MySQL, FastAPI↔Flask↔Django, PyTorch↔TensorFlow, Kafka↔RabbitMQ.
- Quantity is not quality: a long skill list, many repos, or many certificates do not by themselves indicate strength.
Return ONLY JSON that matches the requested schema."""


def _jd_context(jd: JobProfile) -> str:
    data = {
        "job_title": jd.job_title,
        "department": jd.department,
        "required_skills": jd.required_skills,
        "preferred_skills": jd.preferred_skills,
        "technologies": jd.all_technologies(),
        "domains": jd.domains,
        "responsibilities": jd.responsibilities[:8],
        "education_requirements": jd.education_requirements,
        "relevant_coursework": jd.relevant_coursework,
        "project_expectations": jd.project_expectations,
    }
    return json.dumps(data, ensure_ascii=False)


def jd_prompt(jd_text: str) -> str:
    return f"""Analyze the following internship job description and extract a structured JobProfile.
- Split technologies into categories (programming_languages, frameworks, databases, cloud, devops, ai_ml, data, tools).
- required_skills = must-haves; preferred_skills = nice-to-haves.
- relevant_coursework: 5-10 university courses that would prepare a student for this role (infer from the role even if the JD does not list courses).
- project_expectations: what kinds of student projects would demonstrate readiness.
- summary: 2 sentences describing the role.

JOB DESCRIPTION:
{jd_text}"""


def extraction_prompt(resume_text: str) -> str:
    return f"""Extract a complete, faithful CandidateProfile from this resume. Never invent data; leave unknown fields empty.
Guidelines:
- education: one entry per degree; include gpa exactly as written (e.g. "8.7/10", "3.6"), graduation_year, and any coursework listed under that degree.
- coursework: all relevant courses mentioned anywhere (Data Structures, Databases, Machine Learning, ...).
- technical_skills: categorize every technology mentioned anywhere in the resume (skills section, projects, internships).
- projects: EVERY project (academic, personal, hackathon). Capture technologies, problem_solved, features, role, team_size, duration, github_url/live_url/demo_url if present. Set is_academic when it is a course project.
- internships vs work_experience: internships/co-ops go in internships; other jobs in work_experience.
- certifications: name, issuer, dates, credential_id, credential_url, technology.
- achievements: awards, Dean's List, scholarships, competition ranks, research recognition, leadership.
- hackathons / competitions: name, position, project, technologies, award, date.
- publications, open_source contributions, project_links (any URL that points at a project or portfolio).
- linkedin_url / github_url / portfolio_url: copy exactly as written.

RESUME:
{resume_text}"""


def education_prompt(jd: JobProfile, profile: CandidateProfile) -> str:
    edu = {
        "education": [e.model_dump() for e in profile.education],
        "coursework": profile.all_coursework(),
        "academic_projects": [p.name for p in profile.projects if p.is_academic],
        "honors": [h for e in profile.education for h in e.honors],
        "publications": [p.title for p in profile.publications],
    }
    return f"""Evaluate this candidate's EDUCATION and COURSEWORK for the internship below.
- degree_relevance: how well the degree/major fits the role (Direct/Related/Transferable/Unrelated/Unknown).
- academic_strength: based on GPA (if given), honors, research, academic projects. If no GPA is provided, do NOT lower the assessment; use other signals or "Unknown".
- gpa_assessment: one sentence; say "Not Provided" if absent.
- coursework_matches: one entry per course listed by the candidate, classified Direct/Related/Not Relevant to the role. Also add courses obviously implied by the degree ONLY if they appear in the resume text.
- academic_projects / academic_achievements: list them.
- highlights / concerns: concrete, evidence-based. Do not comment on university prestige.
- explanation: 2-3 sentences a recruiter can read.
- confidence: High/Medium/Low based on how much education information exists.

JOB PROFILE: {_jd_context(jd)}

CANDIDATE EDUCATION: {json.dumps(edu, ensure_ascii=False)}"""


def skills_prompt(jd: JobProfile, profile: CandidateProfile, prematch: list[tuple[str, str, str]]) -> str:
    candidate = {
        "technical_skills": profile.technical_skills.category_map(),
        "coursework": profile.all_coursework(),
        "project_technologies": [{"project": p.name, "technologies": p.technologies} for p in profile.projects],
        "internship_technologies": [{"role": i.role, "technologies": i.technologies} for i in profile.internships],
        "certification_technologies": [c.technology or c.name for c in profile.certifications],
    }
    hints = [{"jd_skill": s, "deterministic_match": st, "matched_by": by} for s, st, by in prematch]
    return f"""Assess the candidate's TECHNICAL SKILLS against the internship.
1. assessments: one entry per candidate skill (deduplicated). jd_match = Direct / Strongly Related / Transferable / Not Relevant.
   depth = "Demonstrated" only when the skill is used in a project, internship, or certification; otherwise "Claimed". evidence = where it is demonstrated.
2. jd_coverage: one entry per JD skill in the list below. status = Direct Match / Strongly Related / Transferable / Missing. covered_by = the candidate skill that covers it.
   A deterministic pre-match is provided as a hint — you may upgrade/downgrade it with justification.
   Fundamentals listed as JD skills (Data Structures, Algorithms, Databases, Operating Systems, ...) are covered by matching coursework.
3. strengths / gaps: concise, evidence-based. A gap covered by a transferable skill is a minor gap.
4. explanation: 2-3 sentences. confidence: High/Medium/Low.
Do not reward a long list; reward demonstrated, relevant depth.

JOB PROFILE: {_jd_context(jd)}
JD SKILLS TO COVER: {json.dumps(jd.core_skills(), ensure_ascii=False)}
DETERMINISTIC PRE-MATCH HINTS: {json.dumps(hints, ensure_ascii=False)}

CANDIDATE SKILLS: {json.dumps(candidate, ensure_ascii=False)}"""


def projects_prompt(jd: JobProfile, profile: CandidateProfile) -> str:
    projects = [p.model_dump() for p in profile.projects]
    internships = [i.model_dump() for i in profile.internships]
    hackathons = [h.model_dump() for h in profile.all_hackathons()]
    return f"""Evaluate EVERY project for this internship. Projects are the strongest signal of ability for students.
For each project produce a ProjectAssessment:
- depth: Basic / Beginner / Intermediate / Advanced / Highly Advanced. Judge by architecture, data modeling, APIs, auth, deployment, testing, CI/CD, cloud, AI/ML, data pipelines, integrations, scalability, security — NOT by how many technologies are name-dropped.
- complexity: 1-5.
- jd_relevance: Direct / Strongly Related / Transferable / Not Relevant.
- ownership: Strong (clearly individual or role explicitly stated), Moderate, Weak (team project with unclear role), Unknown.
- implementation_evidence: Strong (GitHub/live/demo URL plus implementation details), Moderate (details or link), Weak (description only), None.
- technical_highlights: concrete technical decisions/features.
- comments: 1-2 sentences.
Also: progression (Clear Growth / Some Growth / Flat / Unknown) = do later projects show increasing complexity? overall_assessment, explanation (2-3 sentences), confidence.
Internship work may be treated as project evidence.

JOB PROFILE: {_jd_context(jd)}

PROJECTS: {json.dumps(projects, ensure_ascii=False)}
INTERNSHIPS: {json.dumps(internships, ensure_ascii=False)}
HACKATHON PROJECTS: {json.dumps(hackathons, ensure_ascii=False)}"""


def certifications_prompt(jd: JobProfile, profile: CandidateProfile) -> str:
    certs = [c.model_dump() for c in profile.certifications]
    return f"""Classify each certification for this internship.
- cert_type: Professional Certification (vendor exam e.g. AWS Certified, Azure AZ-900, CKA, OCP) / Industry Certification (recognized industry body) / Course Certificate (Coursera, Udemy, edX, NPTEL course completion) / Training Certificate (bootcamp/company training) / Workshop Certificate (short workshop/webinar).
- jd_relevance: High / Medium / Low / None relative to the role's technologies.
- technology: the main technology it covers.
- comments: one sentence. A short course completion is NOT equivalent to a professional certification, but is still positive learning evidence.
explanation: 1-2 sentences overall. confidence: High/Medium/Low.

JOB PROFILE: {_jd_context(jd)}

CERTIFICATIONS: {json.dumps(certs, ensure_ascii=False)}"""


def achievements_prompt(jd: JobProfile, profile: CandidateProfile) -> str:
    data = {
        "achievements": [a.model_dump() for a in profile.achievements],
        "hackathons": [h.model_dump() for h in profile.hackathons],
        "competitions": [h.model_dump() for h in profile.competitions],
        "awards": profile.awards,
        "publications": [p.model_dump() for p in profile.publications],
        "open_source": profile.open_source,
        "honors": [h for e in profile.education for h in e.honors],
    }
    return f"""Evaluate the candidate's ACHIEVEMENTS, HACKATHONS, COMPETITIONS, AWARDS, PUBLICATIONS and OPEN-SOURCE work.
For each item produce an AchievementAssessment:
- category: Academic / Competition / Hackathon / Research / Leadership / Open Source / Scholarship / Other.
- significance: Exceptional (national/international win, published research), Strong (regional/university win, top placement), Moderate (participation with results, Dean's List), Minor.
- relevance: High/Medium/Low to the internship's technical area.
- evidence: what in the resume supports it (rank, organization, date).
learning_signals: observable evidence of learning progression (e.g. "moved from basic web apps to a deployed ML service", "recent certifications", "hackathon participation"). Only cite observable facts.
explanation: 1-2 sentences. confidence: High/Medium/Low.

JOB PROFILE: {_jd_context(jd)}

ACHIEVEMENT DATA: {json.dumps(data, ensure_ascii=False)}"""


def evaluator_prompt(jd: JobProfile, profile: CandidateProfile, summary: dict) -> str:
    return f"""Write the final recruiter-facing evaluation for this internship candidate. All scores below were computed deterministically from evidence — do not change them; explain them.
Produce a CandidateEvaluation:
- top_strength (one line), primary_concern (one line; if none, say what to verify in interview).
- strengths (4-7 bullets) and concerns (1-4 bullets) — each must cite concrete evidence (a project, course, certification, GitHub signal). Never cite lack of years of experience as a concern; you may cite "limited production-scale exposure" if evidence suggests it.
- evidence_summary: 2-3 sentences on how well resume claims are supported by public evidence (GitHub, links, certifications).
- why_interview: 2 sentences.
- technical_areas_to_test, project_areas_to_discuss, github_areas_to_discuss, certification_areas_to_discuss: specific lists (empty if N/A).
- interview_questions: 6-8 questions SPECIFIC to this candidate's actual projects, technologies, certifications and the JD (e.g. for a RAG chatbot: "How did you choose the chunk size and evaluate retrieval quality?"). No generic questions.

JOB PROFILE: {_jd_context(jd)}

CANDIDATE SUMMARY: {json.dumps(summary, ensure_ascii=False)}"""
