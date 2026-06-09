"""Orchestrator — the per-turn pipeline (the demo's state machine driver).

Wires together the reasoner (두뇌), dialogue (입), memory, autobiography and the
in-memory store to drive the scripted demo scenario (plan §10).

Public API (used by ``app/ws.py``):
  * ``Orchestrator.handle_user_message(session_id, text, emit)``
  * ``Orchestrator.handle_advance_time(session_id, days, emit)``
  * ``Orchestrator.handle_toggle_tone(session_id, on, emit)``
  * ``Orchestrator.start_session(session_id, patient_id)``  (auto-creates a demo patient)

``emit`` is an async (or sync) callable that delivers one server->client WS
message dict. The orchestrator emits, per user turn and IN THIS ORDER:
  reasoning -> [stage_change] -> [autobiography_page] -> assistant_message
              -> [audio].

A module-level :func:`get_orchestrator` builds the singleton from
``app.config.get_settings`` + ``app.providers.get_providers`` so the WS/router
layer can grab it with no constructor arguments.
"""

from __future__ import annotations

import base64
import inspect
from typing import Any, Awaitable, Callable

from app.providers.base import DIALOGUE_MODEL, REASONING_MODEL, Providers
from app.schemas import stage_label
from app.services.autobiography import AutobiographyService
from app.services.community import CommunityService
from app.services.dialogue import DialogueService
from app.services.memory import MemoryService
from app.services.reasoner import _RECALL_KEYWORDS as REASONER_RECALL_KEYWORDS
from app.services.reasoner import Reasoner
from app.store import RECALL_INTERVALS, SessionState, Store, get_store

Emit = Callable[[dict], Any]


async def _emit(emit: Emit, message: dict) -> None:
    """Call ``emit`` whether it is sync or async."""
    result = emit(message)
    if inspect.isawaitable(result):
        await result


class Orchestrator:
    """Drives the Stage 1/2/3 conversation loop for one process."""

    def __init__(
        self,
        providers: Providers,
        store: Store,
        reasoner: Reasoner,
        dialogue: DialogueService,
        memory: MemoryService,
        autobiography: AutobiographyService,
        community: CommunityService,
    ) -> None:
        self._providers = providers
        self._store = store

        self.reasoner = reasoner
        self.dialogue = dialogue
        self.memory = memory
        self.autobiography = autobiography
        self.community = community

    # -- session lifecycle -------------------------------------------------
    async def start_session(
        self, session_id: str, patient_id: str = ""
    ) -> SessionState:
        """Bind a session to a patient, auto-creating a demo patient if needed."""
        patient = self._store.ensure_demo_patient(patient_id or None)
        state = self._store.get_or_create_session_state(session_id, patient.id)
        state.patient_id = patient.id
        return state

    # -- per user turn -----------------------------------------------------
    async def handle_user_message(
        self, session_id: str, text: str, emit: Emit
    ) -> None:
        """Run the full per-turn pipeline and emit WS messages via ``emit``."""
        state = self._store.get_or_create_session_state(session_id)
        if not state.patient_id:
            patient = self._store.ensure_demo_patient()
            state.patient_id = patient.id

        patient = self._store.get_patient(state.patient_id)
        patient_name = patient.name if patient else ""

        # Personalize the recall test to THIS patient: load their real recall
        # anchors (survey keywords + already-recalled memories) once, so the
        # reasoner (두뇌) judges recall against the person's own memories — not
        # only the demo's generic 시장 baseline. Empty for an unsurveyed demo
        # patient, which preserves the scripted baseline behavior.
        if not state.recall_anchors:
            state.recall_anchors = self.memory.recall_anchors(state.patient_id)

        # Record the utterance BEFORE deciding so the reasoner sees it in history.
        # Snapshot the prior transcript (everything up to but NOT including this
        # turn) so the dialogue LLM gets the running conversation as messages.
        history = list(state.transcript)
        state.user_texts.append(text)
        # Only thread non-empty turns into the replayed transcript so the history
        # stays a clean, alternating user/assistant sequence (Gemini requires
        # ``contents`` to start with a user turn and alternate roles).
        text_has_content = bool(text and text.strip())
        if text_has_content:
            state.transcript.append({"role": "user", "text": text})

        # 1) Reasoner decision (두뇌) + measured latency.
        decision, latency_ms, model = await self.reasoner.decide(state, text)
        await _emit(
            emit,
            {
                "type": "reasoning",
                "decision": decision,
                "latency_ms": round(latency_ms, 2),
                "model": model,
            },
        )

        prev_stage = state.stage
        next_stage = int(decision.get("next_stage", prev_stage))

        # Update the running state machine.
        state.hint_level = int(decision.get("hint_level", state.hint_level))
        if prev_stage == 2 or next_stage == 2:
            state.stage2_turns += 1

        # Tier-1 keyword collection.
        turn_keywords = self.memory.extract_keywords(text)
        for kw in decision.get("keywords", []) + turn_keywords:
            if kw and kw not in state.collected_keywords:
                state.collected_keywords.append(kw)

        # 2) Stage change.
        if next_stage != prev_stage:
            state.stage = next_stage
            await _emit(
                emit,
                {
                    "type": "stage_change",
                    "stage": next_stage,
                    "label": stage_label(next_stage),
                },
            )

        # 3) Recall handling -> create/mark memory, build autobiography page.
        recall_keyword = ""
        if decision.get("recall_detected"):
            recall_keyword = self._pick_recall_keyword(
                decision, turn_keywords, state.recall_anchors
            )
            memory = await self._record_recall(state, text, recall_keyword)
            if memory.id not in state.recalled_memory_ids:
                state.recalled_memory_ids.append(memory.id)

            page = await self.autobiography.build_page(
                patient_id=state.patient_id,
                session_id=session_id,
                memory_text=memory.text,
                keyword=recall_keyword,
                patient_name=patient_name,
            )
            await _emit(emit, {"type": "autobiography_page", "page": page.model_dump()})

            # 5) Register the 1/3/7/21-day forgetting-curve recall items.
            prompt_text = self._recall_prompt_text(recall_keyword)
            self._store.add_recall_items(
                memory_id=memory.id,
                text=prompt_text,
                from_day=state.advanced_days,
                intervals=RECALL_INTERVALS,
            )

        # 4) Dialogue utterance (입) — personalized per patient from the
        # accumulating store (profile + recalled memories + keywords), so the
        # friend "knows" this person and grows with them.
        persona = self.memory.persona_brief(state.patient_id)
        utterance = await self.dialogue.say(
            decision,
            context={
                "patient_name": patient_name,
                "keyword": recall_keyword,
                "persona": persona,
                "user_text": text,
                # The patient's real memories for the dialogue to LEAD toward,
                # so the AI proactively steers recall instead of just reacting.
                "lead_topics": state.recall_anchors,
                # Conversation so far (excludes this turn's user_text, which the
                # dialogue service re-attaches as the personalized current turn).
                "history": history,
            },
        )
        # Persist the AI turn so the next turn's dialogue keeps the thread (only
        # when this was a real, non-empty exchange — keeps alternation intact).
        if text_has_content and utterance and utterance.strip():
            state.transcript.append({"role": "assistant", "text": utterance})
        await _emit(
            emit,
            {
                "type": "assistant_message",
                "text": utterance,
                "stage": state.stage,
                "hint_level": state.hint_level,
            },
        )

        # Optional TTS audio (omitted entirely when mock returns empty bytes).
        await self._maybe_emit_audio(utterance, emit)

        self._store.set_session_state(session_id, state)

    # -- time acceleration -------------------------------------------------
    async def handle_advance_time(
        self, session_id: str, days: int, emit: Emit
    ) -> None:
        """Advance the simulated clock and fire any now-due recall prompts."""
        state = self._store.get_or_create_session_state(session_id)
        state.advanced_days += max(0, int(days))

        # A single memory registers four forgetting-curve items (1/3/7/21d). A
        # big time jump can make several of them due at once — but firing them
        # all together would bury the patient in duplicate prompts for the SAME
        # memory and undercut the "spaced repetition" story. So we surface only
        # the EARLIEST due item per memory this advance; the rest stay queued for
        # the next jump (true interval-by-interval re-test).
        due = self._store.due_recall_items(state.advanced_days)
        seen_memory_ids: set[str] = set()
        for item in sorted(due, key=lambda it: it.interval_stage):
            if item.memory_id in seen_memory_ids:
                continue
            seen_memory_ids.add(item.memory_id)
            await _emit(
                emit,
                {
                    "type": "recall_prompt",
                    "text": item.text,
                    "memory_id": item.memory_id,
                },
            )
            # Fire once: remove from the queue after emitting.
            self._store.pop_recall_item(item.id)

        self._store.set_session_state(session_id, state)

    # -- tone toggle (server just acks; frontend plays audio) --------------
    async def handle_toggle_tone(
        self, session_id: str, on: bool, emit: Emit
    ) -> None:
        state = self._store.get_or_create_session_state(session_id)
        state.tone_on = bool(on)
        self._store.set_session_state(session_id, state)
        # No dedicated ack message type in the contract; state is updated so the
        # next reasoning turn can reflect the 40Hz priming context if desired.

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _pick_recall_keyword(
        decision: dict, turn_keywords: list[str], recall_anchors: list[str] | None = None
    ) -> str:
        """Choose the most concrete recalled keyword for the page/narrative.

        Prefer THIS patient's own recall anchor (e.g. "나물") so the autobiography
        page, narrative and forgetting-curve prompt all center on their real
        memory; fall back to a generic *place* keyword (e.g. "시장") for the demo
        baseline, then any concrete token over filler like "맞다". An anchor/place
        may appear as a substring of a token (e.g. "시장에" contains "시장"), so we
        match on containment, not just equality.
        """
        candidates = list(decision.get("keywords", [])) + list(turn_keywords)
        for anchor in recall_anchors or []:
            for kw in candidates:
                if anchor and anchor in kw:
                    return anchor
        for kw in candidates:
            for place in REASONER_RECALL_KEYWORDS:
                if place in kw:
                    return place
        for kw in candidates:
            if kw:
                return kw
        return "추억"

    async def _record_recall(
        self, state: SessionState, text: str, keyword: str
    ) -> Any:
        """Create (or reuse) a recalled Memory for this turn."""
        memory_text = text.strip() or keyword or "소중한 기억"
        memory = await self.memory.store_memory(
            patient_id=state.patient_id,
            text=memory_text,
            keywords=([keyword] if keyword else []) + state.collected_keywords[:3],
            recall_status="recalled",
        )
        return memory

    @staticmethod
    def _recall_prompt_text(keyword: str) -> str:
        kw = keyword or "그때"
        if kw in ("추억", "그때", ""):
            return "지난번에 들려주신 이야기, 조금 더 들려주실래요?"
        return f"지난번 '{kw}' 이야기 참 좋았어요. 그 이야기 더 들려주실래요?"

    async def _maybe_emit_audio(self, text: str, emit: Emit) -> None:
        """Synthesize TTS and emit an ``audio`` message; skip when empty (mock)."""
        try:
            audio_bytes = await self._providers.tts.synthesize(text)
        except Exception:  # pragma: no cover - runtime guard
            audio_bytes = b""
        if not audio_bytes:
            return
        b64 = base64.b64encode(audio_bytes).decode("ascii")
        await _emit(emit, {"type": "audio", "format": "mp3", "b64": b64})


# ---------------------------------------------------------------------------
# Module-level singleton factory
# ---------------------------------------------------------------------------

_orchestrator: Orchestrator | None = None


def build_orchestrator(settings: Any, providers: Providers) -> Orchestrator:
    """Construct an :class:`Orchestrator` and its sub-services.

    The LLM-backed sub-services run in mock mode when the *resolved* LLM
    provider is the mock one. We read that from the provider ``backend`` tag
    (NOT from settings) so it stays correct even after a credential fallback
    (e.g. ``LLM_PROVIDER=google`` with no key transparently becomes mock).
    The resolved reasoning/dialogue model names come from ``settings`` so they
    follow the selected LLM backend (gpt-4o / gemini-2.5-flash / mock-*).
    """
    store = get_store()
    llm_is_mock = getattr(providers.llm, "backend", "mock") == "mock"
    reasoning_model = getattr(settings, "reasoning_model", REASONING_MODEL)
    dialogue_model = getattr(settings, "dialogue_model", DIALOGUE_MODEL)

    reasoner = Reasoner(providers, use_mock=llm_is_mock, reasoning_model=reasoning_model)
    dialogue = DialogueService(
        providers, use_mock=llm_is_mock, dialogue_model=dialogue_model
    )
    memory = MemoryService(providers, store)
    autobiography = AutobiographyService(
        providers, store, use_mock=llm_is_mock, narrative_model=reasoning_model
    )
    community = CommunityService(
        providers, use_mock=llm_is_mock, dialogue_model=dialogue_model
    )

    return Orchestrator(
        providers=providers,
        store=store,
        reasoner=reasoner,
        dialogue=dialogue,
        memory=memory,
        autobiography=autobiography,
        community=community,
    )


def get_orchestrator() -> Orchestrator:
    """Return the process-wide orchestrator, building it on first use.

    Imports ``get_settings`` / ``get_providers`` lazily so this module has no
    import-time dependency on files owned by other agents.
    """
    global _orchestrator
    if _orchestrator is None:
        from app.config import get_settings  # owned by config agent
        from app.providers import get_providers  # owned by providers agent

        settings = get_settings()
        providers = get_providers(settings)
        _orchestrator = build_orchestrator(settings, providers)
    return _orchestrator
