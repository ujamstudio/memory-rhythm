"""WebSocket endpoint for the STEP 1 초기 설문 (conversational onboarding).

    ws://localhost:8000/ws/survey/{session_id}

Mirrors ``app/ws.py``: on connect we build the provider bundle (mock by default,
no keys needed) and a :class:`~app.services.survey.SurveyService`, then loop
receiving JSON client messages validated against the ``SurveyClientMessage``
discriminated union from ``app.schemas`` and dispatch them to the service, which
is handed an ``emit`` callback that serializes and sends ``SurveyServerMessage``
objects back to the browser.

Per-survey conversation state lives in ``app.store`` (keyed by ``session_id``),
so this handler stays stateless beyond the socket lifetime. This endpoint and
its message unions are entirely SEPARATE from the therapy WS.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, TypeAdapter, ValidationError

from app.config import get_settings
from app.providers import get_providers
from app.schemas import (
    ErrorMsg,
    SkipQuestion,
    StartSurvey,
    SurveyAnswer,
    SurveyClientMessage,
)
from app.services.survey import SurveyService
from app.store import get_store

router = APIRouter()

# Validates raw client dicts into the correct concrete survey model via the
# discriminator on the "type" field.
_client_adapter: TypeAdapter[SurveyClientMessage] = TypeAdapter(SurveyClientMessage)


def _to_jsonable(message: Any) -> dict:
    """Coerce a SurveyServerMessage (pydantic model) or plain dict into JSON."""
    if isinstance(message, BaseModel):
        return message.model_dump(mode="json")
    if isinstance(message, dict):
        return message
    raise TypeError(f"Cannot serialize server message of type {type(message)!r}")


@router.websocket("/ws/survey/{session_id}")
async def survey_socket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()

    # Build per-connection from fresh settings + providers (mock fallback). The
    # SurveyService picks templated vs LLM summary from providers.llm.backend.
    settings = get_settings()
    providers = get_providers(settings)
    service = SurveyService(providers, get_store())

    async def emit(message: Any) -> None:
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
                await _dispatch(service, session_id, msg, emit)
            except Exception as exc:  # keep the socket alive on per-turn failures
                await emit(ErrorMsg(message=f"처리 중 오류가 발생했습니다: {exc}"))
            # Persist after each survey step so the completed profile + seeded
            # memories (the patient's starting data) survive a restart.
            get_store().persist()

    except WebSocketDisconnect:
        # Normal client-initiated close — nothing to clean up (state is in store).
        return
    except RuntimeError:
        # Socket already closed mid-send; treat as a disconnect.
        return


async def _dispatch(
    service: SurveyService,
    session_id: str,
    msg: SurveyClientMessage,
    emit: Any,
) -> None:
    """Route a validated survey client message to the matching service method."""
    if isinstance(msg, StartSurvey):
        await service.start(
            session_id, msg.patient_id, msg.name, msg.dementia_type, emit
        )
    elif isinstance(msg, SurveyAnswer):
        await service.answer(session_id, msg.text, emit)
    elif isinstance(msg, SkipQuestion):
        await service.skip(session_id, emit)
    else:  # pragma: no cover - discriminated union is exhaustive
        await emit(ErrorMsg(message="지원하지 않는 메시지 타입입니다."))
