"""Survey service — STEP 1 초기 설문 (대화형 온보딩).

A patient-facing, AI-persona conversational onboarding that SETS THE USER'S
CONTEXT for the therapy flow. It conducts a thorough ~12-question survey across
life domains, with question text/emphasis BRANCHED BY DEMENTIA TYPE
(alzheimer / vascular / lewy), classifies each answer recallable vs unrecallable
(frequency + hesitation heuristic), and on completion builds a persona_profile,
seeds episodic memories into the SAME in-memory store keyed by ``patient_id``,
and persists a :class:`~app.schemas.SurveyResult`.

Everything works FULLY OFFLINE in mock mode: questions are scripted, the
classification is heuristic, and the summary is templated. When the LLM backend
is real (``providers.llm.backend != "mock"``) the summary is LLM-generated, with
a deterministic fallback to the template on any error.

State lives in ``app.store`` keyed by ``session_id`` (a :class:`SurveyState`),
so this service stays stateless beyond the store.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Awaitable, Callable

from app.providers.base import Providers
from app.schemas import (
    SurveyCaptureMsg,
    SurveyCompleteMsg,
    SurveyQuestionData,
    SurveyQuestionMsg,
    SurveyResult,
)
from app.services.memory import MemoryService
from app.store import Store, SurveyState, now_iso

# Hesitation markers — if any appears in an answer (or the answer is empty/skip)
# the answer is treated as unrecallable regardless of keyword count.
_HESITATION_MARKERS: tuple[str, ...] = (
    "모르",
    "기억 안",
    "기억이 안",
    "글쎄",
    "생각이 안",
    "잘 모",
    "몰라",
    "가물",
    "흐릿",
    "...",
    "…",
    "기억나지",
    "기억이 나지",
)

# Human-readable Korean labels per domain key (for unrecallable_topics + UI).
DOMAIN_LABELS: dict[str, str] = {
    "name_era": "이름과 시대",
    "childhood_place": "어린 시절 고향",
    "family": "가족",
    "work": "직업과 일",
    "daily_routine": "하루 일과",
    "food": "음식",
    "music_media": "노래와 영화",
    "season_nature": "계절과 자연",
    "relationships": "사람들과의 인연",
    "hardship": "힘들었던 시절",
    "cherished_memory": "소중한 추억",
    "hope_message": "전하고 싶은 말",
    # Recent-memory probes (alzheimer) — likely unrecallable.
    "recent_meal": "오늘 아침 식사 (최근 기억)",
    "recent_visitor": "어제 만난 사람 (최근 기억)",
}


# ---------------------------------------------------------------------------
# Question bank — genuinely branched by dementia type.
# Each entry is {"domain": <key>, "text": <Korean question>}. ~12 per type.
# ---------------------------------------------------------------------------

# alzheimer: lead with well-preserved REMOTE memories to build confidence, then
# intersperse RECENT-memory probes (recent_meal / recent_visitor) which are
# likely classified UNRECALLABLE. Warm, repetition-tolerant phrasing.
_QUESTIONS_ALZHEIMER: tuple[dict[str, str], ...] = (
    {"domain": "name_era", "text": "안녕하세요, 어르신. 천천히 말씀해 주세요. 성함이 어떻게 되시고, 어느 해에 태어나셨는지 기억나세요?"},
    {"domain": "childhood_place", "text": "어린 시절을 보내신 고향은 어떤 곳이었나요? 그 동네 풍경이 떠오르시나요?"},
    {"domain": "family", "text": "어릴 적 부모님이나 형제자매분들은 어떤 분들이셨어요? 함께한 기억이 있으세요?"},
    {"domain": "recent_meal", "text": "그런데 오늘 아침에는 무엇을 드셨는지 기억나세요?"},
    {"domain": "work", "text": "젊으셨을 때는 어떤 일을 하셨나요? 가장 오래 하신 일이 무엇이었어요?"},
    {"domain": "food", "text": "예전에 즐겨 드시던 음식이나 어머니가 해주시던 음식이 있으셨나요?"},
    {"domain": "music_media", "text": "젊은 시절 좋아하시던 노래나 영화가 있으셨어요? 흥얼거리시던 곡이 있나요?"},
    {"domain": "recent_visitor", "text": "어제는 누구와 이야기를 나누셨는지 기억나세요?"},
    {"domain": "cherished_memory", "text": "지금도 가슴에 가장 따뜻하게 남아 있는 추억은 무엇인가요?"},
    {"domain": "relationships", "text": "살면서 가장 의지가 되었던 분은 누구셨나요?"},
    {"domain": "hardship", "text": "살아오시면서 힘들었지만 잘 이겨내셨던 시절도 있으셨지요. 어떤 때였나요?"},
    {"domain": "hope_message", "text": "마지막으로, 지금 곁에 있는 가족에게 전하고 싶은 말씀이 있으세요?"},
)

# vascular: shorter, more CONCRETE/STRUCTURED, fact-oriented questions (one clear
# thing at a time); fewer open-ended; gentle, sequential.
_QUESTIONS_VASCULAR: tuple[dict[str, str], ...] = (
    {"domain": "name_era", "text": "성함을 말씀해 주시겠어요? 태어나신 해도 함께요."},
    {"domain": "childhood_place", "text": "고향은 어디였나요? 도시였나요, 시골이었나요?"},
    {"domain": "family", "text": "형제자매는 몇 분이셨어요?"},
    {"domain": "work", "text": "주로 하셨던 일은 무엇이었나요? 한 가지만 말씀해 주세요."},
    {"domain": "daily_routine", "text": "예전에 아침에 일어나시면 가장 먼저 무엇을 하셨어요?"},
    {"domain": "food", "text": "가장 좋아하시는 음식 한 가지는 무엇인가요?"},
    {"domain": "music_media", "text": "좋아하시는 노래가 한 곡 있으신가요?"},
    {"domain": "season_nature", "text": "사계절 중에 어느 계절을 가장 좋아하세요?"},
    {"domain": "relationships", "text": "가장 가까운 분은 누구신가요? 한 분만 떠올려 보세요."},
    {"domain": "cherished_memory", "text": "가장 기뻤던 날을 하나만 떠올려 보시겠어요?"},
    {"domain": "hardship", "text": "가장 힘들었던 일은 무엇이었나요? 짧게 말씀해 주셔도 좋아요."},
    {"domain": "hope_message", "text": "가족에게 한마디 남기신다면 어떤 말씀을 하시겠어요?"},
)

# lewy: include VISUAL/scene-based prompts and acknowledge FLUCTUATION; gentler
# pacing.
_QUESTIONS_LEWY: tuple[dict[str, str], ...] = (
    {"domain": "name_era", "text": "편안하게 말씀해 주세요. 성함과 태어나신 해가 떠오르시나요? 기억나는 날도, 흐릿한 날도 있으시지요."},
    {"domain": "childhood_place", "text": "어린 시절 고향을 떠올리면 어떤 장면이 눈앞에 그려지시나요? 그 풍경을 한번 그려봐 주세요."},
    {"domain": "family", "text": "가족이 함께 모여 있던 한 장면을 떠올려 보시겠어요? 누가 보이시나요?"},
    {"domain": "work", "text": "일하시던 모습을 그려보면 어떤 장면이 떠오르세요? 어떤 곳이었나요?"},
    {"domain": "food", "text": "밥상 위에 어떤 음식이 놓여 있는 장면이 그려지시나요? 그 색과 냄새가 떠오르세요?"},
    {"domain": "music_media", "text": "좋아하시던 노래를 떠올리면 어떤 장면이 함께 떠오르나요?"},
    {"domain": "season_nature", "text": "가장 좋아하시는 계절의 풍경을 한번 그려봐 주세요. 지금 눈앞에 보이시나요?"},
    {"domain": "relationships", "text": "함께 있으면 마음이 편했던 분의 얼굴이 그려지시나요? 어떤 모습인가요?"},
    {"domain": "cherished_memory", "text": "가장 따뜻했던 한 장면을 떠올려 보세요. 어떤 장면이 그려지시나요?"},
    {"domain": "hardship", "text": "힘들었던 시절의 한 장면도 있으시지요. 떠오르는 만큼만 말씀해 주세요."},
    {"domain": "daily_routine", "text": "예전에 하루를 보내시던 모습을 그려보면 어떤 장면이 보이세요?"},
    {"domain": "hope_message", "text": "마지막으로, 사랑하는 사람에게 전하고 싶은 말씀을 떠오르는 대로 들려주세요."},
)

_QUESTION_BANK: dict[str, tuple[dict[str, str], ...]] = {
    "alzheimer": _QUESTIONS_ALZHEIMER,
    "vascular": _QUESTIONS_VASCULAR,
    "lewy": _QUESTIONS_LEWY,
}

# Domains whose answers are EXPECTED to probe recent memory (alzheimer); even a
# fluent-looking answer here is informative, but these are the ones most likely
# to land in unrecallable_topics. (Classification is still driven by the answer.)
_RECENT_PROBE_DOMAINS: frozenset[str] = frozenset({"recent_meal", "recent_visitor"})

# Emit callback type: accepts a pydantic model or dict, returns an awaitable.
EmitFn = Callable[[Any], Awaitable[None]]


class SurveyService:
    """Conversational survey: question bank + classification + build/seed.

    Provider-aware: the completion summary is templated in mock mode and
    LLM-generated when ``providers.llm.backend != "mock"``.
    """

    def __init__(self, providers: Providers, store: Store) -> None:
        self._providers = providers
        self._store = store
        self._memory = MemoryService(providers, store)

    @property
    def _is_real_llm(self) -> bool:
        return self._providers.llm.backend != "mock"

    # -- lifecycle ---------------------------------------------------------
    async def start(
        self,
        session_id: str,
        patient_id: str | None,
        name: str,
        dementia_type: str,
        emit: EmitFn,
    ) -> None:
        """Create/get the patient, init survey state, emit the first question."""
        dt = dementia_type if dementia_type in _QUESTION_BANK else "alzheimer"
        clean_name = (name or "").strip() or "어르신"

        # Reuse an existing patient when an id is supplied + known; otherwise
        # create a fresh one (id may be supplied to fix the id, e.g. demo).
        patient = self._store.get_patient(patient_id) if patient_id else None
        if patient is None:
            patient = self._store.create_patient(
                name=clean_name,
                dementia_type=dt,
                patient_id=patient_id or None,
            )

        questions = [dict(q) for q in _QUESTION_BANK[dt]]
        state = SurveyState(
            session_id=session_id,
            patient_id=patient.id,
            name=clean_name,
            dementia_type=dt,
            questions=questions,
            index=0,
        )
        self._store.set_survey_state(session_id, state)

        await emit(self._question_msg(state, preface=""))

    async def answer(self, session_id: str, text: str, emit: EmitFn) -> None:
        """Classify the current answer, emit capture, then advance/complete."""
        await self._record(session_id, text, skipped=False, emit=emit)

    async def skip(self, session_id: str, emit: EmitFn) -> None:
        """Treat the current question as a declined/unrecallable answer."""
        await self._record(session_id, "", skipped=True, emit=emit)

    # -- internals ---------------------------------------------------------
    async def _record(
        self, session_id: str, text: str, skipped: bool, emit: EmitFn
    ) -> None:
        state = self._store.get_survey_state(session_id)
        if state is None:
            from app.schemas import ErrorMsg  # local import: avoid top churn

            await emit(ErrorMsg(message="설문 세션을 찾을 수 없습니다. 다시 시작해 주세요."))
            return
        if state.index >= len(state.questions):
            return  # already complete; ignore stray answers

        current = state.questions[state.index]
        domain = current["domain"]
        answer_text = (text or "").strip()

        keywords = self._memory.extract_keywords(answer_text)
        hesitated = skipped or self._is_hesitation(answer_text)
        recallable = (not hesitated) and len(keywords) >= 1

        # Persist the raw answer + classification into state.
        state.answers[domain] = answer_text
        if recallable:
            state.recallable.append({"text": answer_text, "keywords": keywords})
            for kw in keywords:
                state.keyword_freq[kw] = state.keyword_freq.get(kw, 0) + 1
        else:
            state.unrecallable.append(domain)
        state.index += 1
        self._store.set_survey_state(session_id, state)

        # Emit the capture for the answer we just processed.
        await emit(
            SurveyCaptureMsg(
                domain=domain,
                answer=answer_text,
                keywords=keywords,
                recallable=recallable,
            )
        )

        # Next question, or completion.
        if state.index >= len(state.questions):
            result = await self._build_and_seed(state)
            await emit(SurveyCompleteMsg(result=result))
        else:
            preface = self._preface(state, recallable, keywords)
            await emit(self._question_msg(state, preface=preface))

    def _question_msg(self, state: SurveyState, preface: str) -> SurveyQuestionMsg:
        q = state.questions[state.index]
        data = SurveyQuestionData(
            index=state.index,
            total=len(state.questions),
            domain=q["domain"],
            text=q["text"],
            preface=preface,
        )
        return SurveyQuestionMsg(**data.model_dump())

    def _is_hesitation(self, text: str) -> bool:
        if not text:
            return True
        return any(marker in text for marker in _HESITATION_MARKERS)

    def _preface(
        self, state: SurveyState, recallable: bool, keywords: list[str]
    ) -> str:
        """Warm persona reaction to the previous answer (mock-templated)."""
        if not recallable:
            return "괜찮습니다, 천천히 떠오르는 만큼만 말씀해 주셔도 좋아요."
        if keywords:
            return f"'{keywords[0]}' 이야기, 참 정겹게 들려요. 조금 더 여쭤볼게요."
        return "말씀 감사합니다. 다음으로 넘어가 볼게요."

    # -- build + seed ------------------------------------------------------
    async def _build_and_seed(self, state: SurveyState) -> SurveyResult:
        """Rank keywords, seed recallable memories, build + persist the result."""
        # Ranked recallable keywords: frequency desc, then first-seen, deduped.
        counter = Counter(state.keyword_freq)
        first_seen = list(state.keyword_freq.keys())
        recallable_keywords = sorted(
            first_seen,
            key=lambda k: (-counter[k], first_seen.index(k)),
        )[:12]

        # Human labels for the domains the patient could not recall (deduped,
        # order-preserving).
        seen_topics: list[str] = []
        for domain in state.unrecallable:
            label = DOMAIN_LABELS.get(domain, domain)
            if label not in seen_topics:
                seen_topics.append(label)
        unrecallable_topics = seen_topics

        # SEED: store each recallable answer as a recalled episodic memory under
        # the SAME patient_id so the therapy flow + autobiography + memories REST
        # automatically see them.
        seeded = 0
        for item in state.recallable:
            text = item["text"]
            if not text:
                continue
            await self._memory.store_memory(
                patient_id=state.patient_id,
                text=text,
                keywords=item["keywords"],
                recall_status="recalled",
            )
            seeded += 1

        era = self._infer_era(state.answers.get("name_era", ""))
        summary = await self._make_summary(
            state, recallable_keywords, seeded
        )

        profile: dict[str, Any] = {
            "name": state.name,
            "era": era,
            "dementia_type": state.dementia_type,
            "domains": dict(state.answers),
            "recallable_keywords": recallable_keywords,
            "unrecallable_topics": unrecallable_topics,
            "summary": summary,
        }

        result = SurveyResult(
            patient_id=state.patient_id,
            name=state.name,
            dementia_type=state.dementia_type,  # type: ignore[arg-type]
            profile=profile,
            recallable_keywords=recallable_keywords,
            unrecallable_topics=unrecallable_topics,
            summary=summary,
            seeded_memory_count=seeded,
            completed_at=now_iso(),
        )

        # Persist: survey result + patient persona_profile (back-compat str).
        self._store.save_survey_result(state.patient_id, result)
        self._store.update_patient_profile(state.patient_id, summary)
        return result

    def _infer_era(self, name_era_answer: str) -> str:
        """Best-effort era extraction from the name/era answer (4-digit year)."""
        import re

        if not name_era_answer:
            return ""
        match = re.search(r"(18|19|20)\d{2}", name_era_answer)
        if match:
            return f"{match.group(0)}년생"
        return ""

    async def _make_summary(
        self, state: SurveyState, recallable_keywords: list[str], seeded: int
    ) -> str:
        """Templated narrative in mock mode; LLM-generated when real (fallback)."""
        template = self._template_summary(state, recallable_keywords, seeded)
        if not self._is_real_llm:
            return template
        try:
            return await self._llm_summary(state, recallable_keywords, seeded, template)
        except Exception:
            # Deterministic fallback — never let a flaky LLM break completion.
            return template

    def _template_summary(
        self, state: SurveyState, recallable_keywords: list[str], seeded: int
    ) -> str:
        """A warm 2-3 sentence Korean narrative built from name + top keywords."""
        name = state.name
        top = recallable_keywords[:4]
        if top:
            kw_phrase = ", ".join(f"'{k}'" for k in top)
            first = (
                f"{name} 어르신은 {kw_phrase} 와(과) 같은 기억을 또렷이 간직하고 계십니다."
            )
        else:
            first = f"{name} 어르신과 함께 지난 삶의 이야기를 천천히 나누었습니다."
        second = (
            f"이번 대화에서 {seeded}개의 소중한 기억을 함께 모았습니다."
        )
        if state.unrecallable:
            third = "최근의 일은 흐릿할 때가 있지만, 오래된 추억은 따뜻하게 살아 있습니다."
        else:
            third = "앞으로의 대화에서도 이 기억들을 다정하게 이어가려 합니다."
        return f"{first} {second} {third}"

    async def _llm_summary(
        self,
        state: SurveyState,
        recallable_keywords: list[str],
        seeded: int,
        fallback: str,
    ) -> str:
        """Summarize the profile warmly in 2-3 Korean sentences via the LLM."""
        domains_text = "\n".join(
            f"- {DOMAIN_LABELS.get(d, d)}: {a}"
            for d, a in state.answers.items()
            if a
        )
        keywords_text = ", ".join(recallable_keywords) or "(없음)"
        messages = [
            {
                "role": "system",
                "content": (
                    "당신은 치매 어르신을 따뜻하게 돕는 인지 동반자입니다. "
                    "어르신의 초기 설문 답변을 바탕으로, 어르신의 삶과 성품을 "
                    "존중하는 2~3문장의 한국어 페르소나 요약을 작성하세요. "
                    "존댓말을 쓰고, 추측을 덧붙이지 말고 답변에 드러난 사실만 사용하세요."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"어르신 성함: {state.name}\n"
                    f"치매 유형: {state.dementia_type}\n"
                    f"또렷한 기억 키워드: {keywords_text}\n"
                    f"답변 모음:\n{domains_text}\n\n"
                    "위 내용을 2~3문장의 따뜻한 한국어 요약으로 작성해 주세요."
                ),
            },
        ]
        text = await self._providers.llm.complete(
            messages,
            model=self._reasoning_model,
            temperature=0.6,
            max_tokens=220,
        )
        text = (text or "").strip()
        return text or fallback

    @property
    def _reasoning_model(self) -> str:
        from app.config import get_settings

        return get_settings().reasoning_model
