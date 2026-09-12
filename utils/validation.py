def validate_weights(weights: dict[str, float]) -> list[str]:
    errors: list[str] = []
    if not weights:
        return ["No scoring weights configured."]
    for key, value in weights.items():
        if value < 0:
            errors.append(f"Weight for '{key}' cannot be negative.")
    if sum(weights.values()) <= 0:
        errors.append("Scoring weights must sum to a positive number.")
    return errors


def validate_batch_inputs(jd_text: str, pdf_count: int, weights: dict[str, float]) -> list[str]:
    errors: list[str] = []
    if not (jd_text or "").strip():
        errors.append("A job description is required (upload a file or paste text).")
    elif len(jd_text.strip()) < 40:
        errors.append("The job description is too short to analyze.")
    if pdf_count <= 0:
        errors.append("The ZIP must contain at least one PDF resume.")
    errors.extend(validate_weights(weights))
    return errors
