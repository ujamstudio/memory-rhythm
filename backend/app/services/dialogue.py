"""Dialogue service — the "입" (Dialogue LLM, GPT-4o-mini).

Turns the reasoner's *decision* into a warm, natural Korean utterance for the
patient. Called every turn, so it must be fast and low-latency (the dual-LLM
split exists precisely so heavy reasoning never blocks the spoken response).

  * mock  -> deterministic templated Korean phrases keyed by stage + hint_level
            (drives the scripted 시장 scenario, plan §10).
  * openai-> calls ``llm.complete`` with ``DIALOGUE_MODEL``.
"""

from __future__ import annotations

import logging
import random

from app.providers.base import DIALOGUE_MODEL, Providers

logger = logging.getLogger(__name__)

# How many recent transcript turns (user+assistant combined) to replay as
# messages so the "입" carries the conversation without blowing the token budget.
_HISTORY_TURNS = 8

# Stage 1 정서 안정화 — warm priming openers.
_STAGE1_LINES: tuple[str, ...] = (
    "안녕하세요~ 오늘 목소리 들으니 참 반가워요. 우리 천천히 도란도란 얘기 나눠요.",
    "여기 따뜻한 음악도 흐르네요. 잠깐 마음 푹 놓으셔도 돼요, 제가 곁에 있을게요.",
    "오늘 하루는 어떠셨어요? 서두르지 마시고, 편하게 이야기해 주세요.",
)

# Stage 2 대화형 인출 — utterance per hint level (0..4). The market scenario
# threads through these: open question -> category -> peripheral -> visual ->
# direct cue.
_STAGE2_LINES: dict[int, tuple[str, ...]] = {
    0: (
        "예전에 자주 가시던 곳, 혹시 떠오르는 데 있어요? 생각나는 대로 편하게 말해 주세요.",
        "젊으셨을 때 즐겨 가던 곳, 어디였을까요? 우리 같이 떠올려 봐요.",
    ),
    1: (
        "사람들 북적북적하고, 물건도 사고팔고 하던 그런 데는 어때요?",
        "동네에서 장 보러 다니던 곳, 우리 한번 떠올려 볼까요?",
    ),
    2: (
        "그곳 가면 어떤 소리가 들렸을까요? 흥정 소리에, 고소~한 냄새도 솔솔 났을 것 같은데요.",
        "이른 아침에 물건 진열하고, 단골손님이랑 인사 나누던 거 기억나세요?",
    ),
    3: (
        "이런 모습 떠오르세요? 좌판에 채소가 수북하고, 천막이 죽 늘어선 골목이요.",
        "장바구니 들고 좁은 골목 누비던 그 장면, 그림처럼 한번 그려 봐요.",
    ),
    4: (
        "혹시 '시장' 아니었어요? 채소 가게 하셨다고 들었거든요. 그 얘기 좀 들려주실래요?",
        "동네 '시장' 말이에요. 거기서 보낸 시간 떠오르면 살짝 들려주세요.",
    ),
}

# Stage 3 행동 수행 — affirm recall, narrate the page being added.
_STAGE3_LINES: tuple[str, ...] = (
    "와, 정말 멋진 기억이에요! 방금 그 이야기, 그림책 한 장에 살며시 담아 뒀어요. 오른쪽 한번 보세요.",
    "이렇게 소중한 얘기 들려주셔서 고마워요. 그 장면, 자서전에 한 페이지로 예쁘게 남겨 뒀답니다.",
    "그 시절이 눈앞에 그려지는 것 같아요. 오늘 이야기, 그림이랑 글로 정리해 뒀어요.",
)


class DialogueService:
    """Generates the spoken Korean turn from a reasoner decision."""

    def __init__(
        self,
        providers: Providers,
        use_mock: bool,
        dialogue_model: str = DIALOGUE_MODEL,
    ) -> None:
        self._providers = providers
        self._use_mock = use_mock
        # Resolved by the caller from the selected LLM backend (gpt-4o-mini /
        # gemini-2.5-flash / mock-dialogue). The mock path ignores it.
        self._model = dialogue_model
        # Recently spoken mock lines (this connection), so the templated path
        # doesn't repeat the same sentence on consecutive turns. The service is
        # built per WebSocket connection, so this is naturally per-session.
        self._recent: list[str] = []

    def _choose(self, pool: tuple[str, ...]) -> str:
        """Pick a templated line, avoiding the last couple we already used."""
        fresh = [ln for ln in pool if ln not in self._recent[-2:]]
        line = random.choice(fresh or list(pool))
        self._recent.append(line)
        if len(self._recent) > 4:
            self._recent = self._recent[-4:]
        return line

    async def say(self, decision: dict, context: dict | None = None) -> str:
        """Return a Korean utterance for the given decision.

        ``context`` may carry ``patient_name`` and the recalled ``keyword`` so the
        utterance can be personalized.
        """
        context = context or {}
        if self._use_mock:
            return self._say_mock(decision, context)
        return await self._say_openai(decision, context)

    # -- mock path ---------------------------------------------------------
    def _say_mock(self, decision: dict, context: dict) -> str:
        # The spoken line reflects the *stage about to be entered* so it feels
        # responsive: if the reasoner just advanced the stage, speak for it.
        next_stage = int(decision.get("next_stage", decision.get("stage", 1)))
        hint_level = max(0, min(int(decision.get("hint_level", 0)), 4))
        recall = bool(decision.get("recall_detected", False))

        if recall or next_stage == 3:
            return self._choose(_STAGE3_LINES)

        if next_stage <= 1:
            return self._choose(_STAGE1_LINES)

        # Stage 2 — pick by hint level. We intentionally do NOT echo the patient's
        # word back ("'…' 말씀이시군요"): the extracted keyword is often a filler or
        # greeting ('안녕하세요'/'글쎄요'), so parroting it reads as a broken bot.
        return self._choose(_STAGE2_LINES[hint_level])

    @staticmethod
    def _first_keyword(decision: dict) -> str:
        kws = decision.get("keywords") or []
        return kws[0] if kws else ""

    # -- openai path -------------------------------------------------------
    async def _say_openai(self, decision: dict, context: dict) -> str:
        stage = int(decision.get("next_stage", decision.get("stage", 1)))
        hint_level = int(decision.get("hint_level", 0))
        recall = bool(decision.get("recall_detected", False))
        keyword = context.get("keyword") or self._first_keyword(decision)
        patient_name = context.get("patient_name", "")
        # Whether we actually KNOW any real memory to lead with. Derive this from
        # lead_topics (= the patient's recall anchors: survey keywords + already
        # recalled memories) ONLY — NOT from `persona`, which always carries at
        # least the "성함: <이름>" line, so it would be truthy for every patient and
        # the no-fabrication branch below would be dead code. lead_topics is empty
        # exactly for the unsurveyed / first-meeting patient, which is when we must
        # ask open questions instead of inventing a specific memory.
        has_memories = bool([t for t in (context.get("lead_topics") or []) if t])

        hint_guide = {
            0: "열린 질문만 하고 단서는 주지 마세요.",
            1: "장소 '카테고리' 정도의 단서만 주세요.",
            2: "주변 기억(소리·냄새·사람)을 떠올리게 하세요.",
            3: "시각적 장면을 묘사해 떠올리게 하세요.",
            4: "부드럽게 직접 단서를 제시하세요.",
        }.get(hint_level, "")

        system = (
            "당신은 치매를 겪는 어르신의 '오랜 친구'입니다. 의사·상담사·기계가 아니라 곁에서 "
            "도란도란 이야기 나누는 정다운 벗처럼 말하세요. "
            "⚠️무엇보다 먼저, 어르신이 '방금 한 말'에 진심으로 반응하세요 — 질문을 하면 답하고, "
            "감정을 드러내면 공감하고, 다른 주제를 꺼내면 그 이야기를 함께 따라가세요. 어르신 말을 "
            "흘려듣고 곧장 옛 기억 질문으로 돌리면 '내 말을 안 들어준다'고 느낍니다. 절대 그러지 마세요. "
            "옛 기억을 함께 떠올리는 것은 좋은 일이지만 '목표'일 뿐, 매 턴 강요할 일이 아닙니다. "
            "대화가 자연스럽게 그쪽으로 흐를 때만 가볍게 곁들여 권하고, 한 번에 하나씩 천천히 하세요. "
            "따뜻한 해요체로 짧게(한두 문장) 건네고, 어르신이 편하게 말을 이어가도록 다정하게 받아 주세요. "
            "⚠️매 턴 똑같은 인사·감탄사·말머리를 반복하지 마세요(특히 '아이고'·'안녕하세요'·'그러셨구나'나 "
            "호칭으로 매번 시작 금지). 직전과 다르게 운을 떼고, 인사는 첫머리 한 번이면 충분합니다. "
            "성함은 가끔 자연스러울 때만 부르고, ⚠️모르면 지어내지 말고 호칭 없이 말하세요. "
            "정답을 강요하거나 시험하듯 묻지 마세요."
        )
        if recall or stage == 3:
            task = (
                f"어르신이 '{keyword or '소중한 추억'}'을(를) 떠올리셨어요! 오랜 친구처럼 "
                "진심으로 함께 기뻐해 주고, 그 추억을 그림책 한 장으로 살며시 남겨 뒀다고 "
                "다정하게 알려 주세요."
            )
        elif stage <= 1:
            task = "따뜻하게 안부를 묻고 어르신을 편안하게 해 주세요."
        elif has_memories:
            task = (
                "①먼저 방금 어르신 말씀에 충분히 반응하세요 — 질문이면 답하고, 감정이면 공감하고, "
                "다른 주제면 그 이야기를 함께 따라가세요. ②그러고 나서, 그 흐름이 옛 기억과 자연스럽게 "
                "이어진다면 아래 '함께 떠올려볼 추억' 중 하나를 가볍게 곁들여 물어볼 수 있어요. 하지만 "
                "어르신이 다른 이야기를 하거나 회상에 마음이 없어 보이면 억지로 돌리지 말고 그 흐름을 "
                "존중하세요. 매번 회상 질문으로 마무리하지 않아도 됩니다. 아는 기억만 화제로 삼고 "
                "구체적인 사물·장면을 지어내지 마세요. "
                f"(혹시 단서를 권한다면 그 수위: {hint_level}단계 — {hint_guide})"
            )
        else:
            # We do NOT yet know any real memory of this 어르신. Crucially, do not
            # invent one — instead respond first, then optionally invite a memory.
            task = (
                "아직 이 어르신의 구체적인 추억을 모릅니다. ①먼저 방금 말씀에 진심으로 반응·공감하거나 "
                "질문에 답하세요. ⚠️특정 장소·사물·사건·음식을 절대 지어내지 마세요('감나무'·'골목길 "
                "친구들' 같은 걸 만들면 안 됩니다). ②대화가 자연스러우면 '예전에 어떤 곳을 자주 가셨어요?' "
                "처럼 어르신이 스스로 추억을 꺼내도록 가볍게 열린 질문을 곁들이되, 다른 이야기를 하면 "
                "그걸 따라가세요. 한 번에 하나만."
            )

        name_hint = (
            f"어르신 성함: {patient_name} (매 턴 부르지 말고 가끔만 자연스럽게)."
            if patient_name
            else "어르신 성함은 아직 모릅니다. 이름을 지어내지 말고 호칭 없이 말하세요."
        )
        # Per-patient data (grows with the DB) + what the patient JUST said, so
        # the reply follows the actual conversation instead of a blind script.
        persona = (context.get("persona") or "").strip()
        user_text = (context.get("user_text") or "").strip()
        lead_topics = [t for t in (context.get("lead_topics") or []) if t][:6]
        parts: list[str] = []
        if name_hint:
            parts.append(name_hint)
        if persona:
            parts.append("[이 어르신에 대해 당신이 아는 것]\n" + persona)
        if lead_topics and (recall is False and stage >= 2):
            parts.append(
                "[자연스러우면 가볍게 곁들일 수 있는 추억]\n"
                + ", ".join(lead_topics)
                + "\n→ 대화 흐름이 맞을 때만 이 중 하나를 살짝 물어보세요. 억지로 돌리지는 마세요."
            )
        if user_text:
            parts.append(
                f'[방금 어르신 말씀 — 여기에 먼저 반응할 것]\n"{user_text}"\n'
                "→ 이 말에 진심으로 반응하세요: 질문이면 답하고, 감정이면 공감하고, 다른 주제면 그 "
                "이야기를 따라가세요. 회상으로 억지로 돌리지 마세요."
            )
        parts.append("[지금 할 일]\n" + task)
        parts.append(
            "오랜 친구답게 짧고 다정하게(두세 문장 이내) 건네세요. 위에 적힌 어르신의 실제 기억만 "
            "화제로 삼고, 구체적인 사물·사건·장면을 지어내지 마세요(목록에 없는 '감나무'·'특정 음식' "
            "같은 걸 만들지 말 것)."
        )
        parts.append(
            "⚠️중요: 위 대화 기록에서 당신(assistant)이 이미 한 인사·감탄사·말머리·호칭을 그대로 "
            "반복하지 말고, 직전 답변과 확연히 다르게 새 문장으로 시작하세요. 같은 말버릇이 반복되면 "
            "어르신이 같은 말을 되풀이한다고 느낍니다."
        )
        # Replay the recent conversation (both sides) as alternating messages so
        # the reply continues the thread like a chatbot. The current turn — with
        # persona/anti-generic/user_text — stays as the FINAL user message so the
        # guard instructions never get diluted by older turns. We only keep the
        # last N turns and always end on the current user message.
        history_msgs: list[dict] = []
        for item in (context.get("history") or [])[-_HISTORY_TURNS:]:
            text_item = str(item.get("text", "")).strip()
            if not text_item:
                continue
            role = "assistant" if item.get("role") == "assistant" else "user"
            history_msgs.append({"role": role, "content": text_item})
        messages = [
            {"role": "system", "content": system},
            *history_msgs,
            {"role": "user", "content": "\n\n".join(parts)},
        ]
        try:
            text = await self._providers.llm.complete(
                messages, model=self._model, temperature=0.7, max_tokens=320
            )
        except Exception as exc:  # pragma: no cover - runtime guard
            logger.warning(
                "입(dialogue) LLM 호출 실패 → mock 폴백: %s", exc, exc_info=True
            )
            return self._say_mock(decision, context)
        return (text or "").strip() or self._say_mock(decision, context)
