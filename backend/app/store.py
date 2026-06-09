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
    # Full chat transcript (both sides, time-ordered) so the dialogue LLM ("입")
    # can carry the conversation like a chatbot. Each item: {"role": "user"|
    # "assistant", "text": str}. Kept separate from user_texts so the reasoner's
    # user-only history assumptions stay intact.
    transcript: list[dict] = field(default_factory=list)
    # Keywords collected across the whole session (Tier-1 extraction output).
    collected_keywords: list[str] = field(default_factory=list)
    # This patient's REAL recall targets (설문 recallable_keywords + 이미 회상한
    # 기억의 키워드). Populated lazily on the first turn so the reasoner judges
    # recall against the person's own memories, not just the demo's 시장 baseline.
    recall_anchors: list[str] = field(default_factory=list)
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


@dataclass
class TimelineEventRow:
    """One caregiver-dashboard timeline event (WS4), mirroring the OpenAPI
    ``TimelineEvent`` shape. Derived from the live therapy WS conversation."""

    id: int
    timestamp: str
    # ai_message | patient_response | hint_given | mission_success | mission_fail
    type: str
    content: str
    hint_level: int | None = None
    mission_name: str | None = None


class Store:
    """In-memory repository singleton."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counter = 0
        # Optional persistence backend (SQLite). Duck-typed so this module never
        # imports the db layer (no circular import); wired in by app.main on boot.
        self._persist = None

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

        # Caregiver dashboard (WS4): a single "today" view derived from the live
        # therapy WS conversation. Demo-grade (one active patient at a time),
        # kept entirely in memory like everything else.
        self._timeline_seq = 0
        self._session_seq = 0
        self.timeline_events: list[TimelineEventRow] = []
        self.dashboard_sessions: dict[int, dict] = {}
        self.dashboard_started_at: datetime | None = None
        self.dashboard_patient_name: str = ""
        self.dashboard_stage: int = 1
        self.dashboard_hint_level: int = 0

    # -- persistence (optional, attached by app.main on boot) --------------
    def attach_persistence(self, persistence) -> None:
        """Attach a persistence backend and load any saved state into this store."""
        self._persist = persistence
        persistence.load_into(self)

    def persist(self) -> None:
        """Snapshot durable collections to the backend. No-op if none attached."""
        if self._persist is not None:
            self._persist.snapshot(self)

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

    # -- caregiver dashboard (WS4) ----------------------------------------
    def start_dashboard_session(self, patient_name: str) -> dict:
        """Begin a fresh "today" dashboard view for a therapy session.

        Resets the timeline so the dashboard reflects the CURRENT session, and
        records the start time for the duration stat. Returns the session row.
        """
        with self._lock:
            self._session_seq += 1
            self.timeline_events = []
            self.dashboard_started_at = datetime.now(timezone.utc)
            self.dashboard_patient_name = patient_name
            self.dashboard_stage = 1
            self.dashboard_hint_level = 0
            row = {
                "id": self._session_seq,
                "startedAt": self.dashboard_started_at.isoformat(),
                "status": "active",
                "patientName": patient_name,
            }
            self.dashboard_sessions[self._session_seq] = row
            return row

    def create_dashboard_session(self, patient_name: str) -> dict:
        """Create a session row WITHOUT resetting the timeline (POST /sessions)."""
        with self._lock:
            self._session_seq += 1
            if self.dashboard_started_at is None:
                self.dashboard_started_at = datetime.now(timezone.utc)
            if patient_name:
                self.dashboard_patient_name = patient_name
            row = {
                "id": self._session_seq,
                "startedAt": datetime.now(timezone.utc).isoformat(),
                "status": "active",
                "patientName": patient_name,
            }
            self.dashboard_sessions[self._session_seq] = row
            return row

    def append_timeline_event(
        self,
        type: str,
        content: str,
        hint_level: int | None = None,
        mission_name: str | None = None,
    ) -> TimelineEventRow:
        with self._lock:
            self._timeline_seq += 1
            row = TimelineEventRow(
                id=self._timeline_seq,
                timestamp=now_iso(),
                type=type,
                content=content,
                hint_level=hint_level,
                mission_name=mission_name,
            )
            self.timeline_events.append(row)
            return row

    def list_timeline_events(self, limit: int = 100) -> list[TimelineEventRow]:
        return self.timeline_events[-limit:]

    def set_dashboard_stage(self, stage: int) -> None:
        with self._lock:
            self.dashboard_stage = stage

    def set_dashboard_hint(self, hint_level: int) -> None:
        with self._lock:
            self.dashboard_hint_level = max(self.dashboard_hint_level, hint_level)

    def _count_events(self, *types: str) -> int:
        return sum(1 for e in self.timeline_events if e.type in types)

    def dashboard_phase(self) -> tuple[int, int]:
        """Map the therapy 3-stage machine onto the dashboard 4-phase model.

        Returns ``(currentPhase 1..4, progressPercent 0..100)``.
        """
        missions = self._count_events("mission_success")
        stage = self.dashboard_stage
        phase = min(stage, 3)
        if stage >= 3 and missions > 0:
            phase = 4
        base = (phase - 1) / 4 * 100
        within = (self.dashboard_hint_level / 4) * 25
        progress = min(100, round(base + within + (10 if missions else 0)))
        return phase, progress

    def today_summary(self) -> dict:
        """Aggregate the current session's timeline into the SessionSummary shape."""
        msgs = self._count_events("ai_message", "patient_response")
        hints = self._count_events("hint_given")
        missions = self._count_events("mission_success")
        fails = self._count_events("mission_fail")
        phase, _ = self.dashboard_phase()
        if self.dashboard_started_at is not None:
            secs = (datetime.now(timezone.utc) - self.dashboard_started_at).total_seconds()
            duration = max(0, int(secs // 60))
        else:
            duration = 0
        attempts = missions + fails
        success_rate = round(100 * missions / attempts) if attempts else (100 if missions else 0)
        return {
            "date": datetime.now(timezone.utc).date().isoformat(),
            "totalMessages": msgs,
            "hintsUsed": hints,
            "missionsCompleted": missions,
            "currentPhase": phase,
            "durationMinutes": duration,
            "successRate": float(success_rate),
        }

    def record_dashboard_hint(self, hint_level: int, mission_context: str = "") -> dict:
        """Append a hint_given timeline event and return the HintRecord shape."""
        content = mission_context or f"힌트 레벨 {hint_level} 사용"
        row = self.append_timeline_event("hint_given", content, hint_level=hint_level)
        self.set_dashboard_hint(hint_level)
        return {"id": row.id, "hintLevel": hint_level, "recordedAt": row.timestamp}


# Module-level singleton ----------------------------------------------------
_store: Store | None = None


def get_store() -> Store:
    """Return the process-wide :class:`Store` singleton."""
    global _store
    if _store is None:
        _store = Store()
    return _store
