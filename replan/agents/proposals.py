"""Turn a final transcript into a validated Proposal — never directly into
a state change. LLM output is untrusted input: parsed, normalised, and
allowlist-checked before it becomes a Proposal object; the runtime is the
only thing that ever applies it to state.

Also holds the LLM response cache: a dict keyed by the SHA-256 of the exact
prompt, persisted to a JSON fixture. In "record" mode it writes through to
a live call; in "replay" mode a miss is an error, never a live call — this
is what lets `make demo` run with no API key.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

from dateutil import parser as dateparser

from replan.schemas import Proposal, SessionState

ALLOWED_SECTIONS = frozenset(f for f in SessionState.model_fields if f != "version")

LLMCallFn = Callable[[str], Awaitable[str]]


class CacheMiss(RuntimeError):
    """Raised in replay mode when a prompt has no recorded response."""


class LLMCache:
    def __init__(self, path: Path, mode: Literal["record", "replay"]) -> None:
        self.path = path
        self.mode = mode
        self._data: dict[str, str] = {}
        if path.exists():
            self._data = json.loads(path.read_text())

    @staticmethod
    def key_for(prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    async def get_or_call(self, prompt: str, call: LLMCallFn) -> str:
        key = self.key_for(prompt)
        if key in self._data:
            return self._data[key]
        if self.mode == "replay":
            raise CacheMiss(f"no cached response for prompt hash {key[:12]}...")
        response = await call(prompt)
        self._data[key] = response
        self._persist()
        return response

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2, sort_keys=True))


_LOCALITY_KEY_RE = re.compile(r"locality|city|area|neighbou?rhood", re.IGNORECASE)
_DATE_KEY_RE = re.compile(r"date|checkin|checkout|when", re.IGNORECASE)
_BUDGET_KEY_RE = re.compile(r"budget|price|cost|amount", re.IGNORECASE)
_BUDGET_DIGITS_RE = re.compile(r"[\d,]+")


def _normalize_value(key: str, value: Any) -> Any:
    if not isinstance(value, str):
        if _BUDGET_KEY_RE.search(key) and isinstance(value, (int, float)):
            return int(value)
        return value

    if _LOCALITY_KEY_RE.search(key):
        return value.strip().lower()

    if _DATE_KEY_RE.search(key):
        try:
            return dateparser.parse(value).date().isoformat()
        except (ValueError, OverflowError):
            return value

    if _BUDGET_KEY_RE.search(key):
        digits = _BUDGET_DIGITS_RE.search(value)
        if digits:
            return int(digits.group(0).replace(",", ""))
        return value

    return value


def _normalize_patch(patch: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        section: {key: _normalize_value(key, value) for key, value in fields.items()}
        for section, fields in patch.items()
    }


def _patch_is_allowed(patch: dict[str, dict[str, Any]]) -> bool:
    return set(patch.keys()) <= ALLOWED_SECTIONS


_PROPOSAL_SYSTEM_PROMPT = (
    "You extract a state patch from a user's spoken utterance for a booking "
    "assistant. Return JSON only, matching exactly this shape: "
    '{"patch": {"slots": {...}, "constraints": {...}}, "rationale": '
    '"one short sentence", "confidence": 0.0-1.0}. '
    f"The only allowed top-level patch sections are: {sorted(ALLOWED_SECTIONS)}. "
    "Only include fields the utterance actually changes — do not restate "
    "unchanged values. If the utterance changes nothing about the booking "
    "(a backchannel, a question, small talk), return an empty patch."
)


def _build_prompt(transcript: str, state: SessionState) -> str:
    return json.dumps(
        {
            "system": _PROPOSAL_SYSTEM_PROMPT,
            "current_state": {
                "slots": state.slots,
                "constraints": state.constraints,
                "policy": state.policy,
            },
            "utterance": transcript,
        },
        sort_keys=True,
    )


async def extract_proposal(
    transcript: str,
    state: SessionState,
    llm: LLMCallFn,
    cache: LLMCache,
) -> Proposal:
    """Calls the LLM (through the cache) for a strict-JSON proposal,
    validates it, and normalises every value. Falls back to
    rule_based_proposal on any parse/validation failure — at most one LLM
    attempt, no retry loop.
    """
    prompt = _build_prompt(transcript, state)
    try:
        raw = await cache.get_or_call(prompt, llm)
        body = json.loads(raw)
        patch = body.get("patch", {})
        if not isinstance(patch, dict) or not _patch_is_allowed(patch):
            raise ValueError(f"patch touches disallowed sections: {patch.keys()}")
        patch = _normalize_patch(patch)
        return Proposal(
            kind="state_patch",
            patch=patch,
            rationale=str(body.get("rationale", "")),
            confidence=float(body.get("confidence", 1.0)),
        )
    except CacheMiss:
        raise
    except (json.JSONDecodeError, ValueError, TypeError, KeyError):
        return rule_based_proposal(transcript, state)


_LOCALITY_CUE_RE = re.compile(
    r"(?:make it|change it to|instead,?\s*(?:make it)?|in|to)\s+"
    r"([a-zA-Z][a-zA-Z\s]{1,24}?)(?:[.,!?]|$)",
    re.IGNORECASE,
)
_BUDGET_CUE_RE = re.compile(
    r"(?:under|below|less than|budget of)\s*[₹$]?\s*([\d,]+)",
    re.IGNORECASE,
)
_ABORT_CUE_RE = re.compile(r"forget it|cancel everything|never mind|stop", re.IGNORECASE)


def rule_based_proposal(transcript: str, state: SessionState) -> Proposal:
    """Deterministic regex extractor. Must never raise — any failure here
    falls through to an empty, honest patch rather than crashing the turn.
    """
    try:
        if _ABORT_CUE_RE.search(transcript):
            return Proposal(kind="state_patch", patch={}, rationale="abort cue detected", confidence=0.6)

        patch: dict[str, dict[str, Any]] = {}

        budget_match = _BUDGET_CUE_RE.search(transcript)
        if budget_match:
            patch.setdefault("constraints", {})["budget"] = _normalize_value(
                "budget", budget_match.group(1)
            )

        locality_match = _LOCALITY_CUE_RE.search(transcript)
        if locality_match:
            candidate = locality_match.group(1).strip()
            if candidate and len(candidate.split()) <= 4:
                patch.setdefault("slots", {})["locality"] = _normalize_value("locality", candidate)

        if not patch:
            return Proposal(kind="state_patch", patch={}, rationale="no extractable change found", confidence=0.3)

        return Proposal(kind="state_patch", patch=patch, rationale="rule-based extraction", confidence=0.5)
    except Exception:
        return Proposal(kind="state_patch", patch={}, rationale="rule-based extraction failed", confidence=0.0)
