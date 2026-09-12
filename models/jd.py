from pydantic import BaseModel, Field


class JobProfile(BaseModel):
    job_title: str = ""
    department: str = ""
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    programming_languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    databases: list[str] = Field(default_factory=list)
    cloud: list[str] = Field(default_factory=list)
    devops: list[str] = Field(default_factory=list)
    ai_ml: list[str] = Field(default_factory=list)
    data: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    education_requirements: list[str] = Field(default_factory=list)
    preferred_education: list[str] = Field(default_factory=list)
    relevant_coursework: list[str] = Field(default_factory=list)
    project_expectations: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    other_requirements: list[str] = Field(default_factory=list)
    summary: str = ""

    def all_technologies(self) -> list[str]:
        seen: dict[str, str] = {}
        for group in (
            self.required_skills, self.preferred_skills, self.programming_languages,
            self.frameworks, self.databases, self.cloud, self.devops, self.ai_ml,
            self.data, self.tools,
        ):
            for item in group:
                key = item.strip().lower()
                if key and key not in seen:
                    seen[key] = item.strip()
        return list(seen.values())

    def core_skills(self) -> list[str]:
        """Required skills first, then the categorized technologies (deduped)."""
        seen: dict[str, str] = {}
        for item in self.required_skills + self.all_technologies():
            key = item.strip().lower()
            if key and key not in seen:
                seen[key] = item.strip()
        return list(seen.values())
