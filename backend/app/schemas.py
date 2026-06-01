"""Pydantic v2 models for the Memory Rhythm demo.

Single source of truth for:
  * WebSocket client/server messages (discriminated on the ``type`` field).
  * REST data shapes and request/response bodies.

Field names here are byte-for-byte identical to ``frontend/src/protocol.ts``.
All user-facing string content is Korean; identifiers/comments are English.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums (as Literal aliases)
# ---------------------------------------------------------------------------

DementiaType = Literal["alzheimer", "vascular", "lewy"]
RecallStatus = Literal["unrecalled", "recalled"]
IntervalStage = Literal[1, 3, 7, 21]

# Stage labels (1 -> 정서 안정화, 2 -> 대화형 인출, 3 -> 행동 수행)
STAGE_LABELS: dict[int, str] = {
    1: "정서 안정화",
    2: "대화형 인출",
    3: "행동 수행",
}


def stage_label(stage: int) -> str:
    """Return the Korean label for a stage number (empty string if unknown)."""
    return STAGE_LABELS.get(stage, "")


# ---------------------------------------------------------------------------
# Core data shapes (REST + embedded in WS payloads)
# ---------------------------------------------------------------------------

class Patient(BaseModel):
    id: str
    name: str
    dementia_type: DementiaType
    persona_profile: str = ""
    created_at: str


class Memory(BaseModel):
    id: str
    patient_id: str
    text: str
    keywords: list[str] = Field(default_factory=list)
    recall_status: RecallStatus = "unrecalled"
    created_at: str


class AutobiographyPage(BaseModel):
    id: str
    patient_id: str
    session_id: str
    image_url: str
    narrative: str
    order_idx: int


class RecallItem(BaseModel):
    id: str
    memory_id: str
    text: str
    due_at: str
    interval_stage: IntervalStage


class CaregiverIntake(BaseModel):
    patient_id: str
    structured: dict[str, Any] = Field(default_factory=dict)


class ReasoningDecision(BaseModel):
    """The 두뇌 (reasoner) decision attached to a ``reasoning`` WS message."""

    stage: int
    next_stage: int
    hint_level: int
    recall_detected: bool
    keywords: list[str] = Field(default_factory=list)
    reason: str = ""


class CommunityTurn(BaseModel):
    persona: str
    text: str


# ---------------------------------------------------------------------------
# WebSocket: Client -> Server
# ---------------------------------------------------------------------------

class StartSession(BaseModel):
    type: Literal["start_session"] = "start_session"
    patient_id: str = ""


class UserMessage(BaseModel):
    type: Literal["user_message"] = "user_message"
    text: str


class AdvanceTime(BaseModel):
    type: Literal["advance_time"] = "advance_time"
    days: int


class ToggleTone(BaseModel):
    type: Literal["toggle_tone"] = "toggle_tone"
    on: bool


ClientMessage = Annotated[
    Union[StartSession, UserMessage, AdvanceTime, ToggleTone],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# WebSocket: Server -> Client
# ---------------------------------------------------------------------------

class ReasoningMsg(BaseModel):
    type: Literal["reasoning"] = "reasoning"
    decision: ReasoningDecision
    latency_ms: float
    model: str


class StageChange(BaseModel):
    type: Literal["stage_change"] = "stage_change"
    stage: int
    label: str


class AssistantMessage(BaseModel):
    type: Literal["assistant_message"] = "assistant_message"
    text: str
    stage: int
    hint_level: int


class AutobiographyPageMsg(BaseModel):
    type: Literal["autobiography_page"] = "autobiography_page"
    page: AutobiographyPage


class RecallPrompt(BaseModel):
    type: Literal["recall_prompt"] = "recall_prompt"
    text: str
    memory_id: str


class AudioMsg(BaseModel):
    type: Literal["audio"] = "audio"
    format: Literal["mp3"] = "mp3"
    b64: str


class ErrorMsg(BaseModel):
    type: Literal["error"] = "error"
    message: str


ServerMessage = Annotated[
    Union[
        ReasoningMsg,
        StageChange,
        AssistantMessage,
        AutobiographyPageMsg,
        RecallPrompt,
        AudioMsg,
        ErrorMsg,
    ],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# STEP 1 — Survey (초기 설문) data shapes
# ---------------------------------------------------------------------------
# The survey is a patient-facing conversational onboarding that SETS THE USER'S
# CONTEXT for the therapy flow. It uses its OWN WS endpoint
# (``/ws/survey/{session_id}``) and its OWN message unions — these are entirely
# separate from the therapy ClientMessage/ServerMessage above.

class SurveyQuestionData(BaseModel):
    """A single survey question rendered in the conversational UI.

    ``preface`` is an optional warm persona reaction to the PREVIOUS answer
    ("" on the very first question).
    """

    index: int
    total: int
    domain: str
    text: str
    preface: str = ""


class SurveyResult(BaseModel):
    """Final outcome of the survey: persona profile + seeded-memory summary."""

    patient_id: str
    name: str
    dementia_type: DementiaType
    # profile = {name, era, dementia_type, domains:{domainKey: answerText},
    #            recallable_keywords:[...], unrecallable_topics:[...], summary}
    profile: dict[str, Any] = Field(default_factory=dict)
    # ranked by frequency desc then first-seen, deduped
    recallable_keywords: list[str] = Field(default_factory=list)
    # human labels of domains the patient could not recall
    unrecallable_topics: list[str] = Field(default_factory=list)
    # 2-3 sentence Korean narrative profile
    summary: str = ""
    seeded_memory_count: int = 0
    completed_at: str = ""


# ---------------------------------------------------------------------------
# Survey WebSocket: Client -> Server
# ---------------------------------------------------------------------------

class StartSurvey(BaseModel):
    type: Literal["start_survey"] = "start_survey"
    patient_id: str | None = None
    name: str
    dementia_type: DementiaType


class SurveyAnswer(BaseModel):
    type: Literal["survey_answer"] = "survey_answer"
    text: str


class SkipQuestion(BaseModel):
    type: Literal["skip_question"] = "skip_question"


SurveyClientMessage = Annotated[
    Union[StartSurvey, SurveyAnswer, SkipQuestion],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Survey WebSocket: Server -> Client
# ---------------------------------------------------------------------------

class SurveyCaptureMsg(BaseModel):
    """Tier-1 extraction result for the PREVIOUS answer (not on the first turn)."""

    type: Literal["survey_capture"] = "survey_capture"
    domain: str
    answer: str
    keywords: list[str] = Field(default_factory=list)
    recallable: bool


class SurveyQuestionMsg(BaseModel):
    type: Literal["survey_question"] = "survey_question"
    index: int
    total: int
    domain: str
    text: str
    preface: str = ""


class SurveyCompleteMsg(BaseModel):
    type: Literal["survey_complete"] = "survey_complete"
    result: SurveyResult


# NOTE: ``ErrorMsg`` (type="error") is reused from the therapy union above.

SurveyServerMessage = Annotated[
    Union[SurveyCaptureMsg, SurveyQuestionMsg, SurveyCompleteMsg, ErrorMsg],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# REST request / response bodies
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    provider: str
    store: str
    # Effective per-capability backends, e.g. {"llm": "google", "tts": "mock", ...}.
    # Additive/optional: defaults to an empty dict for back-compat.
    providers: dict[str, str] = Field(default_factory=dict)


class CreatePatientRequest(BaseModel):
    name: str
    dementia_type: DementiaType


# List endpoints return bare arrays; these aliases document the element type.
MemoriesResponse = list[Memory]
AutobiographyResponse = list[AutobiographyPage]
RecallQueueResponse = list[RecallItem]


class CaregiverIntakeRequest(BaseModel):
    patient_id: str
    structured: dict[str, Any] = Field(default_factory=dict)


class OkResponse(BaseModel):
    ok: Literal[True] = True


class CommunitySimulateRequest(BaseModel):
    patient_id: str
    topic: str


class CommunitySimulateResponse(BaseModel):
    turns: list[CommunityTurn] = Field(default_factory=list)


class SttResponse(BaseModel):
    text: str


__all__ = [
    # enums / labels
    "DementiaType",
    "RecallStatus",
    "IntervalStage",
    "STAGE_LABELS",
    "stage_label",
    # data shapes
    "Patient",
    "Memory",
    "AutobiographyPage",
    "RecallItem",
    "CaregiverIntake",
    "ReasoningDecision",
    "CommunityTurn",
    # WS client -> server
    "StartSession",
    "UserMessage",
    "AdvanceTime",
    "ToggleTone",
    "ClientMessage",
    # WS server -> client
    "ReasoningMsg",
    "StageChange",
    "AssistantMessage",
    "AutobiographyPageMsg",
    "RecallPrompt",
    "AudioMsg",
    "ErrorMsg",
    "ServerMessage",
    # survey data shapes
    "SurveyQuestionData",
    "SurveyResult",
    # survey WS client -> server
    "StartSurvey",
    "SurveyAnswer",
    "SkipQuestion",
    "SurveyClientMessage",
    # survey WS server -> client
    "SurveyCaptureMsg",
    "SurveyQuestionMsg",
    "SurveyCompleteMsg",
    "SurveyServerMessage",
    # REST bodies
    "HealthResponse",
    "CreatePatientRequest",
    "MemoriesResponse",
    "AutobiographyResponse",
    "RecallQueueResponse",
    "CaregiverIntakeRequest",
    "OkResponse",
    "CommunitySimulateRequest",
    "CommunitySimulateResponse",
    "SttResponse",
]
