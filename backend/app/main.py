"""FastAPI application entry point for the Memory Rhythm demo.

Boots with zero secrets: default ``AI_PROVIDER=mock`` and ``STORE=memory`` so a
full conversation loop is served with no database and no API keys. Set
``AI_PROVIDER=openai`` (+ ``OPENAI_API_KEY``) to switch to real models.

Run from the ``backend/`` directory:

    uv run uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.providers import get_providers
from app.routers import autobiography, caregiver, community, patients, sessions, survey
from app.schemas import HealthResponse
from app.sse import router as sse_router
from app.ws import router as ws_router
from app.ws_survey import router as ws_survey_router

# Surface backend warnings (esp. LLM/이미지/임베딩 → mock 폴백) so a silent
# 429/auth/network degradation is visible in the server log during demos.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

settings = get_settings()


def _init_persistence() -> None:
    """Attach SQLite persistence to the store (load-on-boot) unless STORE=memory.

    Guarded: any failure (read-only FS, locked file) logs and falls back to the
    pure in-memory store, so the demo always boots.
    """
    if settings.store == "memory":
        return
    try:
        from app.db.persistence import SqlitePersistence
        from app.store import get_store

        default = Path(__file__).resolve().parent.parent / "data" / "memory_rhythm.db"
        db_path = settings.db_path or str(default)
        get_store().attach_persistence(SqlitePersistence(db_path))
        logging.getLogger(__name__).info("영속 저장 활성화(SQLite): %s", db_path)
    except Exception as exc:  # pragma: no cover - never block boot
        logging.getLogger(__name__).warning("영속 저장 초기화 실패 → 인메모리로 진행: %s", exc)


_init_persistence()

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
# Caregiver-dashboard contract (WS4): sessions/today, timeline, current-phase, hint.
app.include_router(sessions.router, prefix="/api")
# Caregiver-dashboard live alerts (SSE): GET /api/events/stream.
app.include_router(sse_router, prefix="/api")

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


# ---------------------------------------------------------------------------
# Static frontend (single-host deploy): when a built React bundle is present we
# serve it from FastAPI itself, so ONE process serves the SPA + REST + WS (the
# frontend's ws.ts assumes same-host, so this "just works" — no CORS needed).
# Resolution order: STATIC_DIR env -> backend/static -> ../frontend/dist.
# Absent (local dev with a separate Vite server) -> a friendly JSON root only.
# ---------------------------------------------------------------------------
def _resolve_static_dir() -> Path | None:
    candidates = []
    env_dir = os.environ.get("STATIC_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    here = Path(__file__).resolve().parent  # backend/app
    candidates.append(here.parent / "static")          # backend/static
    candidates.append(here.parent.parent / "frontend" / "dist")  # repo/frontend/dist
    for c in candidates:
        if c.is_dir() and (c / "index.html").is_file():
            return c
    return None


_static_dir = _resolve_static_dir()

if _static_dir is not None:
    _assets = _static_dir / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        """Serve a real static file when it exists, else the SPA index.html so
        client-side routes (wouter) resolve. /api and /ws are matched by their
        routers first, so this catch-all only handles frontend paths."""
        target = _static_dir / full_path
        if full_path and target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(_static_dir / "index.html"))

else:

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        """Tiny landing payload so hitting the bare backend root is friendly."""
        return {
            "service": "memory-rhythm-backend",
            "docs": "/docs",
            "health": "/api/health",
            "ws": "/ws/session/{session_id}",
        }
