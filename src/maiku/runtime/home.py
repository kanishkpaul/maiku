"""Where maiku keeps its state."""

import os
from pathlib import Path

ENV_VAR = "MAIKU_HOME"
DEFAULT = Path.home() / ".maiku"


def home() -> Path:
    return Path(os.environ.get(ENV_VAR) or DEFAULT).expanduser()
