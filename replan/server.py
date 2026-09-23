"""RePlan WebSocket event bridge server and test harness.

Broadcasts recorder events to connected web clients as JSON, and exposes
a POST /inject_late_result endpoint for interactive adversarial demo beats.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Set

import websockets
from websockets.server import WebSocketServerProtocol

from replan.schemas import Event, EventType, Verdict

logger = logging.getLogger("replan.server")


class EventBridgeServer:
    """Async WebSocket server that broadcasts runtime events to browser consoles."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8000):
        self.host = host
        self.port = port
        self.clients: Set[WebSocketServerProtocol] = set()
        self.event_queue: asyncio.Queue[dict] = asyncio.Queue()
        self.injected_late_results: asyncio.Queue[dict] = asyncio.Queue()

    async def register(self, websocket: WebSocketServerProtocol) -> None:
        """Register a new connected client."""
        self.clients.add(websocket)
        logger.info("Browser client connected (%d active)", len(self.clients))

    async def unregister(self, websocket: WebSocketServerProtocol) -> None:
        """Unregister a disconnected client."""
        self.clients.discard(websocket)
        logger.info("Browser client disconnected (%d active)", len(self.clients))

    async def broadcast(self, event_data: dict) -> None:
        """Broadcast an event payload to all connected clients."""
        if not self.clients:
            return
        message = json.dumps(event_data)
        # Send concurrently to all connected clients
        await asyncio.gather(
            *[client.send(message) for client in self.clients],
            return_exceptions=True,
        )

    async def emit_event(self, event: Event) -> None:
        """Emit a schema Event object to the broadcast queue."""
        event_dict = event.model_dump(mode="json")
        await self.broadcast(event_dict)

    async def handler(self, websocket: WebSocketServerProtocol, path: str = "/") -> None:
        """Main WebSocket connection handler."""
        await self.register(websocket)
        try:
            async for message in websocket:
                # Handle any incoming commands from client
                try:
                    data = json.loads(message)
                    if data.get("type") == "inject_late_result":
                        await self.injected_late_results.put(data)
                except Exception as e:
                    logger.warning("Error processing client message: %s", e)
        except websockets.ConnectionClosed:
            pass
        finally:
            await self.unregister(websocket)

    async def start(self) -> None:
        """Start the WebSocket server loop."""
        logger.info("Starting RePlan Event Bridge on ws://%s:%d/events", self.host, self.port)
        async with websockets.serve(self.handler, self.host, self.port):
            await asyncio.Future()  # run forever


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    server = EventBridgeServer()
    await server.start()


if __name__ == "__main__":
    asyncio.run(main())
