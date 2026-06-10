"""Deterministic, offline, Korean mock providers.

These implementations let the entire demo run with **no API key and no
network**. Everything is deterministic so the scripted demo scenario
(plan §10, the "시장"/market recall) plays out the same way every time.

  * :class:`MockLLM`        - canned/templated Korean utterances; ``complete_json``
                              returns sensible reasoner decisions driven by simple
                              keyword + hesitation heuristics.
  * :class:`MockSTT`        - returns a fixed Korean demo line.
  * :class:`MockTTS`        - returns ``b""`` (frontend skips audio when empty).
  * :class:`MockImage`      - returns a deterministic inline-SVG ``data:`` URI so the
                              e-book shows a picture offline.
  * :class:`MockEmbedding`  - deterministic hashed pseudo-vectors of dim ``EMBEDDING_DIM``.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from urllib.parse import quote

from app.providers.base import (
    EMBEDDING_DIM,
    REASONING_MODEL,
    EmbeddingProvider,
    ImageProvider,
    LLMProvider,
    STTProvider,
    TTSProvider,
)

# ---------------------------------------------------------------------------
# Demo heuristics: keywords that signal a concrete recalled place/memory.
# The scripted scenario centers on "시장"(market); we accept a small family of
# concrete nouns so the recall feels natural during a live demo.
# ---------------------------------------------------------------------------

# Concrete place / object keywords that count as a successful recall.
RECALL_KEYWORDS: tuple[str, ...] = (
    "시장",
    "장터",
    "어머니",
    "엄마",
    "손",
    "생선",
    "고등어",
    "콩나물",
    "두부",
    "떡",
    "국밥",
    "골목",
    "바다",
    "고향",
    "학교",
    "딸",
    "아들",
    "남편",
    "아내",
)

# Hesitation / "I can't remember" signals that should escalate the hint level.
HESITATION_PATTERNS: tuple[str, ...] = (
    "모르",
    "기억",
    "글쎄",
    "잘 모",
    "생각이 안",
    "생각 안",
    "안 나",
    "안나",
    "없",
    "흐릿",
    "가물",
    "헷갈",
    "...",
    "음",
    "어…",
)

# Lightweight Korean keyword bank for Tier-1 extraction in mock mode.
_KEYWORD_BANK: tuple[str, ...] = RECALL_KEYWORDS + (
    "봄",
    "여름",
    "가을",
    "겨울",
    "아침",
    "저녁",
    "냄새",
    "노래",
    "꽃",
    "비",
    "눈",
    "강아지",
    "친구",
    "결혼",
    "잔치",
)


def _norm(text: str) -> str:
    return (text or "").strip().lower()


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(n in text for n in needles)


def _extract_keywords(text: str, limit: int = 4) -> list[str]:
    """Tier-1 keyword extraction: pick known bank words present in the text,
    then back-fill with longer raw tokens. Deterministic and order-stable."""
    found: list[str] = []
    for kw in _KEYWORD_BANK:
        if kw in text and kw not in found:
            found.append(kw)
    if len(found) < limit:
        for token in re.findall(r"[가-힣]{2,}", text):
            if token not in found:
                found.append(token)
            if len(found) >= limit:
                break
    return found[:limit]


class MockLLM(LLMProvider):
    """Templated Korean text + heuristic JSON decisions."""

    backend = "mock"

    async def complete(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Return a warm Korean utterance.

        The dialogue service ("입") passes the reasoner decision + context as a
        ``system``/``user`` message pair. We read the last user content and any
        embedded hints to pick a calm, encouraging line. Fully offline.
        """
        last_user = ""
        system = ""
        for m in messages:
            role = m.get("role")
            if role == "user":
                last_user = str(m.get("content", ""))
            elif role == "system":
                system = str(m.get("content", ""))

        blob = _norm(system + " " + last_user)

        # The dialogue prompt embeds stage / hint_level hints; sniff them out so
        # the canned reply matches the orchestrator's intent.
        stage = _sniff_int(blob, "stage", default=1)
        hint_level = _sniff_int(blob, "hint", default=0)
        # Tolerant of: recall_detected: true / recall_detected=true / "recall": true
        # / recall=true / the literal word "recalled" / a concrete recall keyword.
        recall = (
            bool(re.search(r'recall(?:_detected)?["\s:=]+true', blob))
            or "recalled" in blob
            or _contains_any(_norm(last_user), RECALL_KEYWORDS)
        )

        if recall:
            return (
                "맞아요, 시장이었군요. 어머니 손을 꼭 잡고 걷던 그 골목이 "
                "눈에 선하시죠. 정말 소중한 기억이에요. 방금 떠올리신 이야기를 "
                "한 장의 그림으로 남겨 둘게요."
            )

        if stage >= 3:
            return (
                "오늘 이렇게 좋은 기억을 함께 나눠 주셔서 고마워요. 떠올리신 "
                "이야기를 자서전 한 페이지로 정리해 두었어요. 다음에 또 천천히 "
                "이어서 이야기해요."
            )

        if stage <= 1:
            return (
                "안녕하세요, 오늘 목소리가 참 편안하게 들려요. 잠시 깊게 숨을 "
                "쉬어 볼까요. 천천히, 우리 편하게 옛날 이야기 한번 나눠 봐요."
            )

        # Stage 2: hint escalation 0 -> 4.
        prompts = {
            0: "오래전, 가장 자주 가시던 곳이 어디였는지 떠오르시나요? 천천히 말씀해 주세요.",
            1: "그곳은 사람들이 북적이고 물건을 사고팔던 장소였어요. 어떤 곳일까요?",
            2: "어머니 손을 잡고 함께 걸어가셨던 그 길 기억나세요? 무엇을 사러 가셨을까요?",
            3: "생선 비린내와 떡 냄새가 가득했던 그 골목, 그림처럼 떠올려 보세요.",
            4: "바로 '시장'이었어요. 어머니와 함께 가시던 시장, 이제 떠오르시나요?",
        }
        return prompts.get(hint_level, prompts[0])

    async def complete_json(
        self,
        messages: list[dict],
        model: str,
        schema_hint: str = "",
    ) -> dict:
        """Return a reasoner decision dict.

        Shape (matches ``ReasoningDecision``)::

            {stage, next_stage, hint_level, recall_detected, keywords, reason}

        Heuristics that make the scripted "시장" recall work:
          * The orchestrator embeds the current session state in the messages
            (current ``stage`` and ``hint_level``). We parse them out.
          * If the latest user text names a concrete place/keyword
            (e.g. "시장") -> ``recall_detected = True`` and advance toward Stage 3.
          * If the user hesitates ("기억이 안 나요", "글쎄...") in Stage 2 ->
            escalate ``hint_level`` (capped at 4).
          * Stage 1 -> Stage 2 once the user produces any substantive reply.
        """
        last_user = ""
        state_blob = ""
        for m in messages:
            if m.get("role") == "user":
                last_user = str(m.get("content", ""))
            else:
                state_blob += " " + str(m.get("content", ""))

        text = last_user.strip()
        low = _norm(text)
        ctx = _norm(state_blob)

        stage = _sniff_int(ctx, "stage", default=1)
        hint_level = _sniff_int(ctx, "hint", default=0)
        stage = max(1, min(stage, 3))
        hint_level = max(0, min(hint_level, 4))

        keywords = _extract_keywords(text)
        recall_detected = _contains_any(low, RECALL_KEYWORDS)
        hesitated = _contains_any(low, HESITATION_PATTERNS) and not recall_detected

        next_stage = stage
        next_hint = hint_level
        reason = ""

        if stage == 1:
            # Emotional priming: move to retrieval once the user engages at all.
            if len(text) >= 2:
                next_stage = 2
                next_hint = 0
                reason = "환자가 편안하게 응답을 시작해 정서 안정화 단계에서 대화형 인출 단계로 전환합니다."
            else:
                reason = "아직 정서 안정화 단계입니다. 따뜻한 분위기를 이어 갑니다."
        elif stage == 2:
            if recall_detected:
                next_stage = 3
                reason = (
                    f"구체적 장소/대상 키워드({', '.join(keywords) or '시장'})가 "
                    "포착되어 인출 성공으로 판단, 행동 수행 단계로 전환합니다."
                )
            elif hesitated:
                next_hint = min(hint_level + 1, 4)
                reason = (
                    f"환자가 망설이거나 기억을 떠올리지 못해 단서 수준을 "
                    f"{hint_level}->{next_hint}로 단계적으로 높입니다."
                )
            else:
                reason = "대화형 인출을 이어 가며 환자의 자발적 회상을 기다립니다."
        else:  # stage == 3
            next_stage = 3
            reason = "회상된 기억을 자서전 페이지로 확정하고 세션을 마무리합니다."
            recall_detected = recall_detected or True  # ensure a page exists by closing

        return {
            "stage": stage,
            "next_stage": next_stage,
            "hint_level": next_hint,
            "recall_detected": bool(recall_detected),
            "keywords": keywords,
            "reason": reason,
        }


class MockSTT(STTProvider):
    """Deterministic transcript for the offline demo mic button."""

    backend = "mock"

    async def transcribe(self, audio: bytes, mime: str = "audio/webm") -> str:
        # A demo-friendly Korean line that nudges the scenario forward.
        return "어머니랑 시장에 자주 갔던 게 생각나요."


class MockTTS(TTSProvider):
    """No audio in mock mode: return empty bytes so the WS omits ``audio``."""

    backend = "mock"

    async def synthesize(self, text: str, voice: str = "alloy") -> bytes:
        return b""


# Warm palette colors keyed by the dominant recall keyword, so different
# memories produce visibly different (but deterministic) e-book pages.
_SVG_THEMES: dict[str, tuple[str, str, str]] = {
    "시장": ("#f6c177", "#eb6f92", "#fef3c7"),
    "바다": ("#9ccfd8", "#3e8fb0", "#e0f2fe"),
    "고향": ("#c4a7e7", "#907aa9", "#f3e8ff"),
    "꽃": ("#f4a8c0", "#eb6f92", "#fdf2f8"),
    "학교": ("#ea9d34", "#d7827e", "#fff7ed"),
}
_SVG_DEFAULT = ("#f6c177", "#d7827e", "#fdf6ec")


class MockImage(ImageProvider):
    """Deterministic inline-SVG placeholder so the e-book shows a picture offline."""

    backend = "mock"

    async def generate(self, prompt: str) -> str:
        prompt = (prompt or "추억").strip()
        # Pick a label = first known keyword in the prompt, else first word.
        label = next((k for k in _SVG_THEMES if k in prompt), None)
        if label is None:
            m = re.search(r"[가-힣]{2,}", prompt)
            label = m.group(0) if m else "추억"
        c1, c2, c3 = _SVG_THEMES.get(label, _SVG_DEFAULT)

        # Korean-only caption. The image PROMPT is English ("Warm nostalgic
        # Korean watercolor…"), so slicing it raw would bake English ad-copy onto
        # the picture. Use the longest Korean run in the prompt (the recalled
        # memory/keyword) instead, falling back to the theme label.
        kor = re.findall(r"[가-힣][가-힣0-9 ]*", prompt)
        cap_src = max(kor, key=len).strip() if kor else label
        caption = cap_src if len(cap_src) <= 18 else cap_src[:18] + "…"

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="420" '
            'viewBox="0 0 640 420">'
            "<defs>"
            f'<linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0%" stop-color="{c1}"/>'
            f'<stop offset="100%" stop-color="{c2}"/>'
            "</linearGradient></defs>"
            f'<rect width="640" height="420" fill="{c3}"/>'
            '<rect x="24" y="24" width="592" height="372" rx="20" fill="url(#g)"/>'
            '<circle cx="500" cy="120" r="46" fill="#fff7e6" opacity="0.85"/>'
            '<path d="M40 360 Q200 250 360 330 T620 300 V396 H40 Z" '
            'fill="#ffffff" opacity="0.35"/>'
            '<text x="320" y="220" font-family="Apple SD Gothic Neo, Malgun Gothic, '
            'sans-serif" font-size="40" font-weight="700" fill="#3b2f2f" '
            f'text-anchor="middle">{_xml_escape(label)}</text>'
            '<text x="320" y="270" font-family="Apple SD Gothic Neo, Malgun Gothic, '
            'sans-serif" font-size="20" fill="#5b4636" '
            f'text-anchor="middle">{_xml_escape(caption)}</text>'
            "</svg>"
        )
        # data: URI with URL-encoded SVG (renders in <img> without base64 bloat).
        return "data:image/svg+xml;utf8," + quote(svg)


class MockEmbedding(EmbeddingProvider):
    """Deterministic hashed pseudo-vectors (L2-normalized) of dim ``EMBEDDING_DIM``."""

    backend = "mock"

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self.dim = dim or EMBEDDING_DIM

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def _vector(self, text: str) -> list[float]:
        # Expand a SHA-256 stream until we have enough bytes, map to [-1, 1].
        seed = (text or "").encode("utf-8")
        buf = bytearray()
        counter = 0
        while len(buf) < self.dim:
            buf.extend(hashlib.sha256(seed + counter.to_bytes(4, "big")).digest())
            counter += 1
        vec = [(b / 127.5) - 1.0 for b in buf[: self.dim]]
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _sniff_int(blob: str, key: str, default: int) -> int:
    """Pull an integer that follows ``key`` in a free-text/JSON-ish blob.

    Tolerant of forms like ``stage=2``, ``"stage": 2``, ``stage 2``, ``hint_level: 3``.
    """
    m = re.search(rf'{key}[a-z_]*["\s:=]*?(\d+)', blob)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return default
    return default


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# Re-exported so callers don't depend on internal layout for the JSON helper.
def decision_to_json(decision: dict) -> str:
    return json.dumps(decision, ensure_ascii=False)


__all__ = [
    "MockLLM",
    "MockSTT",
    "MockTTS",
    "MockImage",
    "MockEmbedding",
    "RECALL_KEYWORDS",
    "HESITATION_PATTERNS",
]
