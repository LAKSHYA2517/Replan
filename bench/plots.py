"""Generate the four benchmark figures from bench/results.jsonl."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
os.environ.setdefault("MPLCONFIGDIR", str(HERE / ".mplconfig"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


RESULTS_PATH = HERE / "results.jsonl"
FIGURES = HERE / "figures"
POLICIES = ("naive", "cancel_all", "replan")
COLORS = {"naive": "#dc2626", "cancel_all": "#6b7280", "replan": "#16a34a"}


def _mean(rows, field):
    values = [float(row[field]) for row in rows if row[field] is not None]
    return sum(values) / len(values) if values else 0.0


def load_results(path=RESULTS_PATH):
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _save(name, figures):
    plt.tight_layout()
    plt.savefig(figures / name, dpi=180)
    plt.close()


def generate(rows, figures=FIGURES):
    figures = Path(figures)
    figures.mkdir(parents=True, exist_ok=True)

    by_policy_offset = defaultdict(list)
    for row in rows:
        by_policy_offset[(row["policy"], row["interrupt_offset"])].append(row)
    plt.figure(figsize=(8, 4.8))
    for policy in POLICIES:
        offsets = sorted(
            offset for candidate, offset in by_policy_offset if candidate == policy
        )
        plt.plot(
            offsets,
            [_mean(by_policy_offset[(policy, offset)], "reuse_ratio") for offset in offsets],
            marker="o",
            label=policy,
            color=COLORS[policy],
        )
    plt.xlabel("Interrupt offset (seconds)")
    plt.ylabel("Mean work reuse ratio")
    plt.title("Work reuse versus interruption timing")
    plt.grid(alpha=0.25)
    plt.legend()
    _save("work_reuse_ratio.png", figures)

    by_policy = {policy: [row for row in rows if row["policy"] == policy] for policy in POLICIES}
    plt.figure(figsize=(7, 4.5))
    plt.bar(
        POLICIES,
        [_mean(by_policy[policy], "wrong_actions") for policy in POLICIES],
        color=[COLORS[policy] for policy in POLICIES],
    )
    plt.ylabel("Mean wrong actions per episode")
    plt.title("Wrong actions by policy")
    _save("wrong_actions_by_policy.png", figures)

    plt.figure(figsize=(7, 4.5))
    plt.bar(
        POLICIES,
        [_mean(by_policy[policy], "tool_calls") for policy in POLICIES],
        color=[COLORS[policy] for policy in POLICIES],
    )
    plt.ylabel("Mean tool calls per episode")
    plt.title("Tool calls by policy")
    _save("tool_calls_by_policy.png", figures)

    freeze_values = [row["freeze_lead_s"] for row in rows if row["freeze_lead_s"] is not None]
    plt.figure(figsize=(7, 4.5))
    if freeze_values:
        plt.hist(freeze_values, bins=20, color=COLORS["replan"], edgecolor="white")
        plt.xlabel("Freeze lead time (seconds)")
        plt.ylabel("Episodes")
    else:
        plt.text(0.5, 0.5, "No freeze lead samples recorded", ha="center", va="center")
        plt.xticks([])
        plt.yticks([])
    plt.title("Freeze lead time distribution")
    _save("freeze_lead_time_histogram.png", figures)


def main():
    rows = load_results()
    generate(rows)
    print(f"wrote four figures to {FIGURES}")


if __name__ == "__main__":
    main()
