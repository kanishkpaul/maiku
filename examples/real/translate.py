"""IndicTrans2, run inside whichever environment happens to have it.

This file is never imported by maiku. It is invoked as a subprocess through the `cli`
adapter, using a different Python and a different set of installed packages - which is the
point. maiku's own environment has no IndicTransToolkit and does not need one.
"""

import argparse
import json
import sys

MODEL = "ai4bharat/indictrans2-en-indic-1B"


def translate(text: str, target: str) -> str:
    import torch
    from IndicTransToolkit.processor import IndicProcessor
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    processor = IndicProcessor(inference=True)
    tokeniser = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL, trust_remote_code=True)
    model.eval()

    batch = processor.preprocess_batch([text], src_lang="eng_Latn", tgt_lang=target)
    encoded = tokeniser(batch, truncation=True, padding="longest", return_tensors="pt")

    with torch.no_grad():
        generated = model.generate(**encoded, max_length=256, num_beams=5, min_length=0)

    decoded = tokeniser.batch_decode(generated, skip_special_tokens=True)
    return processor.postprocess_batch(decoded, lang=target)[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("text")
    parser.add_argument("target", nargs="?", default="ben_Beng")
    args = parser.parse_args()

    try:
        output = translate(args.text, args.target)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({"text": output, "language": args.target}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
