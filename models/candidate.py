from typing import Optional

from pydantic import BaseModel, Field

from utils.text import github_username_from_url


class TechnicalSkills(BaseModel):
    programming_languages: list[str] = Field(default_factory=list)
    frontend: list[str] = Field(default_factory=list)
    backend: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    databases: list[str] = Field(default_factory=list)
    cloud: list[str] = Field(default_factory=list)
    devops: list[str] = Field(default_factory=list)
    ai_ml: list[str] = Field(default_factory=list)
    data_engineering: list[str] = Field(default_factory=list)
    data_science: list[str] = Field(default_factory=list)
    testing: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    version_control: list[str] = Field(default_factory=list)
    other: list[str] = Field(default_factory=list)

    def all_skills(self) -> list[str]:
        seen: dict[str, str] = {}
        for group in self.model_dump().values():
            for item in group:
                key = item.strip().lower()
                if key and key not in seen:
                    seen[key] = item.strip()
        return list(seen.values())

    def category_map(self) -> dict[str, list[str]]:
        return {k: v for k, v in self.model_dump().items() if v}


class Education(BaseModel):
    degree: str = ""
    major: str = ""
    university: str = ""
    location: str = ""
    start_year: str = ""
    graduation_year: str = ""
    gpa: str = ""
    coursework: list[str] = Field(default_factory=list)
    academic_projects: list[str] = Field(default_factory=list)
    honors: list[str] = Field(default_factory=list)


class Project(BaseModel):
    name: str = ""
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    problem_solved: str = ""
    features: list[str] = Field(default_factory=list)
    role: str = ""
    team_size: str = ""
    duration: str = ""
    github_url: str = ""
    live_url: str = ""
    demo_url: str = ""
    is_academic: bool = False


class Internship(BaseModel):
    company: str = ""
    role: str = ""
    duration: str = ""
    description: str = ""
    technologies: list[str] = Field(default_factory=list)


class Certification(BaseModel):
    name: str = ""
    issuer: str = ""
    issue_date: str = ""
    expiration_date: str = ""
    credential_id: str = ""
    credential_url: str = ""
    technology: str = ""


class Achievement(BaseModel):
    title: str = ""
    category: str = ""
    rank_or_result: str = ""
    organization: str = ""
    date: str = ""
    description: str = ""


class Hackathon(BaseModel):
    name: str = ""
    position: str = ""
    project: str = ""
    technologies: list[str] = Field(default_factory=list)
    award: str = ""
    date: str = ""


class Publication(BaseModel):
    title: str = ""
    venue: str = ""
    year: str = ""
    url: str = ""


class CandidateProfile(BaseModel):
    candidate_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    portfolio_url: str = ""
    other_urls: list[str] = Field(default_factory=list)
    summary: str = ""

    education: list[Education] = Field(default_factory=list)
    coursework: list[str] = Field(default_factory=list)
    technical_skills: TechnicalSkills = Field(default_factory=TechnicalSkills)

    projects: list[Project] = Field(default_factory=list)
    internships: list[Internship] = Field(default_factory=list)
    work_experience: list[Internship] = Field(default_factory=list)

    certifications: list[Certification] = Field(default_factory=list)
    achievements: list[Achievement] = Field(default_factory=list)
    hackathons: list[Hackathon] = Field(default_factory=list)
    competitions: list[Hackathon] = Field(default_factory=list)
    awards: list[str] = Field(default_factory=list)
    publications: list[Publication] = Field(default_factory=list)
    open_source: list[str] = Field(default_factory=list)
    project_links: list[str] = Field(default_factory=list)

    # ── derived convenience accessors ────────────────────────────────────────
    @property
    def primary_education(self) -> Optional[Education]:
        return self.education[0] if self.education else None

    @property
    def degree(self) -> str:
        return self.primary_education.degree if self.primary_education else ""

    @property
    def major(self) -> str:
        return self.primary_education.major if self.primary_education else ""

    @property
    def university(self) -> str:
        return self.primary_education.university if self.primary_education else ""

    @property
    def graduation_year(self) -> str:
        return self.primary_education.graduation_year if self.primary_education else ""

    @property
    def gpa(self) -> str:
        return self.primary_education.gpa if self.primary_education else ""

    @property
    def github_username(self) -> str:
        return github_username_from_url(self.github_url) or ""

    def all_coursework(self) -> list[str]:
        seen: dict[str, str] = {}
        for course in self.coursework + [c for e in self.education for c in e.coursework]:
            key = course.strip().lower()
            if key and key not in seen:
                seen[key] = course.strip()
        return list(seen.values())

    def all_hackathons(self) -> list[Hackathon]:
        return self.hackathons + self.competitions
