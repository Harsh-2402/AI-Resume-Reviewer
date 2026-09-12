import config


def default_weights() -> dict[str, float]:
    return dict(config.INTERNSHIP_WEIGHTS)


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(v for v in weights.values() if v > 0)
    if total <= 0:
        return default_weights()
    return {k: (v / total if v > 0 else 0.0) for k, v in weights.items()}


def classify(score: float) -> str:
    for threshold, label in config.CLASSIFICATION_THRESHOLDS:
        if score >= threshold:
            return label
    return config.CLASSIFICATION_THRESHOLDS[-1][1]


def recommend(classification: str) -> str:
    return config.RECOMMENDATION_BY_CLASSIFICATION.get(classification, "Needs Review")


def classification_order() -> list[str]:
    return [label for _, label in config.CLASSIFICATION_THRESHOLDS]
