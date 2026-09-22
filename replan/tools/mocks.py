"""Deterministic, clock-driven mock tool bodies."""

from random import Random


_HOTEL_NAMES = (
    "Grand",
    "Residency",
    "Suites",
    "Garden",
    "Harbour",
    "Palace",
    "Orchid",
    "Park",
    "Comfort Inn",
    "Courtyard",
    "Boutique",
    "Retreat",
)
_TOOLS = {"search_hotels", "availability", "loyalty_status", "booking_policy"}


def make_mock_tool(name: str, clock, rng: Random, latency: float):
    """Construct an async tool using the supplied clock and seeded RNG."""
    if name not in _TOOLS:
        raise ValueError(f"Unknown mock tool: {name}")

    async def tool(args: dict, idem: str) -> dict:
        await clock.sleep(latency)

        if name == "search_hotels":
            locality = args.get("locality") or args.get("city") or "Mumbai"
            budget = args.get("budget")
            breakfast = args.get("breakfast")
            candidates = [
                {
                    "name": f"{locality} {hotel_name}",
                    "price": 1500 + index * 400 + rng.randrange(300),
                    "breakfast": index % 2 == 0,
                }
                for index, hotel_name in enumerate(rng.sample(_HOTEL_NAMES, len(_HOTEL_NAMES)))
            ]
            eligible = [
                hotel for hotel in candidates
                if (budget is None or hotel["price"] <= budget)
                and (breakfast is None or hotel["breakfast"] == breakfast)
            ]
            return {"hotels": rng.sample(eligible, min(3, len(eligible)))}

        if name == "availability":
            rooms_left = rng.randrange(5)
            return {"hotel": args.get("hotel"), "available": rooms_left > 0, "rooms_left": rooms_left}

        if name == "loyalty_status":
            return {"tier": rng.choice(("Silver", "Gold", "Platinum")), "points": rng.randrange(1000, 10000)}

        return {
            "free_cancellation": rng.choice((True, False)),
            "pay_at_property": rng.choice((True, False)),
        }

    tool.__name__ = name
    tool.base_latency = latency
    return tool
