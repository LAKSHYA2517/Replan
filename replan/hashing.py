"""Canonical JSON and truncated SHA-256 hashing.

Every validity decision in the system is a comparison of two of these
strings, so both functions must be deterministic across processes and runs.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canon(obj: Any) -> str:
    """Canonical JSON: sorted keys, no whitespace, non-JSON types via str()."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def h(*parts: Any, n: int = 16) -> str:
    """SHA-256 over the parts joined by "|", truncated to n hex chars.

    Non-string parts are canonicalized first so a dict argument (e.g. a
    resolved arg_spec) hashes by its sorted-key JSON form, not by Python's
    insertion-ordered repr.
    """
    joined = "|".join(part if isinstance(part, str) else canon(part) for part in parts)
    return hashlib.sha256(joined.encode()).hexdigest()[:n]
