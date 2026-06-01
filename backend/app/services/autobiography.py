"""Autobiography builder — picture-book page generator.

On a successful recall, builds one autobiography page:
  * image    -> ``ImageProvider.generate`` (gpt-image-1; mock = placeholder URI).
  * narrative-> ``LLMProvider.complete`` (GPT-4o; mock = templated Korean line).

Persists the page to the store (ordered via the store's monotonic counter) and
returns the :class:`AutobiographyPage` so the orchestrator can emit it.
"""

from __future__ import annotations

from app.providers.base import REASONING_MODEL, Providers
from app.schemas import AutobiographyPage
from app.store import Store

# Templated narrative fragments keyed by a recalled keyword, for the mock path.
_NARRATIVE_TEMPLATES: dict[str, str] = {
    "시장": (
        "이른 아침, 동네 시장 골목은 늘 활기로 가득했습니다. 좌판 위에 가지런히 "
        "쌓인 채소와 단골손님들의 정겨운 흥정 소리 속에서, 그분의 하루가 시작되곤 했지요."
    ),
    "장터": (
        "닷새마다 열리던 장터는 온 마을 사람들이 모이는 자리였습니다. 그 북적임 속에서 "
        "나눈 인사와 웃음이 오래도록 마음에 남아 있습니다."
    ),
    "학교": (
        "운동장의 흙냄새와 친구들의 웃음소리가 가득하던 학창 시절. 그 교실에서의 작은 "
        "순간들이 한 장의 그림처럼 떠오릅니다."
    ),
    "고향": (
        "굽이진 길을 따라 들어선 고향 마을. 익숙한 풍경과 사람들의 온기가 지금도 "
        "선명하게 마음을 데웁니다."
    ),
}

_DEFAULT_NARRATIVE = (
    "오늘 들려주신 이야기 속에는 따뜻한 시간이 담겨 있었습니다. 그 소중한 순간을 "
    "한 장의 그림으로 남겨 둡니다."
)


class AutobiographyService:
    """Builds and persists autobiography pages from recalled memories."""

    def __init__(
        self,
        providers: Providers,
        store: Store,
        use_mock: bool,
        narrative_model: str = REASONING_MODEL,
    ) -> None:
        self._providers = providers
        self._store = store
        self._use_mock = use_mock
        # Narrative is written by the "두뇌" (reasoning) LLM; resolved by the
        # caller from the selected backend (gpt-4o / gemini-2.5-flash).
        self._model = narrative_model

    async def build_page(
        self,
        patient_id: str,
        session_id: str,
        memory_text: str,
        keyword: str = "",
        patient_name: str = "",
    ) -> AutobiographyPage:
        """Generate image + narrative for a recalled memory and persist a page."""
        image_prompt = self._image_prompt(keyword, memory_text, patient_name)
        image_url = await self._providers.image.generate(image_prompt)
        narrative = await self._build_narrative(keyword, memory_text, patient_name)

        order_idx = self._store.next_seq()
        page = self._store.add_page(
            patient_id=patient_id,
            session_id=session_id,
            image_url=image_url,
            narrative=narrative,
            order_idx=order_idx,
        )
        return page

    # -- prompts / narrative ----------------------------------------------
    @staticmethod
    def _image_prompt(keyword: str, memory_text: str, patient_name: str) -> str:
        topic = keyword or memory_text or "소중한 추억"
        # Warm, nostalgic illustration style suitable for an elderly picture book.
        return (
            "Warm nostalgic Korean watercolor illustration for an elderly person's "
            f"autobiography picture book. Theme: {topic}. Memory: {memory_text}. "
            "Soft golden light, gentle storybook style, no text, calm and comforting."
        )

    async def _build_narrative(
        self, keyword: str, memory_text: str, patient_name: str
    ) -> str:
        if self._use_mock:
            base = _NARRATIVE_TEMPLATES.get(keyword)
            if base is None:
                # Try any template whose keyword appears in the memory text.
                for kw, tmpl in _NARRATIVE_TEMPLATES.items():
                    if kw in memory_text:
                        base = tmpl
                        break
            return base or _DEFAULT_NARRATIVE

        system = (
            "당신은 치매 환자의 자서전 그림책에 들어갈 narrative를 쓰는 작가입니다. "
            "환자가 회상한 기억을 따뜻하고 서정적인 한국어 2~3문장으로 응축하세요. "
            "3인칭의 부드러운 회고 어조를 사용하고, 과장 없이 진솔하게 쓰세요."
        )
        name_hint = f"환자 이름: {patient_name}. " if patient_name else ""
        user = (
            f"{name_hint}회상한 기억의 핵심 키워드: '{keyword or '추억'}'. "
            f"환자의 발화/기억: \"{memory_text}\". "
            "이 기억을 자서전 한 페이지의 narrative로 써 주세요."
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            text = await self._providers.llm.complete(
                messages, model=self._model, temperature=0.6, max_tokens=200
            )
        except Exception:  # pragma: no cover - runtime guard
            return _NARRATIVE_TEMPLATES.get(keyword, _DEFAULT_NARRATIVE)
        return (text or "").strip() or _DEFAULT_NARRATIVE
