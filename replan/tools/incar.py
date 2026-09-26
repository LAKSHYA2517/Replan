"""In-memory in-car tools for the extension safety demonstration."""


INCAR_STATE: dict[str, object] = {
    "destination": None,
    "navigation": {"active": False, "route_id": None, "destination": None},
}


async def set_destination(args: dict, idem: str) -> dict:
    destination = args["destination"]
    previous = INCAR_STATE["destination"]
    INCAR_STATE["destination"] = destination
    return {"destination": destination, "previous_destination": previous}


async def revert_destination(args: dict, idem: str) -> dict:
    destination = args.get("previous_destination")
    INCAR_STATE["destination"] = destination
    return {"destination": destination, "reverted": True}


async def start_navigation(args: dict, idem: str) -> dict:
    destination = args.get("destination", INCAR_STATE["destination"])
    route_id = f"route-{idem}"
    navigation = {
        "active": True,
        "route_id": route_id,
        "destination": destination,
    }
    INCAR_STATE["navigation"] = navigation
    return dict(navigation)


async def cancel_route(args: dict, idem: str) -> dict:
    navigation = INCAR_STATE["navigation"]
    was_active = bool(navigation["active"])
    navigation["active"] = False
    return {
        "route_id": navigation["route_id"],
        "destination": navigation["destination"],
        "active": False,
        "cancelled": was_active,
    }
