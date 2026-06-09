"""Patient REST endpoints (CONTRACT.md §4).

    POST /api/patients                      -> Patient
    GET  /api/patients/{id}                 -> Patient
    GET  /api/patients/{id}/memories        -> Memory[]
    GET  /api/patients/{id}/autobiography    -> AutobiographyPage[]
    GET  /api/patients/{id}/recall-queue     -> RecallItem[]

Plus the optional STT helper (multipart) used by the handset mic:

    POST /api/stt   (file field "audio")    -> {text: string}

All endpoints are thin and delegate to the in-memory ``store`` singleton; STT
delegates to the configured provider bundle (mock returns canned Korean text).
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import get_settings
from app.providers import get_providers
from app.schemas import (
    AutobiographyPage,
    CreatePatientRequest,
    Memory,
    Patient,
    RecallItem,
    SttResponse,
)
from app.store import get_store

router = APIRouter(tags=["patients"])


@router.post("/patients", response_model=Patient)
async def create_patient(body: CreatePatientRequest) -> Patient:
    store = get_store()
    return store.create_patient(name=body.name, dementia_type=body.dementia_type)


@router.get("/patients", response_model=list[Patient])
async def list_patients() -> list[Patient]:
    """List all patients (used by the home-page demo picker)."""
    store = get_store()
    return list(store.patients.values())


@router.get("/patients/{patient_id}", response_model=Patient)
async def get_patient(patient_id: str) -> Patient:
    store = get_store()
    patient = store.get_patient(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="환자를 찾을 수 없습니다.")
    return patient


@router.get("/patients/{patient_id}/memories", response_model=list[Memory])
async def list_memories(patient_id: str) -> list[Memory]:
    store = get_store()
    return store.list_memories(patient_id)


@router.get("/patients/{patient_id}/autobiography", response_model=list[AutobiographyPage])
async def list_autobiography(patient_id: str) -> list[AutobiographyPage]:
    store = get_store()
    return store.list_pages(patient_id)


@router.get("/patients/{patient_id}/recall-queue", response_model=list[RecallItem])
async def list_recall_queue(patient_id: str) -> list[RecallItem]:
    store = get_store()
    return store.list_recall_items(patient_id)


@router.post("/stt", response_model=SttResponse)
async def speech_to_text(audio: UploadFile = File(...)) -> SttResponse:
    """Transcribe an uploaded audio clip to Korean text via the STT provider."""
    data = await audio.read()
    providers = get_providers(get_settings())
    mime = audio.content_type or "audio/webm"
    text = await providers.stt.transcribe(data, mime=mime)
    return SttResponse(text=text)
