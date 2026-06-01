"""Survey REST endpoint (STEP 1 — 초기 설문).

    GET /api/patients/{patient_id}/survey  -> SurveyResult  (404 if none yet)

Thin: delegates to the in-memory ``store`` singleton, which holds completed
survey results keyed by ``patient_id`` (written by the survey WS on completion).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas import SurveyResult
from app.store import get_store

router = APIRouter(tags=["survey"])


@router.get("/patients/{patient_id}/survey", response_model=SurveyResult)
async def get_survey(patient_id: str) -> SurveyResult:
    store = get_store()
    result = store.get_survey_result(patient_id)
    if result is None:
        raise HTTPException(status_code=404, detail="설문 결과를 찾을 수 없습니다.")
    return result
