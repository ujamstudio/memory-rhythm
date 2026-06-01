"""Caregiver portal REST endpoints (CONTRACT.md §4).

    POST /api/caregiver/intake   body {patient_id, structured: object}  -> {ok: true}

The structured intake (collected via the caregiver IntakeForm) is persisted on
the in-memory store so the orchestrator / memory service can use it to prime the
patient persona and seed recall candidates.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas import CaregiverIntakeRequest, OkResponse
from app.store import get_store

router = APIRouter(tags=["caregiver"])


@router.post("/caregiver/intake", response_model=OkResponse)
async def submit_intake(body: CaregiverIntakeRequest) -> OkResponse:
    store = get_store()
    if store.get_patient(body.patient_id) is None:
        raise HTTPException(status_code=404, detail="환자를 찾을 수 없습니다.")
    store.save_intake(patient_id=body.patient_id, structured=body.structured)
    return OkResponse(ok=True)
