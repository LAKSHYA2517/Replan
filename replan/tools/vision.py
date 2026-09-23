"""Vision tool that converts OCR output into a validated state proposal.

Live mode expects ``args["_vision_model"]`` to be an async callable accepting
JPEG bytes and returning an OCR dict with price, currency, and confidence.
"""

from __future__ import annotations

import json
from pathlib import Path

from replan.schemas import Proposal


_FIXTURE = Path(__file__).parents[2] / "tests" / "fixtures" / "vision_ocr.json"


def _empty(rationale: str) -> dict:
    return Proposal(patch={}, rationale=rationale, confidence=0.0).model_dump()


def _jpeg_bytes(source) -> bytes:
    if isinstance(source, (str, Path)):
        image = Path(source).read_bytes()
    elif isinstance(source, bytes):
        image = source
    else:
        raise ValueError("image must be a JPEG path or bytes")
    if not image.startswith(b"\xff\xd8\xff") or not image.endswith(b"\xff\xd9"):
        raise ValueError("image is not valid JPEG data")
    return image


def _proposal(ocr: dict, session_currency) -> dict:
    price = ocr.get("price")
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        return _empty("rejected OCR: price is not numeric")
    if not float(price).is_integer():
        return _empty("rejected OCR: price must be a whole number")
    price = int(price)
    if not 100 <= price <= 100_000:
        return _empty("rejected OCR: price is outside the plausible range 100-100000")

    detected_currency = ocr.get("currency")
    if not isinstance(session_currency, str) or not session_currency.strip():
        return _empty("rejected OCR: session currency is missing")
    if not isinstance(detected_currency, str) or detected_currency.upper() != session_currency.upper():
        return _empty(
            f"rejected OCR: detected currency {detected_currency!r} does not match "
            f"session currency {session_currency!r}"
        )

    confidence = ocr.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        return _empty("rejected OCR: confidence must be between 0 and 1")
    return Proposal(
        kind="state_patch",
        patch={"constraints": {"budget": price}},
        rationale=f"OCR detected {detected_currency.upper()} {price}",
        confidence=float(confidence),
    ).model_dump()


async def analyze_image(args: dict, idem: str) -> dict:
    """Analyze JPEG input in deterministic mock mode or through a live model."""
    try:
        image = _jpeg_bytes(args.get("image"))
    except (OSError, ValueError) as error:
        return _empty(f"rejected image: {error}")

    mode = args.get("mode", "mock")
    if mode == "mock":
        ocr = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    elif mode == "live":
        model = args.get("_vision_model")
        if model is None:
            raise ValueError("live mode requires a configured _vision_model")
        ocr = await model(image)
    else:
        return _empty(f"rejected image: unknown vision mode {mode!r}")

    if not isinstance(ocr, dict):
        return _empty("rejected OCR: model output must be a dictionary")
    return _proposal(ocr, args.get("session_currency", args.get("currency")))
