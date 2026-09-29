"""Tier-1 hypothesis classifier: pure regex over a partial transcript,
deciding whether a goal change is coming and which state paths it will
touch. Must stay fast enough to call on every partial (no network, no
model call, no import of any core module besides schemas) — this runs
several times a second on the fast path (B6).

Checked in order, first match wins. An utterance can only be one kind.
"""

from __future__ import annotations

import re

from replan.schemas import Hypothesis, Interruption

_BACKCHANNEL_RE = re.compile(
    r"^\s*(?:[mh]{2,}(?:[\s-][mh]{2,})?|uh[\s-]?huh|yeah|yep|ok(?:ay)?|right|sure)\s*[.!]?\s*$",
    re.IGNORECASE,
)
_ABORT_RE = re.compile(
    r"\b(?:forget it|cancel everything|never mind|stop)\b",
    re.IGNORECASE,
)
_POLICY_RE = re.compile(
    r"\b(?:don'?t\s+(?:book|buy|order|send|confirm)|just show|only show|hold off)\b",
    re.IGNORECASE,
)
_CLARIFY_RE = re.compile(
    r"\b(?:what was|say that again|repeat|how much|which one)\b",
    re.IGNORECASE,
)
_CONFIRM_CUE_RE = re.compile(
    r"\b(?:yes,?\s*book it|go ahead|confirm|do it|that one)\b",
    re.IGNORECASE,
)
_PIVOT_CUE_RE = re.compile(
    r"\b(?:actually|instead|no wait|scratch that|make it|change it to|"
    r"change the \w+ to|rather)\b",
    re.IGNORECASE,
)
# "no," as a bare turn-initial correction opener ("no, pick up Priya
# first") — kept separate from _PIVOT_CUE_RE because a trailing \b right
# after a comma never matches (no word/non-word transition there), so it
# can't share that group's boundary without breaking every other
# alternative in it.
_PIVOT_NO_COMMA_RE = re.compile(r"^\s*no\s*,", re.IGNORECASE)

# Which state paths a pivot cue's surrounding text seems to reference.
# Structural/lexical cues only — this decides WHICH slot might be
# changing, not the new value (that's replan/agents/proposals.py's job).
SLOT_CUES: dict[str, re.Pattern[str]] = {
    "slots.locality": re.compile(
        r"\b(?:in|to|near|at|around|make it|change it to)\s+[a-zA-Z]", re.IGNORECASE
    ),
    "constraints.budget": re.compile(
        r"\b(?:budget|under|below|less than|more than|₹|\$|rupees?|price)\b", re.IGNORECASE
    ),
    "constraints.dates": re.compile(
        r"\b(?:today|tomorrow|tonight|weekend|check.?in|check.?out|date|"
        r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        re.IGNORECASE,
    ),
    "constraints.breakfast": re.compile(r"\bbreakfast\b", re.IGNORECASE),
    # In-car extension domain (B10) — matches bench.scenarios'
    # incar_destination_pivot, which patches slots.destination. Some
    # phrasing ("change it to X", "make it X") already overlaps
    # slots.locality's cue above; that's harmless over-approximation,
    # not a bug — blast_radius only ever matches real task deps.
    "slots.destination": re.compile(
        r"\b(?:take me to|go to|navigate to|head to|drive to|destination|pick(?:\s+me)?\s+up)\b",
        re.IGNORECASE,
    ),
}


def hypothesise(partial: str, at: float) -> Hypothesis | None:
    if _BACKCHANNEL_RE.match(partial):
        return Hypothesis(kind=Interruption.BACKCHANNEL, confidence=0.95, changed_paths=set(), at=at)

    if _ABORT_RE.search(partial):
        return Hypothesis(kind=Interruption.ABORT, confidence=0.85, changed_paths=set(), at=at)

    if _POLICY_RE.search(partial):
        return Hypothesis(
            kind=Interruption.POLICY,
            confidence=0.85,
            changed_paths={"policy.booking_enabled"},
            at=at,
        )

    if _CLARIFY_RE.search(partial):
        return Hypothesis(kind=Interruption.CLARIFY, confidence=0.7, changed_paths=set(), at=at)

    if _CONFIRM_CUE_RE.search(partial):
        return Hypothesis(kind=Interruption.CONFIRM, confidence=0.9, changed_paths=set(), at=at)

    if _PIVOT_CUE_RE.search(partial) or _PIVOT_NO_COMMA_RE.search(partial):
        paths = {path for path, cue in SLOT_CUES.items() if cue.search(partial)}
        confidence = min(0.50 + 0.22 * len(paths), 0.92)
        kind = Interruption.PIVOT if paths else Interruption.REFINE
        return Hypothesis(kind=kind, confidence=confidence, changed_paths=paths, at=at)

    return None
