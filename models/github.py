from typing import Literal

from pydantic import BaseModel, Field

GitHubStatus = Literal[
    "analyzed", "no_public_repos", "not_provided", "not_found", "rate_limited", "error",
]


class RepoAnalysis(BaseModel):
    name: str = ""
    url: str = ""
    description: str = ""
    primary_language: str = ""
    languages: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    stars: int = 0
    forks: int = 0
    is_fork: bool = False
    created_at: str = ""
    pushed_at: str = ""
    commit_count: int = 0
    has_readme: bool = False
    readme_length: int = 0
    has_tests: bool = False
    has_ci: bool = False
    has_docker: bool = False
    has_license: bool = False
    file_count: int = 0
    matched_technologies: list[str] = Field(default_factory=list)
    relevance: Literal["Direct", "Strongly Related", "Transferable", "Not Relevant"] = "Not Relevant"
    complexity_score: float = 0.0
    quality_score: float = 0.0
    inspected: bool = False


class GitHubScoreBreakdown(BaseModel):
    repository_quality: float = 0.0
    meaningful_activity: float = 0.0
    technology_relevance: float = 0.0
    project_complexity: float = 0.0
    documentation: float = 0.0
    testing_ci: float = 0.0
    recent_activity: float = 0.0


class GitHubAnalysis(BaseModel):
    username: str = ""
    url: str = ""
    status: GitHubStatus = "not_provided"
    public_repos: int = 0
    analyzed_repos: int = 0
    relevant_repos: list[RepoAnalysis] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    technology_evidence: list[str] = Field(default_factory=list)
    last_activity: str = ""
    active_last_6_months: bool = False
    meaningful_commits: int = 0
    total_commits_sampled: int = 0
    breakdown: GitHubScoreBreakdown = Field(default_factory=GitHubScoreBreakdown)
    github_score: float | None = None
    confidence: Literal["High", "Medium", "Low", "N/A"] = "N/A"
    notes: list[str] = Field(default_factory=list)
    explanation: str = ""
