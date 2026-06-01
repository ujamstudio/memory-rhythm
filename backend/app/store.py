"""In-memory store (singleton) for the Memory Rhythm demo.

Backs *everything* the demo needs with plain Python dicts — no database is
required to run. Real pg/pgvector/neo4j/redis clients land in M1 under
``app/db/``; for the demo this module is the single source of truth.

Tables (dicts keyed by id):
  * patients          : patient_id -> Patient
  * memories          : memory_id  -> Memory   (carries an embedding sidecar)
  * pages             : page_id    -> AutobiographyPage
  * recall_queue      : item_id    -> RecallItem (+ due-day sidecar for the
                        demo's "시간 가속" toggle)
  * intake            : patient_id -> CaregiverIntake
  * session_state     : session_id -> SessionState (stage/hint/context machine)

IDs are generated from ``uuid4().hex``; timestamps use ``datetime.now(timezone.utc)``.
The store also owns a monotonic counter used for autobiography page ordering and
any other deterministic sequencing the demo needs.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.schemas import (
    AutobiographyPage,
    CaregiverIntake,
    Memory,
    Patient,
    RecallItem,
    SurveyResult,
)

# Interval stages for the forgetting-curve recall queue (days).
RECALL_INTERVALS: tuple[int, int, int, int] = (1, 3, 7, 21)


def new_id() -> str:
    """Return a fresh uuid4 hex id."""
    return uuid4().hex


def now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SessionState:
    """Per-session conversation state machine (the Redis ``session:{id}:state``
    of the demo). Kept entirely in memory and keyed by ``session_id``."""

    session_id: str
    patient_id: str = ""
    stage: int = 1
    hint_level: int = 0
    # Rolling history of recent user utterances (used by the mock reasoner to
    # decide hint escalation when the patient hesitates).
    user_texts: list[str] = field(default_factory=list)
    # Keywords collected across the whole session (Tier-1 extraction output).
    collected_keywords: list[str] = field(default_factory=list)
    # Number of *substantive* turns spent inside Stage 2 (hesitation counter).
    stage2_turns: int = 0
    # Memory ids recalled during this session (so we don't double-build pages).
    recalled_memory_ids: list[str] = field(default_factory=list)
    # Simulated "now" offset in days, advanced by the advance_time toggle.
    advanced_days: int = 0
    tone_on: bool = False


@dataclass
class SurveyState:
    """Per-survey conversation state for STEP 1 — 초기 설문, keyed by ``session_id``.

    Holds the branched question bank (already selected for the patient's dementia
    type), the running index, and the accumulating classification buffers used to
    build the persona profile + seed episodic memories on completion.
    """

    session_id: str
    patient_id: str = ""
    name: str = ""
    dementia_type: str = "alzheimer"
    # Branched question bank: list of {"domain": str, "text": str}.
    questions: list[dict] = field(default_factory=list)
    # Index of the NEXT question to ask (0-based).
    index: int = 0
    # domainKey -> answer text (the raw answers, including unrecallable ones).
    answers: dict[str, str] = field(default_factory=dict)
    # Recallable answer keyword lists accumulated (for seeding).
    recallable: list[dict] = field(default_factory=list)
    # Domain keys classified unrecallable (the patient could not recall).
    unrecallable: list[str] = field(default_factory=list)
    # Keyword frequency across recallable answers (insertion-ordered).
    keyword_freq: dict[str, int] = field(default_factory=dict)


class Store:
    """In-memory repository singleton."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counter = 0

        self.patients: dict[str, Patient] = {}
        self.memories: dict[str, Memory] = {}
        # Sidecar: memory_id -> embedding vector (kept out of the pydantic model).
        self.memory_vectors: dict[str, list[float]] = {}
        self.pages: dict[str, AutobiographyPage] = {}
        self.recall_queue: dict[str, RecallItem] = {}
        # Sidecar: recall item_id -> due offset in days from session start.
        self.recall_due_days: dict[str, int] = {}
        self.intake: dict[str, CaregiverIntake] = {}
        self.session_state: dict[str, SessionState] = {}
        # STEP 1 — Survey: per-session conversation state, keyed by session_id.
        self.survey_state: dict[str, SurveyState] = {}
        # STEP 1 — Survey: completed results, keyed by patient_id.
        self.survey_results: dict[str, SurveyResult] = {}

    # -- counter -----------------------------------------------------------
    def next_seq(self) -> int:
        """Store-managed monotonic counter (page ordering, deterministic seq)."""
        with self._lock:
            self._counter += 1
            return self._counter

    # -- patients ----------------------------------------------------------
    def create_patient(
        self,
        name: str,
        dementia_type: str,
        persona_profile: str = "",
        patient_id: str | None = None,
    ) -> Patient:
        with self._lock:
            pid = patient_id or new_id()
            patient = Patient(
                id=pid,
                name=name,
                dementia_type=dementia_type,  # type: ignore[arg-type]
                persona_profile=persona_profile,
                created_at=now_iso(),
            )
            self.patients[pid] = patient
            return patient

    def get_patient(self, patient_id: str) -> Patient | None:
        return self.patients.get(patient_id)

    def update_patient_profile(self, patient_id: str, summary: str) -> Patient | None:
        """Set a patient's ``persona_profile`` to ``summary`` (back-compat str).

        Used by the survey on completion so the therapy flow reads the freshly
        built persona narrative. Returns the updated patient (or ``None`` if the
        id is unknown).
        """
        with self._lock:
            patient = self.patients.get(patient_id)
            if patient is None:
                return None
            updated = patient.model_copy(update={"persona_profile": summary})
            self.patients[patient_id] = updated
            return updated

    def ensure_demo_patient(self, patient_id: str | None = None) -> Patient:
        """Return an existing patient, or auto-create a demo patient.

        Used by ``start_session`` when the client omits / sends an unknown id so
        the conversation loop always has someone to talk to (zero-secrets demo).
        """
        with self._lock:
            if patient_id and patient_id in self.patients:
                return self.patients[patient_id]
            return self.create_patient(
                name="김순자",
                dementia_type="alzheimer",
                persona_profile=(
                    "1947년생. 젊은 시절 동네 시장에서 채소 가게를 하셨습니다. "
                    "딸 둘, 손주 셋. 트로트와 옛날 영화를 좋아하십니다."
                ),
                patient_id=patient_id or None,
            )

    # -- memories ----------------------------------------------------------
    def add_memory(
        self,
        patient_id: str,
        text: str,
        keywords: list[str] | None = None,
        recall_status: str = "unrecalled",
        embedding: list[float] | None = None,
    ) -> Memory:
        with self._lock:
            mid = new_id()
            memory = Memory(
                id=mid,
                patient_id=patient_id,
                text=text,
                keywords=keywords or [],
                recall_status=recall_status,  # type: ignore[arg-type]
                created_at=now_iso(),
            )
            self.memories[mid] = memory
            if embedding is not None:
                self.memory_vectors[mid] = embedding
            return memory

    def get_memory(self, memory_id: str) -> Memory | None:
        return self.memories.get(memory_id)

    def set_memory_vector(self, memory_id: str, embedding: list[float]) -> None:
        with self._lock:
            self.memory_vectors[memory_id] = embedding

    def mark_memory_recalled(self, memory_id: str) -> Memory | None:
        with self._lock:
            mem = self.memories.get(memory_id)
            if mem is None:
                return None
            updated = mem.model_copy(update={"recall_status": "recalled"})
            self.memories[memory_id] = updated
            return updated

    def list_memories(self, patient_id: str) -> list[Memory]:
        return [m for m in self.memories.values() if m.patient_id == patient_id]

    def list_memory_vectors(self, patient_id: str) -> list[tuple[Memory, list[float]]]:
        """Return (memory, vector) pairs for a patient that have an embedding."""
        out: list[tuple[Memory, list[float]]] = []
        for m in self.memories.values():
            if m.patient_id == patient_id and m.id in self.memory_vectors:
                out.append((m, self.memory_vectors[m.id]))
        return out

    # -- autobiography pages ----------------------------------------------
    def add_page(
        self,
        patient_id: str,
        session_id: str,
        image_url: str,
        narrative: str,
        order_idx: int | None = None,
    ) -> AutobiographyPage:
        with self._lock:
            page = AutobiographyPage(
                id=new_id(),
                patient_id=patient_id,
                session_id=session_id,
                image_url=image_url,
                narrative=narrative,
                order_idx=order_idx if order_idx is not None else self.next_seq(),
            )
            self.pages[page.id] = page
            return page

    def list_pages(self, patient_id: str) -> list[AutobiographyPage]:
        pages = [p for p in self.pages.values() if p.patient_id == patient_id]
        pages.sort(key=lambda p: p.order_idx)
        return pages

    # -- recall queue ------------------------------------------------------
    def add_recall_items(
        self,
        memory_id: str,
        text: str,
        from_day: int = 0,
        intervals: tuple[int, ...] = RECALL_INTERVALS,
    ) -> list[RecallItem]:
        """Register 1/3/7/21-day forgetting-curve items for a recalled memory.

        ``from_day`` is the session's current simulated day offset; due dates are
        computed both as real ISO timestamps (for display) and as a day offset
        sidecar (for the demo's time-acceleration toggle).
        """
        with self._lock:
            created: list[RecallItem] = []
            base = datetime.now(timezone.utc)
            for interval in intervals:
                item_id = new_id()
                due = base + timedelta(days=interval)
                item = RecallItem(
                    id=item_id,
                    memory_id=memory_id,
                    text=text,
                    due_at=due.isoformat(),
                    interval_stage=interval,  # type: ignore[arg-type]
                )
                self.recall_queue[item_id] = item
                self.recall_due_days[item_id] = from_day + interval
                created.append(item)
            return created

    def list_recall_items(self, patient_id: str) -> list[RecallItem]:
        """Recall items whose backing memory belongs to ``patient_id``."""
        out: list[RecallItem] = []
        for item in self.recall_queue.values():
            mem = self.memories.get(item.memory_id)
            if mem is not None and mem.patient_id == patient_id:
                out.append(item)
        out.sort(key=lambda i: self.recall_due_days.get(i.id, 0))
        return out

    def due_recall_items(self, current_day: int) -> list[RecallItem]:
        """Items due at or before ``current_day`` (the advanced simulated day).

        Returned in ascending due-day order; the orchestrator removes them as it
        emits recall prompts so each item fires once.
        """
        due = [
            self.recall_queue[item_id]
            for item_id, day in self.recall_due_days.items()
            if day <= current_day and item_id in self.recall_queue
        ]
        due.sort(key=lambda i: self.recall_due_days.get(i.id, 0))
        return due

    def pop_recall_item(self, item_id: str) -> RecallItem | None:
        with self._lock:
            self.recall_due_days.pop(item_id, None)
            return self.recall_queue.pop(item_id, None)

    # -- caregiver intake --------------------------------------------------
    def save_intake(self, patient_id: str, structured: dict) -> CaregiverIntake:
        with self._lock:
            intake = CaregiverIntake(patient_id=patient_id, structured=structured)
            self.intake[patient_id] = intake
            return intake

    def get_intake(self, patient_id: str) -> CaregiverIntake | None:
        return self.intake.get(patient_id)

    # -- session state -----------------------------------------------------
    def get_session_state(self, session_id: str) -> SessionState | None:
        return self.session_state.get(session_id)

    def get_or_create_session_state(
        self, session_id: str, patient_id: str = ""
    ) -> SessionState:
        with self._lock:
            state = self.session_state.get(session_id)
            if state is None:
                state = SessionState(session_id=session_id, patient_id=patient_id)
                self.session_state[session_id] = state
            elif patient_id and not state.patient_id:
                state.patient_id = patient_id
            return state

    def set_session_state(self, session_id: str, state: SessionState) -> None:
        with self._lock:
            self.session_state[session_id] = state

    # -- survey state (STEP 1) --------------------------------------------
    def get_survey_state(self, session_id: str) -> SurveyState | None:
        return self.survey_state.get(session_id)

    def get_or_create_survey_state(
        self, session_id: str, patient_id: str = ""
    ) -> SurveyState:
        with self._lock:
            state = self.survey_state.get(session_id)
            if state is None:
                state = SurveyState(session_id=session_id, patient_id=patient_id)
                self.survey_state[session_id] = state
            elif patient_id and not state.patient_id:
                state.patient_id = patient_id
            return state

    def set_survey_state(self, session_id: str, state: SurveyState) -> None:
        with self._lock:
            self.survey_state[session_id] = state

    # -- survey results (STEP 1) ------------------------------------------
    def save_survey_result(self, patient_id: str, result: SurveyResult) -> SurveyResult:
        with self._lock:
            self.survey_results[patient_id] = result
            return result

    def get_survey_result(self, patient_id: str) -> SurveyResult | None:
        return self.survey_results.get(patient_id)


# Module-level singleton ----------------------------------------------------
_store: Store | None = None


def get_store() -> Store:
    """Return the process-wide :class:`Store` singleton."""
    global _store
    if _store is None:
        _store = Store()
    return _store
