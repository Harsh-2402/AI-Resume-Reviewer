from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["High", "Medium", "Low", "N/A"]


class ComponentScore(BaseModel):
    key: str
    label: str
    score: float | None = None  # None → N/A (excluded from the weighted average)
    weight: float = 0.0
    applied_weight: float = 0.0
    explanation: str = ""
    confidence: Confidence = "N/A"

    @property
    def display(self) -> str:
        return "N/A" if self.score is None else f"{self.score:.1f}"


class ScoreCard(BaseModel):
    components: list[ComponentScore] = Field(default_factory=list)
    overall_score: float = 0.0
    classification: str = ""
    recommendation: str = ""
    evidence_confidence: Confidence = "Low"
    explanation: str = ""

    def component(self, key: str) -> ComponentScore | None:
        return next((c for c in self.components if c.key == key), None)

    def score_of(self, key: str) -> float | None:
        comp = self.component(key)
        return comp.score if comp else None

    def as_row(self) -> dict[str, float | None]:
        return {c.key: c.score for c in self.components}
