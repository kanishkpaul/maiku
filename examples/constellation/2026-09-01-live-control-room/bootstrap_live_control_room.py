"""Fetch the small local fixture the live constellation needs on a fresh checkout.

The repository already carries a trained CNN checkpoint. The browser case only needs the
MNIST test images so it can create an honest image artifact and retrieve the independent
label. This command downloads that public test split once; it does not retrain the model.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

def main() -> None:
    from examples.real.cnn import DATA, WEIGHTS

    if not WEIGHTS.exists():
        raise SystemExit(
            f"Missing {WEIGHTS}; run `uv run --extra torch "
            "python -m examples.real.cnn` to train it."
        )
    from torchvision import datasets

    datasets.MNIST(DATA, train=False, download=True)
    print(f"MNIST test fixture ready in {DATA}")


if __name__ == "__main__":
    main()
