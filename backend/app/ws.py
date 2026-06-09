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
from app.sse import get_bus
from app.store import get_store, now_iso

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


def _record_dashboard(message: Any, dash: dict) -> None:
    """Derive caregiver-dashboard timeline events + SSE pushes from an outgoing
    ServerMessage. Best-effort and non-fatal — never breaks the chat loop.

    ``dash`` is per-connection scratch state (tracks the last hint level so an
    escalation is only recorded once).
    """
    try:
        d = _to_jsonable(message)
    except Exception:
        return
    store = get_store()
    t = d.get("type")
    if t == "assistant_message":
        hl = int(d.get("hint_level", 0) or 0)
        store.set_dashboard_stage(int(d.get("stage", 1) or 1))
        store.append_timeline_event("ai_message", d.get("text", ""), hint_level=hl or None)
        if hl > dash.get("hint", 0):
            store.record_dashboard_hint(hl, f"‘{(d.get('text') or '')[:24]}’")
            get_bus().publish(
                "hint",
                {"level": hl, "content": (d.get("text") or "")[:48], "at": now_iso()},
            )
            dash["hint"] = hl
    elif t == "autobiography_page":
        page = d.get("page", {}) or {}
        narrative = (page.get("narrative") or "")[:24]
        store.append_timeline_event(
            "mission_success",
            f"기억이 자서전으로 남았어요: {narrative}…",
            mission_name="자서전 페이지",
        )
    elif t == "recall_prompt":
        store.append_timeline_event("ai_message", f"🔔 {d.get('text', '')}")


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

    # Per-connection caregiver-dashboard derivation state (hint escalation).
    dash: dict[str, int] = {"hint": 0}

    async def emit(message: Any) -> None:
        """Send a ServerMessage (or dict) to the connected client as JSON text."""
        _record_dashboard(message, dash)
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
            # Persist the (possibly grown) durable store after each turn so the
            # patient's accumulating data survives a restart. No-op in memory mode.
            get_store().persist()

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
        # Caregiver dashboard: begin a fresh "today" view + push a live alert.
        store = get_store()
        state = store.get_session_state(session_id)
        pid = (state.patient_id if state else "") or msg.patient_id
        patient = store.get_patient(pid)
        name = patient.name if patient else "환자"
        store.start_dashboard_session(name)
        get_bus().publish("session_started", {"patientName": name, "at": now_iso()})
    elif isinstance(msg, UserMessage):
        get_store().append_timeline_event("patient_response", msg.text)
        await orchestrator.handle_user_message(session_id, msg.text, emit)
    elif isinstance(msg, AdvanceTime):
        await orchestrator.handle_advance_time(session_id, msg.days, emit)
    elif isinstance(msg, ToggleTone):
        await orchestrator.handle_toggle_tone(session_id, msg.on, emit)
    else:  # pragma: no cover - discriminated union is exhaustive
        await emit(ErrorMsg(message="지원하지 않는 메시지 타입입니다."))
