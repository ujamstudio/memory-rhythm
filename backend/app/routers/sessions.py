"""Caregiver-dashboard REST endpoints (WS4).

Implements the Memory-Rhythm OpenAPI contract (``Memory-Rhythm/lib/api-spec/
openapi.yaml``) over the in-memory :class:`~app.store.Store`, so the adopted
shadcn caregiver dashboard (which talks to these via the orval-generated client)
lights up with REAL data derived from the live therapy WebSocket conversation.

Shapes are camelCase to match the generated TypeScript client exactly. Like the
rest of the demo this needs no database and no API keys — the whole "today"
view is computed from the in-memory timeline the WS handler appends.

    GET  /api/healthz                 -> {status: "ok"}
    GET  /api/sessions/today          -> SessionSummary
    GET  /api/sessions/timeline       -> TimelineEvent[]
    POST /api/sessions                -> Session            (body SessionInput)
    GET  /api/patient/current-phase   -> PhaseInfo
    POST /api/patient/hint            -> HintRecord         (body HintInput)
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.store import get_store, now_iso

router = APIRouter(tags=["sessions"])

# 4-phase caregiver-dashboard model (the adopted frontend renders these labels in
# its phase tracker). Mapped from the therapy 3-stage machine in Store.
PHASE_META: dict[int, tuple[str, str]] = {
    1: ("기억 회상", "옛 기억을 떠올리며 정서적으로 안정화하는 단계입니다."),
    2: ("감각 자극", "40Hz 자극과 음악·사진 단서로 기억 인출을 돕는 단계입니다."),
    3: ("인지 훈련", "대화로 중심 기억을 회상하고 강화하는 단계입니다."),
    4: ("일상 복귀", "회상한 기억을 오늘의 행동으로 연결하는 단계입니다."),
}


# ---------------------------------------------------------------------------
# camelCase contract models (mirror openapi.yaml component schemas)
# ---------------------------------------------------------------------------

class HealthStatus(BaseModel):
    status: str


class SessionSummary(BaseModel):
    date: str
    totalMessages: int
    hintsUsed: int
    missionsCompleted: int
    currentPhase: int
    durationMinutes: int
    successRate: float


class TimelineEvent(BaseModel):
    id: int
    timestamp: str
    type: str
    content: str
    hintLevel: int | None = None
    missionName: str | None = None


class Session(BaseModel):
    id: int
    startedAt: str
    status: str


class SessionInput(BaseModel):
    patientName: str


class PhaseInfo(BaseModel):
    currentPhase: int
    phaseName: str
    phaseDescription: str
    startedAt: str
    progressPercent: float


class HintInput(BaseModel):
    sessionId: int | None = None
    hintLevel: int
    missionContext: str | None = None


class HintRecord(BaseModel):
    id: int
    hintLevel: int
    recordedAt: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/healthz", response_model=HealthStatus)
async def health_check() -> HealthStatus:
    """Contract health probe (distinct from the richer /api/health)."""
    return HealthStatus(status="ok")


@router.get("/sessions/today", response_model=SessionSummary)
async def get_today_summary() -> SessionSummary:
    return SessionSummary(**get_store().today_summary())


@router.get("/sessions/timeline", response_model=list[TimelineEvent])
async def get_timeline() -> list[TimelineEvent]:
    rows = get_store().list_timeline_events()
    return [
        TimelineEvent(
            id=r.id,
            timestamp=r.timestamp,
            type=r.type,
            content=r.content,
            hintLevel=r.hint_level,
            missionName=r.mission_name,
        )
        for r in rows
    ]


@router.post("/sessions", response_model=Session, status_code=201)
async def create_session(body: SessionInput) -> Session:
    row = get_store().create_dashboard_session(body.patientName)
    return Session(id=row["id"], startedAt=row["startedAt"], status=row["status"])


@router.get("/patient/current-phase", response_model=PhaseInfo)
async def get_current_phase() -> PhaseInfo:
    store = get_store()
    phase, progress = store.dashboard_phase()
    name, desc = PHASE_META.get(phase, PHASE_META[1])
    started = (
        store.dashboard_started_at.isoformat()
        if store.dashboard_started_at is not None
        else now_iso()
    )
    return PhaseInfo(
        currentPhase=phase,
        phaseName=name,
        phaseDescription=desc,
        startedAt=started,
        progressPercent=float(progress),
    )


@router.post("/patient/hint", response_model=HintRecord, status_code=201)
async def record_hint(body: HintInput) -> HintRecord:
    rec = get_store().record_dashboard_hint(body.hintLevel, body.missionContext or "")
    return HintRecord(**rec)
