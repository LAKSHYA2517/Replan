"""Named deterministic tool latency profiles, in seconds."""

from replan.tools.registry import TOOL_SPECS


_TYPICAL = {name: spec["latency"] for name, spec in TOOL_SPECS.items()}

LATENCY_PROFILES = {
    "fast": {name: delay / 4 for name, delay in _TYPICAL.items()},
    "typical": _TYPICAL,
    "slow": {name: delay * 3 for name, delay in _TYPICAL.items()},
    "long_tail": {
        name: delay * (8 if name in {"search_hotels", "analyze_image"} else 1)
        for name, delay in _TYPICAL.items()
    },
    "one_stalled": {
        name: delay * (20 if name == "availability" else 1)
        for name, delay in _TYPICAL.items()
    },
}
