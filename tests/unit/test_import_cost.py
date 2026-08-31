import subprocess
import sys

# The adapter registry resolves schemes lazily, so importing maiku must never drag in a
# heavy adapter dependency. This is the regression test for that promise.
FORBIDDEN = ("torch", "transformers", "litellm", "httpx", "typer")


def test_importing_maiku_pulls_in_no_heavy_dependencies():
    code = f"import sys, maiku; print(','.join(m for m in {FORBIDDEN!r} if m in sys.modules))"
    leaked = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert leaked == "", f"import maiku pulled in: {leaked}"
