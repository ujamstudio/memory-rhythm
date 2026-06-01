"""Dialogue service — the "입" (Dialogue LLM, GPT-4o-mini).

Turns the reasoner's *decision* into a warm, natural Korean utterance for the
patient. Called every turn, so it must be fast and low-latency (the dual-LLM
split exists precisely so heavy reasoning never blocks the spoken response).

  * mock  -> deterministic templated Korean phrases keyed by stage + hint_level
            (drives the scripted 시장 scenario, plan §10).
  * openai-> calls ``llm.complete`` with ``DIALOGUE_MODEL``.
"""

from __future__ import annotations

import random

from app.providers.base import DIALOGUE_MODEL, Providers

# Stage 1 정서 안정화 — warm priming openers.
_STAGE1_LINES: tuple[str, ...] = (
    "안녕하세요, 오늘 목소리가 참 좋으시네요. 천천히 저랑 이야기 나눠요.",
    "여기 따뜻한 음악과 함께 잠시 마음을 편히 가져 보실까요. 제가 곁에 있을게요.",
    "오늘 하루는 어떠셨어요? 서두르지 않으셔도 괜찮아요, 편하게 말씀해 주세요.",
)

# Stage 2 대화형 인출 — utterance per hint level (0..4). The market scenario
# threads through these: open question -> category -> peripheral -> visual ->
# direct cue.
_STAGE2_LINES: dict[int, tuple[str, ...]] = {
    0: (
        "옛날에 자주 가시던 곳이 있으셨어요? 떠오르는 대로 편히 말씀해 주세요.",
        "젊으셨을 적에 즐겨 찾던 장소가 있으셨나요?",
    ),
    1: (
        "혹시 사람들이 북적이고, 물건을 사고팔던 그런 곳은 어떠세요?",
        "동네에서 장 보러 다니시던 곳을 한번 떠올려 볼까요?",
    ),
    2: (
        "그곳에 가면 어떤 소리가 들렸을까요? 사람들 흥정 소리, 고소한 음식 냄새 같은 것들이요.",
        "이른 아침 물건을 진열하고, 단골손님과 인사 나누던 기억은 어떠세요?",
    ),
    3: (
        "이런 모습이 떠오르세요? 좌판에 채소가 가득 쌓이고, 천막이 줄지어 선 골목 말이에요.",
        "장바구니를 들고 좁은 골목을 누비던 장면, 그림처럼 떠올려 보실래요?",
    ),
    4: (
        "혹시 '시장' 아니었을까요? 채소 가게를 하셨다고 들었어요. 거기 이야기 조금 들려주시겠어요?",
        "동네 '시장' 말이에요. 그곳에서 보내신 시간이 떠오르시면 말씀해 주세요.",
    ),
}

# Stage 3 행동 수행 — affirm recall, narrate the page being added.
_STAGE3_LINES: tuple[str, ...] = (
    "정말 멋진 기억이에요. 방금 그 이야기를 그림책 한 장으로 담아 두었어요. 오른쪽을 한번 보세요.",
    "소중한 기억을 들려주셔서 고마워요. 그 장면을 자서전에 한 페이지로 남겼답니다.",
    "그 시절이 생생하게 느껴지네요. 오늘 이야기를 그림과 글로 정리해 두었어요.",
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
        keyword = context.get("keyword") or self._first_keyword(decision)

        if recall or next_stage == 3:
            line = random.choice(_STAGE3_LINES)
            return line

        if next_stage <= 1:
            return random.choice(_STAGE1_LINES)

        # Stage 2 — pick by hint level.
        line = random.choice(_STAGE2_LINES[hint_level])
        # If the patient surfaced a non-target keyword, gently acknowledge it.
        if keyword and hint_level < 4 and keyword not in ("시장", ""):
            return f"'{keyword}' 말씀이시군요. {line}"
        return line

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

        hint_guide = {
            0: "열린 질문만 하고 단서는 주지 마세요.",
            1: "장소 '카테고리' 정도의 단서만 주세요.",
            2: "주변 기억(소리·냄새·사람)을 떠올리게 하세요.",
            3: "시각적 장면을 묘사해 떠올리게 하세요.",
            4: "부드럽게 직접 단서를 제시하세요.",
        }.get(hint_level, "")

        system = (
            "당신은 치매 환자와 대화하는 따뜻한 '입'(Dialogue) 모듈입니다. "
            "두뇌가 내린 결정을 자연스러운 한국어 한두 문장으로 표현하세요. "
            "노년층이 편하게 느끼도록 천천히, 정답을 강요하지 말고 부드럽게 말하세요. "
            "존댓말을 사용하고 한 번에 한 가지만 물으세요."
        )
        if recall or stage == 3:
            instruction = (
                f"환자가 '{keyword or '소중한 장소'}'를 회상하는 데 성공했습니다. "
                "따뜻하게 칭찬하고, 그 기억을 자서전 그림책 한 페이지로 담았다고 알려 주세요."
            )
        elif stage <= 1:
            instruction = "정서 안정화 단계입니다. 따뜻하게 안부를 묻고 편안하게 해 주세요."
        else:
            instruction = (
                f"대화형 인출 단계입니다. 현재 힌트 수위 {hint_level}. {hint_guide}"
            )

        name_hint = f"환자 이름: {patient_name}. " if patient_name else ""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"{name_hint}{instruction}"},
        ]
        try:
            text = await self._providers.llm.complete(
                messages, model=self._model, temperature=0.7, max_tokens=160
            )
        except Exception:  # pragma: no cover - runtime guard
            return self._say_mock(decision, context)
        return (text or "").strip() or self._say_mock(decision, context)
