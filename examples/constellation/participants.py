"""Small, explicit non-LLM intelligences used by the constellation demonstration."""

from maiku.adapters.decorator import affordance, participant
from maiku.descriptor.enums import Determinism, Kind, LatencyClass, SideEffect


@participant(
    handle="logic/verifier",
    kind=Kind.AGENT,
    name="Rule verifier",
    description="A deterministic evidence checker that never guesses beyond its inputs.",
    tags=["symbolic", "verification", "deterministic"],
)
@affordance(
    determinism=Determinism.DETERMINISTIC,
    latency_class=LatencyClass.INSTANT,
    idempotent=True,
    side_effects=SideEffect.NONE,
)
def rule_verifier(observed: int, expected: int, confidence: float) -> dict:
    """Check whether a classifier result agrees with independently supplied ground truth."""
    return {
        "agrees": observed == expected,
        "claim": f"CNN observed {observed}; independent label is {expected}.",
        "confidence": confidence,
        "decision": "verified" if observed == expected else "disputed",
    }


@participant(
    handle="stats/calibrator",
    kind=Kind.PIPELINE,
    name="Confidence calibrator",
    description="A conservative rule-based confidence interpreter.",
    tags=["statistics", "calibration", "conservative"],
)
@affordance(
    determinism=Determinism.DETERMINISTIC,
    latency_class=LatencyClass.INSTANT,
    idempotent=True,
    side_effects=SideEffect.NONE,
)
def confidence_calibrator(confidence: float, agrees: bool) -> dict:
    """Translate a score and an independent agreement check into a calibrated confidence band."""
    if not agrees:
        band, recommendation = "withhold", "Do not state a conclusion."
    elif confidence >= 0.99:
        band, recommendation = "high", "State the result with the measured confidence."
    elif confidence >= 0.90:
        band, recommendation = "moderate", "State the result but invite review."
    else:
        band, recommendation = "low", "Escalate for review before relying on the result."
    return {"band": band, "recommendation": recommendation}
