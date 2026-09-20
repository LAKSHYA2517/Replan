"""Tool table. FROZEN after Hour Zero — declarations only, no bodies.

Person C fills in tool bodies in other files under replan/tools/.
"""

from replan.schemas import Effect

TOOL_SPECS: dict[str, dict] = {
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
}
