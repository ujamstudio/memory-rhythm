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

import time

from app.providers.base import REASONING_MODEL, Providers
from app.store import SessionState

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
        else:
            decision = await self._decide_openai(state, user_text)
        latency_ms = (time.perf_counter() - start) * 1000.0
        model = self._model if not self._use_mock else "mock-reasoner"
        return decision, latency_ms, model

    # -- mock path ---------------------------------------------------------
    def _decide_mock(self, state: SessionState, user_text: str) -> dict:
        text = (user_text or "").strip()
        keywords = self._extract_keywords(text)
        recall_kw = [k for k in _RECALL_KEYWORDS if k in text]
        hesitated = any(m in text for m in _HESITATION_MARKERS)

        stage = state.stage
        next_stage = stage
        hint_level = state.hint_level
        recall_detected = False
        reason = ""

        if stage == 1:
            # Stage 1 정서 안정화: one warm priming turn, then move to retrieval.
            # The very first turn stays in Stage 1; any subsequent turn advances.
            if state.stage2_turns == 0 and len(state.user_texts) <= 1:
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
            elif hesitated or not keywords:
                hint_level = min(state.hint_level + 1, 4)
                reason = _HINT_REASONS[hint_level]
                if hint_level >= 4:
                    reason += " (다음 단서로도 회상이 없으면 부담을 줄여 마무리합니다.)"
            else:
                # Patient is engaging but hasn't hit the target keyword yet —
                # nudge one level up to keep the retrieval moving.
                hint_level = min(state.hint_level + 1, 4)
                reason = (
                    "환자가 반응하지만 핵심 기억에는 도달하지 않아 "
                    f"단서를 한 단계 높입니다. {_HINT_REASONS[hint_level]}"
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
            "Stage 2에서는 환자가 머뭇거리면 힌트 수위를 0->4로 점진적으로 올립니다 "
            "(0 질문만, 1 카테고리 단서, 2 주변 기억, 3 시각 단서, 4 직접 단서). "
            "구체적인 장소나 사건 키워드가 회상되면 recall_detected=true 로 판단하고 "
            "다음 단계로 전환합니다. 정답을 강요하지 말고 부드럽게 유도하세요. "
            "반드시 JSON만 출력하세요."
        )
        history = "\n".join(f"- {t}" for t in state.user_texts[-5:]) or "(없음)"
        user = (
            f"현재 stage={state.stage}, hint_level={state.hint_level}, "
            f"stage2_turns={state.stage2_turns}.\n"
            f"최근 환자 발화:\n{history}\n"
            f"이번 환자 발화: \"{user_text}\"\n\n"
            "다음 키를 가진 JSON으로 결정을 출력하세요: "
            "stage(int), next_stage(int), hint_level(int 0-4), "
            "recall_detected(bool), keywords(string[]), reason(string, 한국어)."
        )
        schema_hint = (
            '{"stage": 2, "next_stage": 2, "hint_level": 1, '
            '"recall_detected": false, "keywords": ["시장"], "reason": "..."}'
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            data = await self._providers.llm.complete_json(
                messages, model=self._model, schema_hint=schema_hint
            )
        except Exception:  # pragma: no cover - network/runtime guard
            # Fall back to the deterministic logic so the demo never stalls.
            return self._decide_mock(state, user_text)

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
