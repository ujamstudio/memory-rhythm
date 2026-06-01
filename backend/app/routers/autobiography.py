"""Autobiography REST endpoint.

The contract's autobiography listing lives under the patient resource
(``GET /api/patients/{id}/autobiography``) and is served by the patients
router. This module additionally exposes a convenience listing keyed directly
by patient id so the e-book panel can refresh pages without re-deriving the
route, and so the router set stays symmetric with the other resources.

    GET /api/autobiography/{patient_id}   -> AutobiographyPage[]

It is a thin pass-through to the in-memory ``store`` singleton.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas import AutobiographyPage
from app.store import get_store

router = APIRouter(tags=["autobiography"])


@router.get("/autobiography/{patient_id}", response_model=list[AutobiographyPage])
async def list_pages(patient_id: str) -> list[AutobiographyPage]:
    """Return the ordered autobiography picture-book pages for a patient."""
    store = get_store()
    # store.list_pages already returns pages sorted by order_idx.
    return store.list_pages(patient_id)
