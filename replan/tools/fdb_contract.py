"""LiveKit tool-contract adapter: thin async wrappers around FDB-v3's own
mock API functions, in the same (args, idem) -> dict shape every other
tool in this project already uses (C1's make_mock_tool, etc.), so the
Executor/CommitGate dispatch and judge them exactly as before.

Calls FDB-v3's real functions directly — never reimplements their logic —
so results can never drift from what the official evaluator computes.
Deliberately does NOT go through FDB-v3's own MockAPIRegistry.call(): that
wrapper does a real blocking sleep (plus unseeded randomness and a raw
wall-clock read) for its own latency simulation, which is the stock
template's own behaviour but would stall this project's single event
loop if awaited into an async dispatch. Latency here is simulated
through the injected clock instead, using registry.py's own declared
latency per tool — the raw mock functions themselves have no randomness
or side effects, so bypassing only the latency wrapper still returns
byte-identical results.
"""

from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Awaitable, Callable

# The 12 tools confirmed directly against v3/mock_apis.py in the real
# github.com/DanielLin94144/Full-Duplex-Bench repo — not the published
# paper's table, which names five of these differently or not at all.
FDB_TOOLS = (
    "search_flights", "book_flight", "update_identity_doc",
    "get_card_benefits", "get_exchange_rate", "modify_autopay",
    "search_apartments", "calculate_commute", "update_search_filter",
    "track_order", "search_products", "add_to_cart",
)


def _load_fdb_mock_apis():
    """Import FDB-v3's real mock_apis module from the local clone made
    during the C9 hard gate. Lazy, not module-level: importing eagerly
    would make `import replan.tools.fdb_contract` fail for anyone who
    hasn't set FDB_V3_PATH yet, even code that never dispatches these
    tools (e.g. running the original hotel/smart-home scenarios).
    """
    fdb_path = os.environ.get("FDB_V3_PATH")
    if not fdb_path:
        raise RuntimeError(
            "FDB_V3_PATH is not set. Point it at the v3/ directory of your "
            "local github.com/DanielLin94144/Full-Duplex-Bench clone "
            "(the one C9's hard gate already has you make), e.g. "
            "FDB_V3_PATH=/path/to/Full-Duplex-Bench/v3"
        )
    if fdb_path not in sys.path:
        sys.path.insert(0, fdb_path)
    try:
        return importlib.import_module("mock_apis")
    except ImportError as exc:
        raise RuntimeError(
            f"Could not import mock_apis from FDB_V3_PATH={fdb_path!r}. "
            "Confirm it points at the v3/ directory (the one containing "
            "mock_apis.py), not the repo root."
        ) from exc


def make_fdb_tool(name: str, clock, latency: float) -> Callable[[dict, str], Awaitable[dict]]:
    """Build an async tool callable for FDB-v3 tool `name`, matching this
    project's (args, idem) -> dict convention. `latency` comes from the
    caller (registry.py's TOOL_SPECS), matching how make_mock_tool takes
    it explicitly rather than looking it up internally.
    """
    if name not in FDB_TOOLS:
        raise ValueError(f"Not an FDB-v3 tool: {name!r}. Known: {sorted(FDB_TOOLS)}")

    async def tool(args: dict, idem: str) -> dict:
        module = _load_fdb_mock_apis()
        real_func = getattr(module, name)
        await clock.sleep(latency)
        return real_func(**args)

    tool.__name__ = name
    return tool
