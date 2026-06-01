"""WebSocket endpoint for the live conversation loop.

    ws://localhost:8000/ws/session/{session_id}

On connect we build the provider bundle (mock by default — no keys needed) and
an :class:`~app.services.orchestrator.Orchestrator`, then loop receiving JSON
client messages. Each message is validated against the ``ClientMessage``
discriminated union from ``app.schemas`` and dispatched to an orchestrator
``handle_*`` coroutine, which is handed an ``emit`` callback that serializes and
sends ``ServerMessage`` objects back to the browser.

Per-session conversation state lives in ``app.store`` (keyed by ``session_id``),
so this handler stays stateless beyond the socket lifetime.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, TypeAdapter, ValidationError

from app.config import get_settings
from app.providers import get_providers
from app.schemas import (
    AdvanceTime,
    ClientMessage,
    ErrorMsg,
    StartSession,
    ToggleTone,
    UserMessage,
)
from app.services.orchestrator import Orchestrator, build_orchestrator

router = APIRouter()

# Validates raw client dicts into the correct concrete model via the
# discriminator on the "type" field.
_client_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


def _to_jsonable(message: Any) -> dict:
    """Coerce a ServerMessage (pydantic model) or plain dict into a JSON dict."""
    if isinstance(message, BaseModel):
        # mode="json" ensures enums/Literals/datetimes serialize cleanly.
        return message.model_dump(mode="json")
    if isinstance(message, dict):
        return message
    raise TypeError(f"Cannot serialize server message of type {type(message)!r}")


@router.websocket("/ws/session/{session_id}")
async def session_socket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()

    # Build per-connection from fresh settings + providers. The factory picks a
    # provider per capability (mock/openai/google) with transparent mock
    # fallback, and build_orchestrator derives mock-mode + resolved model names
    # from the provider backend tags and settings.
    settings = get_settings()
    providers = get_providers(settings)
    orchestrator = build_orchestrator(settings, providers)

    async def emit(message: Any) -> None:
        """Send a ServerMessage (or dict) to the connected client as JSON text."""
        await websocket.send_json(_to_jsonable(message))

    try:
        while True:
            raw = await websocket.receive_json()
            try:
                msg = _client_adapter.validate_python(raw)
            except ValidationError as exc:
                await emit(ErrorMsg(message=f"잘못된 메시지 형식입니다: {exc.errors()[:1]}"))
                continue

            try:
                await _dispatch(orchestrator, session_id, msg, emit)
            except Exception as exc:  # keep the socket alive on per-turn failures
                await emit(ErrorMsg(message=f"처리 중 오류가 발생했습니다: {exc}"))

    except WebSocketDisconnect:
        # Normal client-initiated close — nothing to clean up (state is in store).
        return
    except RuntimeError:
        # Socket already closed mid-send; treat as a disconnect.
        return


async def _dispatch(
    orchestrator: Orchestrator,
    session_id: str,
    msg: ClientMessage,
    emit: Any,
) -> None:
    """Route a validated client message to the matching orchestrator handler.

    The orchestrator's handlers take unwrapped primitives (text / days / on) and
    receive ``emit`` (a dict-accepting, possibly-async callback). ``start_session``
    binds the session to a patient (auto-creating a demo patient when needed) and
    does not itself emit, so the socket stays quiet until the first user turn.
    """
    if isinstance(msg, StartSession):
        await orchestrator.start_session(session_id, msg.patient_id)
    elif isinstance(msg, UserMessage):
        await orchestrator.handle_user_message(session_id, msg.text, emit)
    elif isinstance(msg, AdvanceTime):
        await orchestrator.handle_advance_time(session_id, msg.days, emit)
    elif isinstance(msg, ToggleTone):
        await orchestrator.handle_toggle_tone(session_id, msg.on, emit)
    else:  # pragma: no cover - discriminated union is exhaustive
        await emit(ErrorMsg(message="지원하지 않는 메시지 타입입니다."))
