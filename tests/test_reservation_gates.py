import sys
from types import ModuleType, SimpleNamespace

import pytest

from replan.schemas import Effect, SessionState
from replan.tools.gates import may_confirm
from replan.tools.registry import TOOL_SPECS
from replan.tools.reservation import Reservation, ReservationBook


class FakeClock:
    def __init__(self, now=0.0):
        self.value = now

    def now(self):
        return self.value


@pytest.mark.asyncio
async def test_prepare_allocates_sequential_reservations_with_expiry_and_fingerprint():
    clock = FakeClock(10.0)
    book = ReservationBook(clock)

    first = await book.prepare({"_fp": "fp-1"}, "prepare-1")
    second = await book.prepare({"_fp": "fp-2"}, "prepare-2", ttl=30.0)

    assert first == {"reservation_id": "res-0001", "expires_at": 130.0}
    assert second == {"reservation_id": "res-0002", "expires_at": 40.0}
    assert book.held == {
        "res-0001": Reservation("res-0001", "fp-1", 130.0),
        "res-0002": Reservation("res-0002", "fp-2", 40.0),
    }


@pytest.mark.asyncio
async def test_confirm_succeeds_and_replay_is_idempotent():
    book = ReservationBook(FakeClock(5.0))
    prepared = await book.prepare({"_fp": "fp"}, "prepare")

    confirmed = await book.confirm(prepared, "confirm-1")
    replay = await book.confirm(prepared, "confirm-2")

    assert confirmed == {"reservation_id": "res-0001", "confirmed": True}
    assert replay == {"idempotent_replay": True}
    assert book.held["res-0001"].confirmed is True


@pytest.mark.asyncio
async def test_confirm_rejects_unknown_and_expired_reservations():
    clock = FakeClock(20.0)
    book = ReservationBook(clock)

    with pytest.raises(ValueError, match="Unknown reservation"):
        await book.confirm({"reservation_id": "res-9999"}, "unknown")

    prepared = await book.prepare({"_fp": "fp"}, "prepare", ttl=2.0)
    clock.value = prepared["expires_at"]
    with pytest.raises(ValueError, match="Expired reservation"):
        await book.confirm(prepared, "expired")


@pytest.mark.asyncio
async def test_release_is_idempotent():
    book = ReservationBook(FakeClock())
    prepared = await book.prepare({"_fp": "fp"}, "prepare")

    assert await book.release(prepared, "release-1") == {"released": True}
    assert await book.release(prepared, "release-2") == {"released": False}
    assert book.held == {}


def _install_fingerprint(monkeypatch, value):
    module = ModuleType("replan.depgraph")
    module.fingerprint = lambda task, state: value
    monkeypatch.setitem(sys.modules, "replan.depgraph", module)


@pytest.mark.parametrize(
    ("booking_enabled", "user_confirmed", "current_fp", "dispatch_fp", "allowed", "reason"),
    [
        (False, True, "same", "same", False, "booking is disabled"),
        (True, False, "same", "same", False, "explicit user confirmation"),
        (True, True, "new", "old", False, "fingerprint is stale"),
        (True, True, "same", "same", True, "fingerprint current"),
    ],
)
def test_may_confirm_requires_policy_confirmation_and_current_fingerprint(
    monkeypatch,
    booking_enabled,
    user_confirmed,
    current_fp,
    dispatch_fp,
    allowed,
    reason,
):
    _install_fingerprint(monkeypatch, current_fp)
    task = SimpleNamespace(dispatch_fp=dispatch_fp)
    store = SimpleNamespace(
        current=SessionState(policy={"booking_enabled": booking_enabled})
    )

    result = may_confirm(task, store, user_confirmed)

    assert result[0] is allowed
    assert reason in result[1]


def test_reservation_registry_contracts():
    assert TOOL_SPECS["reserve_room"]["effect"] is Effect.REVERSIBLE
    assert TOOL_SPECS["reserve_room"]["compensator"] == "release_room"
    assert TOOL_SPECS["confirm_room"]["effect"] is Effect.IRREVERSIBLE
    assert TOOL_SPECS["confirm_room"]["compensator"] is None
    assert TOOL_SPECS["release_room"]["effect"] is Effect.REVERSIBLE
