"""Writing the narrative summary.

Uses a real local LLM when one is reachable and deterministic prose when not, rather than
stubbing a model and calling the result a demo of model integration.
"""

from maiku.runtime.session import Session

LLM_CANDIDATES = ("ollama/qwen3:8b", "ollama/llama3.2", "ollama/qwen2.5")

PROMPT = """Write two sentences summarising this security-camera triage result.
Be plain and factual. Do not add caveats.

{verdict}"""


async def narrate(session: Session, verdict: dict) -> tuple[str, str]:
    """Return (prose, who wrote it)."""
    known = {entry.handle for entry in session.participants()}
    for candidate in LLM_CANDIDATES:
        if candidate in known:
            prose = await session.result(
                candidate, "complete", {"prompt": PROMPT.format(verdict=verdict)}
            )
            return prose.strip(), candidate
    return deterministic(verdict), "arithmetic"


def deterministic(verdict: dict) -> str:
    counts = ", ".join(f"{n} {label}" for label, n in verdict["counts"].items() if n)
    return (
        f"Reviewed {verdict['frames']} frames and found {counts}. "
        f"The clip is best described as '{verdict['verdict']}'."
    )


def markdown(verdict: dict, prose: str, author: str) -> str:
    lines = [
        "# Triage report",
        "",
        prose,
        "",
        f"- frames: {verdict['frames']}",
        f"- verdict: {verdict['verdict']}",
        f"- sequence: {' '.join(verdict['sequence'])}",
        f"- summary written by: {author}",
    ]
    return "\n".join(lines) + "\n"
