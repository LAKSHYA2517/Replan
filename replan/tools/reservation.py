"""In-memory, clock-driven reservation tools."""

from dataclasses import dataclass
from itertools import count


@dataclass
class Reservation:
    reservation_id: str
    fingerprint: str
    expires_at: float
    confirmed: bool = False


class ReservationBook:
    def __init__(self, clock):
        self.clock = clock
        self.held: dict[str, Reservation] = {}
        self._ids = count(1)

    async def prepare(self, args: dict, idem: str, ttl: float = 120.0) -> dict:
        fingerprint = args["_fp"]
        reservation_id = f"res-{next(self._ids):04d}"
        expires_at = self.clock.now() + ttl
        self.held[reservation_id] = Reservation(reservation_id, fingerprint, expires_at)
        return {"reservation_id": reservation_id, "expires_at": expires_at}

    async def confirm(self, args: dict, idem: str) -> dict:
        reservation_id = args["reservation_id"]
        reservation = self.held.get(reservation_id)
        if reservation is None:
            raise ValueError(f"Unknown reservation: {reservation_id}")
        if reservation.confirmed:
            return {"idempotent_replay": True}
        if self.clock.now() >= reservation.expires_at:
            raise ValueError(f"Expired reservation: {reservation_id}")
        reservation.confirmed = True
        return {"reservation_id": reservation_id, "confirmed": True}

    async def release(self, args: dict, idem: str) -> dict:
        return {"released": self.held.pop(args["reservation_id"], None) is not None}
