import asyncio

import pytest

from bench.run import _drive_episode
from bench.scenarios import incar_destination_pivot
from replan.schemas import Effect, EventType, Verdict
from replan.tools.incar import (
    INCAR_STATE,
    cancel_route,
    revert_destination,
    set_destination,
    start_navigation,
)
from replan.tools.registry import TOOL_SPECS


@pytest.fixture(autouse=True)
def reset_incar_state():
    INCAR_STATE["destination"] = None
    INCAR_STATE["navigation"] = {
        "active": False,
        "route_id": None,
        "destination": None,
    }


@pytest.mark.asyncio
async def test_incar_state_and_compensators():
    old = await set_destination({"destination": "Mumbai Airport"}, "dest-1")
    new = await set_destination({"destination": "Bandra Station"}, "dest-2")
    route = await start_navigation({"destination": "Bandra Station"}, "nav-1")

    assert INCAR_STATE["destination"] == "Bandra Station"
    assert route == {
        "active": True,
        "route_id": "route-nav-1",
        "destination": "Bandra Station",
    }
    assert await cancel_route(route, "cancel-1") == {
        "route_id": "route-nav-1",
        "destination": "Bandra Station",
        "active": False,
        "cancelled": True,
    }
    assert await revert_destination(new, "revert-1") == {
        "destination": "Mumbai Airport",
        "reverted": True,
    }
    assert old["previous_destination"] is None


def test_incar_scenario_and_registry_contract():
    scenario = incar_destination_pivot(0.6)

    assert scenario["interruption"]["at"] == 0.6
    assert scenario["interruption"]["patch"] == {
        "slots": {"destination": "Bandra Station"}
    }
    assert scenario["late_result"] == {
        "at": 1.1,
        "tool": "set_destination",
        "args": {"destination": "Mumbai Airport"},
    }
    assert TOOL_SPECS["set_destination"]["effect"] is Effect.REVERSIBLE
    assert TOOL_SPECS["set_destination"]["compensator"] == "revert_destination"
    assert TOOL_SPECS["start_navigation"]["compensator"] == "cancel_route"


def test_replan_records_old_destination_as_stale_evidence():
    runtime = asyncio.run(
        _drive_episode(
            "incar_destination_pivot", 0.6, "fast", "none", 7, "replan"
        )
    )
    stale = [decision for decision in runtime.gate.ledger if decision.verdict is Verdict.STALE]
    verdict_events = [
        event
        for event in runtime.recorder.events
        if event.type is EventType.VERDICT and event.payload.get("verdict") == "stale"
    ]

    assert stale
    assert verdict_events
    assert "dispatch fp" in verdict_events[-1].payload["reason"]
    assert runtime.metrics.wrong_actions == 0


def test_fdb_v3_registry_has_all_twelve_official_tools():
    official = {
        "search_flights",
        "book_flight",
        "update_identity_doc",
        "get_card_benefits",
        "get_exchange_rate",
        "modify_autopay",
        "search_apartments",
        "calculate_commute",
        "update_search_filter",
        "track_order",
        "search_products",
        "add_to_cart",
    }

    assert official <= TOOL_SPECS.keys()
    assert all(set(TOOL_SPECS[name]) == {"effect", "cost", "latency", "compensator"} for name in official)
