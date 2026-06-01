"""Community simulator — virtual peer-persona group chat (plan §STEP 3).

Generates a short group conversation among N virtual peer personas on a given
topic (typically a recalled keyword), simulating the "소속 공동체" feature that
turns episodic recall into semantic, shared memory.

  * mock  -> deterministic, persona-flavored Korean turns templated by topic.
  * openai-> a single LLM call producing JSON turns, with a deterministic
            fallback so the demo never breaks.
"""

from __future__ import annotations

from app.providers.base import DIALOGUE_MODEL, Providers
from app.schemas import CommunityTurn

# Fixed cast of warm, age-appropriate peer personas.
PERSONAS: tuple[dict[str, str], ...] = (
    {"name": "박영자", "trait": "활달하고 옛날이야기를 즐겨 하는 분"},
    {"name": "이정숙", "trait": "차분하고 공감을 잘 해 주는 분"},
    {"name": "최복동", "trait": "유머가 많고 농담을 좋아하는 분"},
)

# Topic-flavored opener fragments for the mock path.
_TOPIC_HOOKS: dict[str, tuple[str, str, str]] = {
    "시장": (
        "아이고, 시장 이야기 나오니 반갑네요. 저도 장날만 되면 새벽부터 나갔잖아요.",
        "맞아요, 시장 골목 그 냄새가 아직도 생생해요. 두부 사러 가던 길이 떠오르네요.",
        "허허, 나는 시장에서 국밥 한 그릇 먹는 재미로 살았지요. 그때가 좋았어요.",
    ),
}

_GENERIC_HOOKS: tuple[str, str, str] = (
    "그 이야기 들으니 옛 생각이 절로 나네요. 저도 비슷한 추억이 있어요.",
    "정말 공감돼요. 그 시절엔 다들 그렇게 정 나누며 살았지요.",
    "허허, 듣고 보니 저도 한마디 보태고 싶네요. 참 따뜻한 기억이에요.",
)

_FOLLOWUPS: tuple[str, str, str] = (
    "다음에 우리 같이 그 시절 이야기 더 나눠 봐요. 함께하니 든든하네요.",
    "이렇게 같은 추억을 나누는 분들이 있어 참 다행이에요.",
    "오늘 이야기 정말 즐거웠어요. 또 이런 자리 자주 만들어요.",
)


class CommunityService:
    """Simulates a peer group chat for the community / belonging feature."""

    def __init__(
        self,
        providers: Providers,
        use_mock: bool,
        dialogue_model: str = DIALOGUE_MODEL,
    ) -> None:
        self._providers = providers
        self._use_mock = use_mock
        # Group chat is spoken by the "입" (dialogue) LLM; resolved by the caller
        # from the selected backend (gpt-4o-mini / gemini-2.5-flash).
        self._model = dialogue_model

    async def simulate(self, topic: str, n_turns: int = 3) -> list[CommunityTurn]:
        """Return a list of :class:`CommunityTurn` on ``topic``."""
        if self._use_mock:
            return self._simulate_mock(topic)
        return await self._simulate_openai(topic, n_turns)

    # -- mock path ---------------------------------------------------------
    def _simulate_mock(self, topic: str) -> list[CommunityTurn]:
        topic = (topic or "추억").strip()
        hooks = None
        for key, lines in _TOPIC_HOOKS.items():
            if key in topic:
                hooks = lines
                break
        if hooks is None:
            hooks = _GENERIC_HOOKS

        turns: list[CommunityTurn] = []
        for persona, hook in zip(PERSONAS, hooks):
            turns.append(CommunityTurn(persona=persona["name"], text=hook))
        # A closing warm follow-up from the first persona.
        turns.append(CommunityTurn(persona=PERSONAS[0]["name"], text=_FOLLOWUPS[0]))
        return turns

    # -- openai path -------------------------------------------------------
    async def _simulate_openai(self, topic: str, n_turns: int) -> list[CommunityTurn]:
        roster = ", ".join(f"{p['name']}({p['trait']})" for p in PERSONAS)
        system = (
            "당신은 치매 회복 커뮤니티의 또래 그룹 대화를 시뮬레이션합니다. "
            f"등장인물: {roster}. "
            "주어진 주제로 따뜻하고 공감 어린 한국어 그룹 대화를 만들되, "
            "각 인물의 성격이 드러나게 하세요. JSON 배열만 출력합니다."
        )
        user = (
            f"주제: '{topic}'. {n_turns + 1}개의 대화 turn을 만들어 주세요. "
            '형식: [{"persona": "이름", "text": "발화"}, ...]'
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            data = await self._providers.llm.complete_json(
                messages,
                model=self._model,
                schema_hint='[{"persona": "박영자", "text": "..."}]',
            )
            turns = self._coerce_turns(data)
            if turns:
                return turns
        except Exception:  # pragma: no cover - runtime guard
            pass
        return self._simulate_mock(topic)

    @staticmethod
    def _coerce_turns(data) -> list[CommunityTurn]:
        # complete_json may return a dict wrapping the array (e.g. {"turns":[...]})
        items = data
        if isinstance(data, dict):
            for key in ("turns", "items", "conversation", "messages"):
                if isinstance(data.get(key), list):
                    items = data[key]
                    break
            else:
                items = []
        out: list[CommunityTurn] = []
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and it.get("persona") and it.get("text"):
                    out.append(
                        CommunityTurn(
                            persona=str(it["persona"]), text=str(it["text"])
                        )
                    )
        return out
