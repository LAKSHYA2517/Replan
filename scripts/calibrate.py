"""Prints a confusion matrix and mean confidence per kind for the B5
hypothesis classifier against tests/fixtures/utterances.jsonl. Run by
hand: python scripts/calibrate.py

Calibrated on ~70 of the team's own utterances. Not validated out of
distribution — see LIMITATIONS.md.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from replan.hypothesis import hypothesise

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "utterances.jsonl"


def main() -> None:
    rows = [json.loads(line) for line in FIXTURE_PATH.read_text().splitlines() if line.strip()]

    labels = sorted({r["label"] for r in rows})
    matrix: dict[str, dict[str, int]] = {label: defaultdict(int) for label in labels}
    confidences: dict[str, list[float]] = defaultdict(list)

    for row in rows:
        text, expected = row["text"], row["label"]
        hyp = hypothesise(text, at=0.0)
        predicted = hyp.kind.value.upper() if hyp is not None else "NONE"
        matrix[expected][predicted] += 1
        if hyp is not None:
            confidences[expected].append(hyp.confidence)

    all_predicted = sorted({p for row in matrix.values() for p in row} | set(labels))

    header = "expected\\predicted".ljust(14) + "".join(p.ljust(14) for p in all_predicted)
    print(header)
    correct = 0
    total = 0
    for expected in labels:
        row_counts = matrix[expected]
        line = expected.ljust(14) + "".join(str(row_counts.get(p, 0)).ljust(14) for p in all_predicted)
        print(line)
        correct += row_counts.get(expected, 0)
        total += sum(row_counts.values())

    print()
    print(f"overall accuracy: {correct}/{total} ({100 * correct / total:.1f}%)")
    print()
    print("mean confidence per expected kind (when a hypothesis fired):")
    for expected in labels:
        vals = confidences[expected]
        if vals:
            print(f"  {expected}: {sum(vals) / len(vals):.2f} (n={len(vals)})")
        else:
            print(f"  {expected}: no hypothesis fired")


if __name__ == "__main__":
    main()
