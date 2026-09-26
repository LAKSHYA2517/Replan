"""Deterministic benchmark scenario definitions."""


def incar_destination_pivot(interrupt_offset: float) -> dict:
    """Change destination while an old destination result is still in flight."""
    if interrupt_offset < 0:
        raise ValueError("interrupt_offset must be non-negative")
    return {
        "name": "incar_destination_pivot",
        "initial": {
            "at": 0.0,
            "utterance": "Set my destination to Mumbai Airport and start navigation.",
            "patch": {"slots": {"destination": "Mumbai Airport"}},
            "tool_calls": [
                {"tool": "set_destination", "args": {"destination": "Mumbai Airport"}},
                {"tool": "start_navigation", "args": {"destination": "Mumbai Airport"}},
            ],
        },
        "interruption": {
            "at": interrupt_offset,
            "utterance": "Actually, take me to Bandra Station instead.",
            "patch": {"slots": {"destination": "Bandra Station"}},
            "tool_calls": [
                {"tool": "set_destination", "args": {"destination": "Bandra Station"}},
                {"tool": "start_navigation", "args": {"destination": "Bandra Station"}},
            ],
        },
        "late_result": {
            "at": interrupt_offset + 0.5,
            "tool": "set_destination",
            "args": {"destination": "Mumbai Airport"},
        },
    }


def smarthome_pivot(interrupt_offset: float) -> dict:
    """Build the smart-home pivot with a deliberately late stale result."""
    if interrupt_offset < 0:
        raise ValueError("interrupt_offset must be non-negative")
    return {
        "name": "smarthome_pivot",
        "initial": {
            "at": 0.0,
            "utterance": "Set the AC in the bedroom to 18 and start the washer on cotton.",
            "patch": {
                "slots": {"room": "bedroom", "appliance": "washer"},
                "constraints": {"temperature": 18, "mode": "cotton"},
            },
            "tool_calls": [
                {"tool": "set_temperature", "args": {"room": "bedroom", "degrees": 18}},
                {"tool": "start_appliance", "args": {"name": "washer", "mode": "cotton"}},
            ],
        },
        "interruption": {
            "at": interrupt_offset,
            "utterance": "No — the living room, and make it 24.",
            "patch": {
                "slots": {"room": "living room"},
                "constraints": {"temperature": 24},
            },
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


def hotel_locality_pivot(interrupt_offset: float) -> dict:
    """Change locality while unrelated loyalty work remains useful."""
    if interrupt_offset < 0:
        raise ValueError("interrupt_offset must be non-negative")
    return {
        "name": "hotel_locality_pivot",
        "initial": {
            "at": 0.0,
            "utterance": "Find hotels in Bandra under 5000 with breakfast.",
            "patch": {
                "slots": {"locality": "Bandra", "member": "member-7"},
                "constraints": {"budget": 5000, "breakfast": True},
            },
            "tool_calls": [
                {
                    "tool": "search_hotels",
                    "args": {"locality": "Bandra", "budget": 5000, "breakfast": True},
                },
                {"tool": "loyalty_status", "args": {"member": "member-7"}},
            ],
        },
        "interruption": {
            "at": interrupt_offset,
            "utterance": "Actually, make that Juhu.",
            "patch": {"slots": {"locality": "Juhu"}},
            "tool_calls": [
                {
                    "tool": "search_hotels",
                    "args": {"locality": "Juhu", "budget": 5000, "breakfast": True},
                }
            ],
        },
        "late_result": {
            "at": interrupt_offset + 0.5,
            "tool": "search_hotels",
            "args": {"locality": "Bandra", "budget": 5000, "breakfast": True},
        },
    }


def hotel_budget_refine(interrupt_offset: float) -> dict:
    """Tighten a budget while policy lookup remains reusable."""
    if interrupt_offset < 0:
        raise ValueError("interrupt_offset must be non-negative")
    return {
        "name": "hotel_budget_refine",
        "initial": {
            "at": 0.0,
            "utterance": "Show Juhu hotels under 8000 with breakfast.",
            "patch": {
                "slots": {"locality": "Juhu"},
                "constraints": {"budget": 8000, "breakfast": True},
            },
            "tool_calls": [
                {
                    "tool": "search_hotels",
                    "args": {"locality": "Juhu", "budget": 8000, "breakfast": True},
                },
                {"tool": "booking_policy", "args": {"rate": "refundable"}},
            ],
        },
        "interruption": {
            "at": interrupt_offset,
            "utterance": "Keep it under 5000.",
            "patch": {"constraints": {"budget": 5000}},
            "tool_calls": [
                {
                    "tool": "search_hotels",
                    "args": {"locality": "Juhu", "budget": 5000, "breakfast": True},
                }
            ],
        },
        "late_result": {
            "at": interrupt_offset + 0.5,
            "tool": "search_hotels",
            "args": {"locality": "Juhu", "budget": 8000, "breakfast": True},
        },
    }


def booking_policy_pivot(interrupt_offset: float) -> dict:
    """Disable booking while hotel availability remains independently useful."""
    if interrupt_offset < 0:
        raise ValueError("interrupt_offset must be non-negative")
    return {
        "name": "booking_policy_pivot",
        "initial": {
            "at": 0.0,
            "utterance": "Check the Sea View and allow booking.",
            "patch": {
                "slots": {"hotel": "Sea View"},
                "policy": {"booking_enabled": True},
            },
            "tool_calls": [
                {"tool": "availability", "args": {"hotel": "Sea View"}},
                {"tool": "booking_policy", "args": {"booking_enabled": True}},
            ],
        },
        "interruption": {
            "at": interrupt_offset,
            "utterance": "Do not book anything, just show availability.",
            "patch": {"policy": {"booking_enabled": False}},
            "tool_calls": [
                {"tool": "booking_policy", "args": {"booking_enabled": False}}
            ],
        },
        "late_result": {
            "at": interrupt_offset + 0.5,
            "tool": "booking_policy",
            "args": {"booking_enabled": True},
        },
    }


SCENARIOS = {
    "hotel_locality_pivot": hotel_locality_pivot,
    "hotel_budget_refine": hotel_budget_refine,
    "booking_policy_pivot": booking_policy_pivot,
    "smarthome_pivot": smarthome_pivot,
    "incar_destination_pivot": incar_destination_pivot,
}
