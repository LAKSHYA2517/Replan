"""Tool table. FROZEN after Hour Zero — declarations only, no bodies.

Person C fills in tool bodies in other files under replan/tools/.
"""

from replan.schemas import Effect

TOOL_SPECS: dict[str, dict] = {
    # FDB-v3 scored tools. Its five mutations expose no undo API, so their
    # compensators remain intentionally unresolved instead of naming wrappers
    # that do not exist in the benchmark contract.
    "search_flights": {"effect": Effect.PURE, "cost": 0.5, "latency": 0.5, "compensator": None},
    "book_flight": {"effect": Effect.REVERSIBLE, "cost": 1.0, "latency": 2.0, "compensator": None},
    "update_identity_doc": {"effect": Effect.REVERSIBLE, "cost": 1.0, "latency": 0.125, "compensator": None},
    "get_card_benefits": {"effect": Effect.PURE, "cost": 0.5, "latency": 0.125, "compensator": None},
    "get_exchange_rate": {"effect": Effect.PURE, "cost": 0.5, "latency": 0.125, "compensator": None},
    "modify_autopay": {"effect": Effect.REVERSIBLE, "cost": 1.0, "latency": 2.0, "compensator": None},
    "search_apartments": {"effect": Effect.PURE, "cost": 0.5, "latency": 0.5, "compensator": None},
    "calculate_commute": {"effect": Effect.PURE, "cost": 0.5, "latency": 0.5, "compensator": None},
    "update_search_filter": {"effect": Effect.REVERSIBLE, "cost": 1.0, "latency": 0.125, "compensator": None},
    "track_order": {"effect": Effect.PURE, "cost": 0.5, "latency": 0.125, "compensator": None},
    "search_products": {"effect": Effect.PURE, "cost": 0.5, "latency": 0.5, "compensator": None},
    "add_to_cart": {"effect": Effect.REVERSIBLE, "cost": 1.0, "latency": 2.0, "compensator": None},

    # Original extension-use-case tools.
    "search_hotels": {"effect": Effect.PURE, "cost": 1.0, "latency": 0.4, "compensator": None},
    "availability": {"effect": Effect.PURE, "cost": 1.0, "latency": 0.3, "compensator": None},
    "loyalty_status": {"effect": Effect.PURE, "cost": 0.5, "latency": 0.2, "compensator": None},
    "booking_policy": {"effect": Effect.PURE, "cost": 0.5, "latency": 0.2, "compensator": None},
    "reserve_room": {"effect": Effect.REVERSIBLE, "cost": 1.0, "latency": 0.5, "compensator": "release_room"},
    "confirm_room": {"effect": Effect.IRREVERSIBLE, "cost": 1.0, "latency": 0.5, "compensator": None},
    "release_room": {"effect": Effect.REVERSIBLE, "cost": 0.2, "latency": 0.2, "compensator": None},
    "analyze_image": {"effect": Effect.PURE, "cost": 1.5, "latency": 0.8, "compensator": None},
    "set_temperature": {"effect": Effect.REVERSIBLE, "cost": 0.5, "latency": 0.2, "compensator": "restore_temperature"},
    "start_appliance": {"effect": Effect.REVERSIBLE, "cost": 0.5, "latency": 0.2, "compensator": "stop_appliance"},
    "set_destination": {"effect": Effect.REVERSIBLE, "cost": 0.5, "latency": 0.2, "compensator": "revert_destination"},
    "revert_destination": {"effect": Effect.REVERSIBLE, "cost": 0.2, "latency": 0.1, "compensator": None},
    "start_navigation": {"effect": Effect.REVERSIBLE, "cost": 0.5, "latency": 0.2, "compensator": "cancel_route"},
    "cancel_route": {"effect": Effect.REVERSIBLE, "cost": 0.2, "latency": 0.1, "compensator": None},
}
