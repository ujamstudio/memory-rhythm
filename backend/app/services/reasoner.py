"""Reasoner — the "두뇌" (Reasoning LLM, GPT-4o).

Responsible for the *decision*, not the wording:
  * Stage transition (1 정서 안정화 -> 2 대화형 인출 -> 3 행동 수행).
  * Hint escalation 0 -> 4 inside Stage 2 when the patient hesitates.
  * Recall-success judgement (a concrete place/keyword surfaced).

Returns a plain ``decision`` dict matching ``ReasoningDecision``:
``{stage, next_stage, hint_level, recall_detected, keywords, reason}``.

The reasoner measures its own latency (``time.perf_counter``) and reports the
model name so the frontend reasoning-chain panel can prove the dual-LLM split.

Two code paths:
  * mock  -> deterministic logic that makes the scripted "시장"(market) recall
            scenario work offline (hint escalation, then detect recall).
  * openai-> calls ``llm.complete_json`` with ``REASONING_MODEL``.
"""

from __future__ import annotations

import logging
import re
import time

from app.providers.base import REASONING_MODEL, Providers
from app.store import SessionState

logger = logging.getLogger(__name__)

# Concrete place/keyword tokens that count as a successful recall in the demo
# scenario. The headline target is "시장" (market) per plan §10.
_RECALL_KEYWORDS: tuple[str, ...] = (
    "시장", "장터", "장날", "가게", "채소", "노점", "골목",
    "학교", "교실", "고향", "바닷가", "바다", "기차", "역",
    "공장", "논", "밭", "우물", "마당", "절", "교회",
)

# Words that signal hesitation / "I can't remember" -> escalate the hint level.
_HESITATION_MARKERS: tuple[str, ...] = (
    "모르", "기억 안", "기억이 안", "글쎄", "생각이 안", "잘 모", "음...",
    "몰라", "기억 못", "가물", "떠오르지",
)

# Words that signal the patient is DENYING the AI's suggestion ("no, that's not
# it"). Critical: a denial must NEVER be read as recall, even when it repeats the
# target keyword ("시장은 아니야"). These are deliberately FULLER denial forms, not
# the bare interjection "아니" — elderly speakers routinely open an affirmative
# recall with the filler "아니, 글쎄…", and idioms like "아니나 다를까"/"여간 아닌" are
# positive, so a bare "아니"/"아닌" substring would wrongly suppress real recall.
_NEGATION_MARKERS: tuple[str, ...] = (
    "아니야", "아니에요", "아니예요", "아녜요", "아니라", "아니거든",
    "아닌데", "아냐", "그게 아니", "그건 아니", "그런 적 없", "그런 거 없",
    "한 적 없", "간 적 없", "안 갔", "안 가봤", "못 갔", "안 했",
    "맞지 않아", "맞지 않다", "틀렸", "틀려",
)

# Clause delimiters: a denial in one clause ("…은 안 갔어") must not wipe out a
# genuine recall in another ("시장만 갔지"), so negation is judged per clause.
_CLAUSE_SPLIT = re.compile(r"[,.!?]|말고|하지만|지만|는데")

# Korean reason strings for each hint level (shown verbatim in the panel).
_HINT_REASONS: dict[int, str] = {
    0: "열린 질문으로 부담 없이 회상을 시도합니다.",
    1: "환자가 머뭇거려 카테고리 단서(장소 범주)를 제시합니다.",
    2: "주변 기억(주변 사람·소리·냄새)으로 중심 기억을 유도합니다.",
    3: "시각 단서(사진·물건 이미지)를 떠올리게 합니다.",
    4: "직접 단서를 부드럽게 제시해 회상을 마무리합니다.",
}


class Reasoner:
    """The decision LLM. Stateless across calls except via ``SessionState``."""

    def __init__(
        self,
        providers: Providers,
        use_mock: bool,
        reasoning_model: str = REASONING_MODEL,
    ) -> None:
        self._providers = providers
        self._use_mock = use_mock
        # Resolved by the caller from the selected LLM backend (gpt-4o /
        # gemini-2.5-flash / mock-reasoner). Used both as the displayed model
        # name and as the model arg passed to the real LLM call.
        self._model = reasoning_model

    async def decide(
        self, state: SessionState, user_text: str
    ) -> tuple[dict, float, str]:
        """Return ``(decision_dict, latency_ms, model_name)``.

        Latency is measured around the actual decision computation so the panel
        reflects the real cost of the reasoning step. The reported model name is
        the resolved backend model, or ``"mock-reasoner"`` in mock mode.
        """
        start = time.perf_counter()
        if self._use_mock:
            decision = self._decide_mock(state, user_text)
            model = "mock-reasoner"
        else:
            decision = await self._decide_openai(state, user_text)
            # _decide_openai tags a runtime fallback (429/네트워크/파싱 실패) so the
            # reasoning panel tells the truth instead of claiming the live model
            # answered when it actually degraded to mock.
            fell_back = bool(decision.pop("_fell_back", False))
            model = f"{self._model} → mock 폴백" if fell_back else self._model
        latency_ms = (time.perf_counter() - start) * 1000.0
        return decision, latency_ms, model

    # -- mock path ---------------------------------------------------------
    def _decide_mock(self, state: SessionState, user_text: str) -> dict:
        text = (user_text or "").strip()
        keywords = self._extract_keywords(text)
        # Recall targets = this patient's REAL memories (state.recall_anchors,
        # from the survey + already-recalled memories) UNIONED with the demo's
        # generic place baseline. Anchors come first so the person's own memory
        # (나물·딸·…) is what gets celebrated; substring match catches '딸이랑'->'딸'.
        recall_targets = list(state.recall_anchors) + list(_RECALL_KEYWORDS)
        # Judge negation per clause so "시장 말고는 안 갔어, 시장만 갔지" keeps the real
        # 시장 recall (one clause denies, another affirms). A keyword only counts
        # when it appears in a clause that is NOT locally negated.
        recall_kw: list[str] = []
        any_negated_clause = False
        for clause in _CLAUSE_SPLIT.split(text):
            if any(m in clause for m in _NEGATION_MARKERS):
                any_negated_clause = True
                continue
            # len>=2 so a 1-char keyword never partial-matches inside a larger
            # word (e.g. '절' inside '시절' wrongly firing a recall on a goodbye).
            recall_kw += [k for k in recall_targets if k and len(k) >= 2 and k in clause]
        recall_kw = list(dict.fromkeys(recall_kw))  # dedupe, preserve order
        # Treat the turn as a denial only when nothing was genuinely recalled.
        negated = any_negated_clause and not recall_kw
        hesitated = any(m in text for m in _HESITATION_MARKERS)

        stage = state.stage
        next_stage = stage
        hint_level = state.hint_level
        recall_detected = False
        reason = ""

        if stage == 1:
            # Stage 1 정서 안정화 -> retrieval. Advance as soon as we are still in
            # Stage 1 and haven't started retrieval yet — do NOT gate on the turn
            # count. Gating on len(user_texts)<=1 stranded the session forever when
            # the live model conservatively kept Stage 1 on turn 1 and later turns
            # fell back to mock (by then len>1, so it could never advance).
            if state.stage2_turns == 0:
                next_stage = 2
                hint_level = 0
                reason = (
                    "정서 안정화 단계를 마치고 대화형 인출(Stage 2)로 전환합니다. "
                    "40Hz 톤과 따뜻한 priming 후 회상 질문을 시작합니다."
                )
            else:
                reason = "환자의 정서 상태를 안정시키며 라포를 형성합니다."

        elif stage == 2:
            # Stage 2 대화형 인출: escalate hints on hesitation; detect recall on
            # a concrete place keyword.
            if recall_kw:
                recall_detected = True
                next_stage = 3
                reason = (
                    f"구체적 장소 키워드 '{recall_kw[0]}' 회상 성공. "
                    "자서전 페이지를 생성하고 행동 수행(Stage 3)으로 전환합니다."
                )
            elif negated and not hesitated:
                # Patient denied the current lead (and is NOT also struggling —
                # a combined "아니야, 잘 모르겠어" should still escalate, handled by
                # the hesitation branch below). Do NOT advance and do NOT keep
                # pushing the same (wrong) cue — back off a notch and re-approach
                # from a different memory so we never insist on a rejected answer.
                hint_level = max(state.hint_level - 1, 0)
                reason = (
                    "환자가 방금 제안을 '아니라고' 부정했습니다. 그 단서는 접고, "
                    "단서 수위를 낮춰 다른 기억으로 부드럽게 화제를 바꿔 다시 접근합니다."
                )
            elif hesitated or not keywords:
                hint_level = min(state.hint_level + 1, 4)
                reason = _HINT_REASONS[hint_level]
                if hint_level >= 4:
                    reason += " (다음 단서로도 회상이 없으면 부담을 줄여 마무리합니다.)"
            else:
                # Patient is engaging (surfaced keywords, no hesitation) — HOLD
                # the current hint level and re-approach from another angle,
                # rather than force-escalating toward the direct cue. Escalation
                # is reserved for genuine hesitation, so we never push answers
                # onto someone who is actively recalling.
                hint_level = state.hint_level
                reason = (
                    "환자가 머뭇거림 없이 대화를 이어가고 있어, 단서 수위를 "
                    "유지한 채 같은 기억을 다른 각도에서 함께 떠올려 봅니다."
                )

        else:  # stage == 3
            # Stage 3 행동 수행: stay; further concrete keywords enrich the page.
            if recall_kw:
                recall_detected = True
                reason = (
                    f"추가 회상 '{recall_kw[0]}' 으로 자서전 서사를 보강합니다."
                )
            else:
                reason = "회상한 기억을 정리하고 세션을 마무리합니다."

        return {
            "stage": stage,
            "next_stage": next_stage,
            "hint_level": hint_level,
            "recall_detected": recall_detected,
            "keywords": keywords or recall_kw,
            "reason": reason,
        }

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        import re

        tokens = re.findall(r"[가-힣]+|[A-Za-z0-9]+", text)
        out: list[str] = []
        for t in tokens:
            if len(t) >= 2 and t not in out:
                out.append(t)
            if len(out) >= 6:
                break
        return out

    # -- openai path -------------------------------------------------------
    async def _decide_openai(self, state: SessionState, user_text: str) -> dict:
        system = (
            "당신은 치매 인지 치료를 지휘하는 '두뇌'(Reasoning) 모듈입니다. "
            "대화 흐름을 3단계로 운영합니다: "
            "1=정서 안정화, 2=대화형 인출, 3=행동 수행. "
            "⚠️Stage 1은 따뜻한 첫 인사 '한 번'이면 충분합니다. 환자가 한 번이라도 응답하면 "
            "지체 없이 next_stage=2(대화형 인출)로 전환하세요. 환자가 피곤함·회피·'기억이 안 난다'를 "
            "표현하더라도 Stage 1에 머무르지 말고, 단서 수위를 낮게(0~1) 시작하며 부드럽게 Stage 2로 "
            "이끄세요. Stage 1에 두 턴 이상 머무르면 안 됩니다. "
            "Stage 2에서는 환자가 머뭇거리면 힌트 수위를 0->4로 점진적으로 올립니다 "
            "(0 질문만, 1 카테고리 단서, 2 주변 기억, 3 시각 단서, 4 직접 단서). "
            "구체적인 장소나 사건 키워드가 회상되면 recall_detected=true 로 판단하고 "
            "다음 단계로 전환합니다. 특히 아래 '이 어르신이 또렷이 기억하는 단서'에 있는 "
            "내용을 환자가 말하면 그 사람만의 진짜 기억이므로 회상 성공으로 인정하세요. "
            "환자가 머뭇거림 없이 잘 따라오면 힌트를 올리지 말고 유지하세요. "
            "⚠️환자가 회상과 무관한 말(질문·감정 토로·다른 주제·잡담)을 하면 단서(hint)를 무리해서 "
            "올리지 말고 현재 수위를 유지하세요. 이건 '못 떠올림'이 아니라 '다른 이야기'이니, 입(dialogue)이 "
            "그 말에 먼저 반응하도록 두는 게 맞습니다. 회상으로 억지로 끌고 가지 마세요. "
            "⚠️환자가 '아니요/아니야/그런 적 없어'처럼 제안을 부정하면, 그 발화에 키워드가 들어 "
            "있더라도 절대 recall_detected=true로 보지 마세요(부정은 회상이 아닙니다). 그럴 땐 "
            "단계를 올리지 말고 그 단서는 접은 뒤 다른 기억으로 방향을 바꾸세요. "
            "정답을 강요하지 말고 부드럽게 유도하세요. 반드시 JSON만 출력하세요."
        )
        history = "\n".join(f"- {t}" for t in state.user_texts[-5:]) or "(없음)"
        anchors = ", ".join(state.recall_anchors[:12]) or "(아직 없음)"
        user = (
            f"현재 stage={state.stage}, hint_level={state.hint_level}, "
            f"stage2_turns={state.stage2_turns}.\n"
            f"이 어르신이 또렷이 기억하는 단서: {anchors}\n"
            f"최근 환자 발화:\n{history}\n"
            f"이번 환자 발화: \"{user_text}\"\n\n"
            "다음 키를 가진 JSON으로 결정을 출력하세요: "
            "stage(int), next_stage(int), hint_level(int 0-4), "
            "recall_detected(bool), keywords(string[]), reason(string, 한국어)."
        )
        schema_hint = (
            '{"stage": 2, "next_stage": 2, "hint_level": 1, '
            '"recall_detected": false, "keywords": ["..."], "reason": "..."}'
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            data = await self._providers.llm.complete_json(
                messages, model=self._model, schema_hint=schema_hint
            )
        except Exception as exc:  # pragma: no cover - network/runtime guard
            # Fall back to the deterministic logic so the demo never stalls — but
            # LOG it (429/auth/network is otherwise invisible) and tag the result
            # so the panel shows the real model degraded to mock.
            logger.warning(
                "두뇌(reasoner) LLM 호출 실패 → mock 폴백: %s", exc, exc_info=True
            )
            fallback = self._decide_mock(state, user_text)
            fallback["_fell_back"] = True
            return fallback

        # An empty/garbled JSON object means the parse failed silently — treat it
        # as a fallback (logged + tagged) rather than emitting an all-default
        # decision that would freeze the stage and never detect recall.
        if not data:
            logger.warning("두뇌(reasoner) JSON 파싱 실패(빈 객체) → mock 폴백")
            fallback = self._decide_mock(state, user_text)
            fallback["_fell_back"] = True
            return fallback

        return self._coerce_decision(data, state)

    @staticmethod
    def _coerce_decision(data: dict, state: SessionState) -> dict:
        """Validate/repair an LLM JSON decision into the contract shape."""

        def _int(value, default: int) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        keywords = data.get("keywords") or []
        if not isinstance(keywords, list):
            keywords = [str(keywords)]
        keywords = [str(k) for k in keywords]

        stage = _int(data.get("stage"), state.stage)
        next_stage = _int(data.get("next_stage"), stage)
        hint_level = max(0, min(_int(data.get("hint_level"), state.hint_level), 4))
        return {
            "stage": stage,
            "next_stage": max(1, min(next_stage, 3)),
            "hint_level": hint_level,
            "recall_detected": bool(data.get("recall_detected", False)),
            "keywords": keywords,
            "reason": str(data.get("reason", "")),
        }
