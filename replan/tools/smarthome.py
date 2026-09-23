"""In-memory smart-home tools used by the safety demonstration."""


DEVICE_STATE: dict[str, dict] = {
    "temperatures": {},
    "appliances": {},
}


async def set_temperature(args: dict, idem: str) -> dict:
    room = args["room"]
    degrees = args["degrees"]
    previous = DEVICE_STATE["temperatures"].get(room)
    DEVICE_STATE["temperatures"][room] = degrees
    return {"room": room, "degrees": degrees, "previous_degrees": previous}


async def restore_temperature(args: dict, idem: str) -> dict:
    room = args["room"]
    previous = args.get("previous_degrees")
    if previous is None:
        DEVICE_STATE["temperatures"].pop(room, None)
    else:
        DEVICE_STATE["temperatures"][room] = previous
    return {"room": room, "degrees": previous, "restored": True}


async def start_appliance(args: dict, idem: str) -> dict:
    name = args["name"]
    mode = args["mode"]
    DEVICE_STATE["appliances"][name] = {"mode": mode, "running": True}
    return {"name": name, "mode": mode, "running": True}


async def stop_appliance(args: dict, idem: str) -> dict:
    name = args["name"]
    appliance = DEVICE_STATE["appliances"].get(name)
    if appliance is None:
        DEVICE_STATE["appliances"][name] = {"mode": args.get("mode"), "running": False}
        stopped = False
    else:
        appliance["running"] = False
        stopped = True
    return {"name": name, "running": False, "stopped": stopped}
