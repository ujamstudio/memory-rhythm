"""Server-Sent Events bus for the caregiver dashboard (WS4).

A tiny in-memory pub/sub: the therapy WebSocket handler publishes
``session_started`` and ``hint`` events as the live conversation runs; the
caregiver dashboard subscribes via ``GET /api/events/stream`` (an EventSource).
No external broker — everything stays in-process, so the zero-secrets boot is
preserved.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["events"])


class _Bus:
    """In-process fan-out of (event, data) tuples to all open SSE streams."""

    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, event: str, data: dict) -> None:
        """Synchronously enqueue an event for every subscriber (non-blocking)."""
        for q in list(self._subs):
            try:
                q.put_nowait((event, data))
            except Exception:  # pragma: no cover - a full/closed queue is non-fatal
                pass


_bus = _Bus()


def get_bus() -> _Bus:
    """Return the process-wide SSE event bus singleton."""
    return _bus


@router.get("/events/stream")
async def events_stream(request: Request) -> StreamingResponse:
    """text/event-stream of live caregiver alerts (hint / session_started)."""
    q = get_bus().subscribe()

    async def gen():
        try:
            # Open the stream so the browser's EventSource fires `onopen`.
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event, data = await asyncio.wait_for(q.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # Periodic comment keeps proxies from closing an idle stream.
                    yield ": keepalive\n\n"
                    continue
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        finally:
            get_bus().unsubscribe(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
