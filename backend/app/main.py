"""FastAPI application entry point for the Memory Rhythm demo.

Boots with zero secrets: default ``AI_PROVIDER=mock`` and ``STORE=memory`` so a
full conversation loop is served with no database and no API keys. Set
``AI_PROVIDER=openai`` (+ ``OPENAI_API_KEY``) to switch to real models.

Run from the ``backend/`` directory:

    uv run uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.providers import get_providers
from app.routers import autobiography, caregiver, community, patients, survey
from app.schemas import HealthResponse
from app.ws import router as ws_router
from app.ws_survey import router as ws_survey_router

settings = get_settings()

app = FastAPI(
    title="Memory Rhythm Backend",
    version="0.1.0",
    description=(
        "치매 인지 동반자 AI 웹 데모 백엔드 — 이중 LLM(두뇌/입), 3-Tier 기억, "
        "자서전 그림책 파이프라인. 기본값(mock/memory)으로 비밀키·DB 없이 동작."
    ),
)

# CORS: the Vite dev server runs at http://localhost:5173 and proxies /api + /ws.
# Allow the configured origin (default http://localhost:5173) plus the 127.0.0.1
# alias so the demo works regardless of how the browser resolves localhost.
_allowed_origins = {settings.cors_origin, "http://localhost:5173", "http://127.0.0.1:5173"}
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(_allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST routers (all mounted under the /api prefix per CONTRACT.md §4).
app.include_router(patients.router, prefix="/api")
app.include_router(autobiography.router, prefix="/api")
app.include_router(caregiver.router, prefix="/api")
app.include_router(community.router, prefix="/api")
# STEP 1 — Survey REST: GET /api/patients/{id}/survey.
app.include_router(survey.router, prefix="/api")

# WebSocket router: ws://localhost:8000/ws/session/{session_id} (no /api prefix).
app.include_router(ws_router)
# Survey WebSocket: ws://localhost:8000/ws/survey/{session_id} (no /api prefix).
app.include_router(ws_survey_router)


@app.get("/api/health", response_model=HealthResponse, tags=["meta"])
async def health() -> HealthResponse:
    """Liveness probe reporting the EFFECTIVE per-capability provider backends.

    Provider constructors are lazy/cheap (SDKs are imported only when a real
    backend is actually selected + keyed), so building the bundle here is fine.
    The reported backends reflect any credential fallback to mock, so this is an
    honest view of what will actually run.
    """
    providers = get_providers(get_settings())
    return HealthResponse(
        status="ok",
        provider=providers.llm.backend,
        store=settings.store,
        providers={
            "llm": providers.llm.backend,
            "stt": providers.stt.backend,
            "tts": providers.tts.backend,
            "image": providers.image.backend,
            "embedding": providers.embedding.backend,
        },
    )


@app.get("/", include_in_schema=False)
async def root() -> dict:
    """Tiny landing payload so hitting the bare backend root is friendly."""
    return {
        "service": "memory-rhythm-backend",
        "docs": "/docs",
        "health": "/api/health",
        "ws": "/ws/session/{session_id}",
    }
