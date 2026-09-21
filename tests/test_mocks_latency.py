from random import Random

import pytest

from bench.latency import LATENCY_PROFILES
from replan.tools.mocks import make_mock_tool
from replan.tools.registry import TOOL_SPECS


class FakeClock:
    def __init__(self):
        self.delays = []

    async def sleep(self, seconds):
        self.delays.append(seconds)


@pytest.mark.asyncio
async def test_search_hotels_is_seeded_filtered_and_reflects_inputs():
    async def run(seed):
        clock = FakeClock()
        tool = make_mock_tool("search_hotels", clock, Random(seed), 0.4)
        result = await tool(
            {"city": "Pune", "budget": 5000, "breakfast": True}, "search-1"
        )
        return result, clock.delays

    first, first_delays = await run(42)
    second, second_delays = await run(42)

    assert first == second
    assert first_delays == second_delays == [0.4]
    assert len(first["hotels"]) == 3
    assert all(hotel["name"].startswith("Pune ") for hotel in first["hotels"])
    assert all(hotel["price"] <= 5000 for hotel in first["hotels"])
    assert all(hotel["breakfast"] is True for hotel in first["hotels"])


@pytest.mark.asyncio
async def test_search_hotels_honours_false_breakfast_and_tight_budget():
    clock = FakeClock()
    tool = make_mock_tool("search_hotels", clock, Random(7), 0.25)

    result = await tool(
        {"locality": "Andheri", "budget": 2100, "breakfast": False}, "search-2"
    )

    assert clock.delays == [0.25]
    assert all(hotel["name"].startswith("Andheri ") for hotel in result["hotels"])
    assert all(hotel["price"] <= 2100 for hotel in result["hotels"])
    assert all(hotel["breakfast"] is False for hotel in result["hotels"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "args", "keys"),
    [
        ("availability", {"hotel": "Pune Grand"}, {"hotel", "available", "rooms_left"}),
        ("loyalty_status", {}, {"tier", "points"}),
        ("booking_policy", {}, {"free_cancellation", "pay_at_property"}),
    ],
)
async def test_other_mock_tools_use_clock_and_seeded_rng(name, args, keys):
    first_clock = FakeClock()
    second_clock = FakeClock()
    first_tool = make_mock_tool(name, first_clock, Random(11), 0.6)
    second_tool = make_mock_tool(name, second_clock, Random(11), 0.6)

    first = await first_tool(args, "idem")
    second = await second_tool(args, "idem")

    assert first == second
    assert set(first) == keys
    assert first_clock.delays == second_clock.delays == [0.6]


def test_unknown_mock_tool_is_rejected():
    with pytest.raises(ValueError, match="Unknown mock tool"):
        make_mock_tool("missing", FakeClock(), Random(1), 0.1)


def test_latency_profiles_cover_every_registered_tool():
    assert set(LATENCY_PROFILES) == {
        "fast",
        "typical",
        "slow",
        "long_tail",
        "one_stalled",
    }
    expected_tools = set(TOOL_SPECS)
    assert all(set(profile) == expected_tools for profile in LATENCY_PROFILES.values())

    for name, spec in TOOL_SPECS.items():
        typical = spec["latency"]
        assert LATENCY_PROFILES["typical"][name] == typical
        assert LATENCY_PROFILES["fast"][name] == typical / 4
        assert LATENCY_PROFILES["slow"][name] == typical * 3
        assert LATENCY_PROFILES["long_tail"][name] == typical * (
            8 if name in {"search_hotels", "analyze_image"} else 1
        )
        assert LATENCY_PROFILES["one_stalled"][name] == typical * (
            20 if name == "availability" else 1
        )
