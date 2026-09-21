"""Deterministic benchmark scenario definitions."""


def smarthome_pivot(interrupt_offset: float) -> dict:
    """Build the smart-home pivot with a deliberately late stale result."""
    if interrupt_offset < 0:
        raise ValueError("interrupt_offset must be non-negative")
    return {
        "name": "smarthome_pivot",
        "initial": {
            "at": 0.0,
            "utterance": "Set the AC in the bedroom to 18 and start the washer on cotton.",
            "tool_calls": [
                {"tool": "set_temperature", "args": {"room": "bedroom", "degrees": 18}},
                {"tool": "start_appliance", "args": {"name": "washer", "mode": "cotton"}},
            ],
        },
        "interruption": {
            "at": interrupt_offset,
            "utterance": "No — the living room, and make it 24.",
            "tool_calls": [
                {"tool": "set_temperature", "args": {"room": "living room", "degrees": 24}},
            ],
        },
        "late_result": {
            "at": interrupt_offset + 0.5,
            "tool": "set_temperature",
            "args": {"room": "bedroom", "degrees": 18},
        },
    }


SCENARIOS = {"smarthome_pivot": smarthome_pivot}
