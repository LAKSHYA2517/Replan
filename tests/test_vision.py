import json
from pathlib import Path

import pytest

from replan.schemas import Effect, Proposal
from replan.tools.registry import TOOL_SPECS
from replan.tools.vision import analyze_image


FIXTURES = Path(__file__).parent / "fixtures"
IMAGE = FIXTURES / "competitor_listing.jpg"


@pytest.mark.asyncio
async def test_mock_vision_is_deterministic_for_path_and_bytes():
    expected = json.loads((FIXTURES / "vision_ocr.json").read_text(encoding="utf-8"))
    path_result = await analyze_image({"image": IMAGE, "currency": "INR"}, "path")
    bytes_result = await analyze_image(
        {"image": IMAGE.read_bytes(), "session_currency": "inr"}, "bytes"
    )

    assert path_result == bytes_result
    proposal = Proposal.model_validate(path_result)
    assert proposal.kind == "state_patch"
    assert proposal.patch == {"constraints": {"budget": expected["price"]}}
    assert proposal.confidence == expected["confidence"]


@pytest.mark.asyncio
async def test_live_vision_calls_configured_model_with_jpeg_bytes():
    calls = []

    async def model(image):
        calls.append(image)
        return {"price": 5100, "currency": "INR", "confidence": 0.91}

    result = await analyze_image(
        {
            "image": IMAGE,
            "mode": "live",
            "_vision_model": model,
            "currency": "INR",
        },
        "live",
    )

    assert calls == [IMAGE.read_bytes()]
    assert Proposal.model_validate(result).patch == {"constraints": {"budget": 5100}}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("ocr", "currency", "reason"),
    [
        ({"price": "4200", "currency": "INR", "confidence": 0.9}, "INR", "not numeric"),
        ({"price": True, "currency": "INR", "confidence": 0.9}, "INR", "not numeric"),
        ({"price": 4200.5, "currency": "INR", "confidence": 0.9}, "INR", "whole number"),
        ({"price": 99, "currency": "INR", "confidence": 0.9}, "INR", "plausible range"),
        ({"price": 100001, "currency": "INR", "confidence": 0.9}, "INR", "plausible range"),
        ({"price": 4200, "currency": "USD", "confidence": 0.9}, "INR", "does not match"),
        ({"price": 4200, "currency": "INR", "confidence": -0.1}, "INR", "confidence"),
        ({"price": 4200, "currency": "INR", "confidence": 1.1}, "INR", "confidence"),
        ({"price": 4200, "currency": "INR", "confidence": 0.9}, None, "currency is missing"),
    ],
)
async def test_invalid_ocr_returns_empty_proposal(ocr, currency, reason):
    async def model(_image):
        return ocr

    result = await analyze_image(
        {
            "image": IMAGE,
            "mode": "live",
            "_vision_model": model,
            "currency": currency,
        },
        "invalid",
    )

    proposal = Proposal.model_validate(result)
    assert proposal.patch == {}
    assert proposal.confidence == 0.0
    assert reason in proposal.rationale


@pytest.mark.asyncio
async def test_invalid_image_mode_and_model_output_are_rejected():
    bad_image = Proposal.model_validate(
        await analyze_image({"image": b"not jpeg", "currency": "INR"}, "bad-image")
    )
    unknown_mode = Proposal.model_validate(
        await analyze_image({"image": IMAGE, "mode": "unknown", "currency": "INR"}, "mode")
    )

    async def model(_image):
        return "not a dictionary"

    bad_output = Proposal.model_validate(
        await analyze_image(
            {"image": IMAGE, "mode": "live", "_vision_model": model, "currency": "INR"},
            "bad-output",
        )
    )

    assert bad_image.patch == {}
    assert "JPEG" in bad_image.rationale
    assert unknown_mode.patch == {}
    assert "unknown vision mode" in unknown_mode.rationale
    assert bad_output.patch == {}
    assert "dictionary" in bad_output.rationale


@pytest.mark.asyncio
async def test_live_mode_requires_configured_model():
    with pytest.raises(ValueError, match="configured _vision_model"):
        await analyze_image({"image": IMAGE, "mode": "live", "currency": "INR"}, "live")


def test_vision_registry_contract():
    assert TOOL_SPECS["analyze_image"] == {
        "effect": Effect.PURE,
        "cost": 1.5,
        "latency": 0.8,
        "compensator": None,
    }
