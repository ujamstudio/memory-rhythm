"""Community simulation REST endpoint (CONTRACT.md §4).

    POST /api/community/simulate   body {patient_id, topic}
        -> {turns: [{persona, text}]}

Delegates to the community service, which generates a short virtual peer-persona
group chat around the given topic (recovered-keyword driven in the full demo).
The mock provider yields deterministic Korean turns so this works offline.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.providers import get_providers
from app.schemas import CommunitySimulateRequest, CommunitySimulateResponse
from app.services.community import CommunityService

router = APIRouter(tags=["community"])


@router.post("/community/simulate", response_model=CommunitySimulateResponse)
async def simulate(body: CommunitySimulateRequest) -> CommunitySimulateResponse:
    settings = get_settings()
    providers = get_providers(settings)
    # Decide mock-mode from the resolved LLM backend tag (NOT settings) so it
    # stays correct under per-capability selection and after credential fallback,
    # and reuse the resolved dialogue model (gpt-4o-mini / gemini-2.5-flash).
    llm_is_mock = getattr(providers.llm, "backend", "mock") == "mock"
    service = CommunityService(
        providers=providers,
        use_mock=llm_is_mock,
        dialogue_model=settings.dialogue_model,
    )
    turns = await service.simulate(topic=body.topic)
    return CommunitySimulateResponse(turns=turns)
