"""The demo is a deliverable, so it is tested like one."""

from examples.triage.participants import LABELS
from examples.triage.report import deterministic, markdown
from examples.triage.run import main


async def test_the_demo_runs_end_to_end(capsys):
    assert await main(interactive=False) == 0
    out = capsys.readouterr().out

    assert "demo/vision" in out
    assert "mcp/fixture" in out
    assert "human/reviewer" in out
    assert "refused: denied" in out
    assert "# Triage report" in out
    assert "failed     demo/vision#publish" in out
    assert "completed  human/reviewer#approve" in out


def test_the_report_reads_like_a_sentence():
    verdict = {
        "frames": 3,
        "counts": {"empty": 1, "motion": 2, "person": 0},
        "verdict": "motion",
        "sequence": ["empty", "motion", "motion"],
    }
    prose = deterministic(verdict)
    assert prose.startswith("Reviewed 3 frames")
    assert "0 person" not in prose

    document = markdown(verdict, prose, "arithmetic")
    assert document.startswith("# Triage report")
    assert "written by: arithmetic" in document


def test_labels_divide_the_frame_evenly():
    from examples.triage.participants import FRAME_BYTES

    assert FRAME_BYTES % len(LABELS) == 0
