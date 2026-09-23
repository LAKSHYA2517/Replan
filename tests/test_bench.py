import json
import os
import shutil
from pathlib import Path

import pytest

from bench.plots import generate
from bench.run import run_sweep
from bench.scenarios import SCENARIOS


ROW_FIELDS = {
    "scenario",
    "interrupt_offset",
    "latency_profile",
    "chaos",
    "seed",
    "policy",
    "stale_commits",
    "wrong_actions",
    "dangling_effects",
    "reuse_ratio",
    "tool_calls",
    "wasted_tool_s",
    "spec_hit_rate",
    "spec_waste_ratio",
    "freeze_lead_s",
    "cancel_latency_s",
    "ttfvr_s",
    "trace_coverage",
    "replay_ok",
}


@pytest.fixture
def bench_temp(request):
    path = Path("tests/.tmp_bench") / f"{request.node.name}-{os.getpid()}"
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def test_four_scenarios_have_configurable_late_results():
    assert len(SCENARIOS) == 4
    for build in SCENARIOS.values():
        scenario = build(0.6)
        assert scenario["interruption"]["at"] == 0.6
        assert scenario["late_result"]["at"] > 0.6
        assert scenario["initial"]["patch"]
        assert scenario["interruption"]["patch"]


def test_small_sweep_writes_complete_replayable_rows(bench_temp):
    output = bench_temp / "results.jsonl"
    rows = run_sweep(
        scenarios=("hotel_locality_pivot",),
        offsets=(0.3,),
        latency_profiles=("fast",),
        chaos_profiles=("severe",),
        seeds=(7,),
        policies=("naive", "cancel_all", "replan"),
        output=output,
    )

    written = [json.loads(line) for line in output.read_text().splitlines()]
    assert written == rows
    assert len(rows) == 3
    assert all(set(row) == ROW_FIELDS for row in rows)
    assert all(row["replay_ok"] for row in rows)
    assert all(row["trace_coverage"] == 1.0 for row in rows)
    assert all(row["dangling_effects"] == 0 for row in rows)
    assert next(row for row in rows if row["policy"] == "naive")["wrong_actions"] >= 1
    assert next(row for row in rows if row["policy"] == "replan")["wrong_actions"] == 0


def test_plotter_writes_four_nonempty_png_files(bench_temp):
    rows = run_sweep(
        scenarios=("hotel_budget_refine",),
        offsets=(0.3, 1.2),
        latency_profiles=("typical",),
        chaos_profiles=("none",),
        seeds=(0,),
        policies=("naive", "cancel_all", "replan"),
        output=bench_temp / "results.jsonl",
    )
    figures = bench_temp / "figures"
    generate(rows, figures)

    files = sorted(figures.glob("*.png"))
    assert [path.name for path in files] == [
        "freeze_lead_time_histogram.png",
        "tool_calls_by_policy.png",
        "work_reuse_ratio.png",
        "wrong_actions_by_policy.png",
    ]
    assert all(path.stat().st_size > 1000 for path in files)
