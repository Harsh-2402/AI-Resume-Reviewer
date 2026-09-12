from models.result import CandidateResult
from scoring.weights import classification_order
from utils.text import normalize_email, normalize_name, normalize_phone


def _score(result: CandidateResult, key: str) -> float:
    value = result.scorecard.score_of(key)
    return value if value is not None else -1.0


def sort_key(result: CandidateResult) -> tuple:
    """Overall desc, then transparent tie-breakers: projects → technical evidence → education/coursework."""
    edu = max(_score(result, "education"), 0.0) + max(_score(result, "coursework"), 0.0)
    return (
        -result.scorecard.overall_score,
        -_score(result, "projects"),
        -_score(result, "technical_skills"),
        -edu,
        result.candidate_id,
    )


def mark_identity_duplicates(results: list[CandidateResult]) -> list[CandidateResult]:
    """Same email/phone/name across different files → keep the higher-scoring one, mark the rest Duplicate."""
    ranked = sorted([r for r in results if r.is_ranked], key=sort_key)
    seen: dict[str, str] = {}
    for r in ranked:
        keys = []
        if normalize_email(r.profile.email):
            keys.append("email:" + normalize_email(r.profile.email))
        if normalize_phone(r.profile.phone):
            keys.append("phone:" + normalize_phone(r.profile.phone))
        name = normalize_name(r.profile.candidate_name)
        if name and name != "unknown" and len(name) > 4:
            keys.append("name:" + name)
        owner = next((seen[k] for k in keys if k in seen), None)
        if owner:
            r.status = "Duplicate"
            r.duplicate_of = owner
            r.warnings.append(f"Duplicate resume detected (same identity as {owner}); the higher-scoring copy was kept")
        else:
            for k in keys:
                seen[k] = r.candidate_id
    return results


def rank_candidates(results: list[CandidateResult]) -> list[CandidateResult]:
    for r in results:
        r.rank = None
        r.interview_priority = None
    ranked = sorted([r for r in results if r.is_ranked], key=sort_key)
    for position, r in enumerate(ranked, start=1):
        r.rank = position
        r.interview_priority = position
    return ranked


def classification_counts(results: list[CandidateResult]) -> dict[str, int]:
    counts = {label: 0 for label in classification_order()}
    for r in results:
        if r.is_ranked:
            counts[r.scorecard.classification] = counts.get(r.scorecard.classification, 0) + 1
    return counts
