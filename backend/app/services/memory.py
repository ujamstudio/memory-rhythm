"""Memory service — 3-Tier extraction + embedding + cosine search.

Tiers (per plan §5 / §6):
  * Tier 1 — real-time keyword extraction from each user turn.
  * Tier 2 — (M1+) session-end deep extraction (stubbed here as summarize()).
  * Tier 3 — persistent store + vector index (backed by ``store.py``).

This module is provider-aware: it embeds memory text with the configured
``EmbeddingProvider`` and runs cosine similarity over the in-memory vectors so
the demo can surface "related memories" without a real pgvector instance.
"""

from __future__ import annotations

import re

import numpy as np

from app.providers.base import Providers
from app.schemas import Memory
from app.store import Store

# A compact Korean stop-word set for Tier-1 keyword extraction. Kept small and
# demo-oriented; the real pipeline would use a morphological analyzer.
_STOPWORDS: frozenset[str] = frozenset(
    {
        # fillers / pronouns / demonstratives
        "그리고", "그래서", "하지만", "그런데", "저는", "제가", "나는", "내가",
        "그냥", "정말", "조금", "아주", "매우", "너무", "그게", "이게", "저게",
        "거기", "여기", "저기", "그거", "이거", "저거", "음", "어", "아", "네",
        "예", "응", "글쎄", "잘", "좀", "더", "또", "다시", "있어요", "없어요",
        "같아요", "이에요", "예요", "거예요", "했어요", "해요", "그때", "그분",
        "당신", "우리", "그것", "무엇", "뭐", "왜", "어디", "언제", "누구",
        "기억", "생각", "모르겠어요", "모르겠네", "글쎄요", "그러게", "맞아요",
        # bound nouns / units / counters — not memory keywords
        "년", "월", "일", "시", "분", "초", "때", "번", "개", "명", "곳", "것",
        "거", "수", "등", "중", "적", "게", "데", "줄", "만큼", "동안", "정도",
        "이름", "나이", "사람", "이야기", "오래", "제일", "많이", "함께",
        # adverbs / frequency words — not memory keywords
        "즐겨", "자주", "천천히", "항상", "가끔", "거의", "역시", "매일",
        "서로", "모두", "다들", "별로", "아마", "워낙", "한참",
    }
)

# --- Korean particle / ending heuristics for cleaner keyword extraction ------
# Multi-char particles (조사) — unambiguous, always safe to strip from a noun's
# tail. Ordered longest-first so the greedy match removes the whole particle.
_MULTI_PARTICLES: tuple[str, ...] = (
    "에서는", "으로는", "에게서", "이라고", "이라는", "으로도", "에서도", "이라도",
    "에게", "한테", "에서", "으로", "까지", "부터", "보다", "처럼", "마다",
    "조차", "마저", "이라", "이며", "이고", "이나", "라고", "라는", "이랑",
    "에는", "에도", "에선", "께서", "밖에", "같이",
)
# Single-char particles SAFE to strip (rarely a noun's final syllable).
# 이/가/로/도/만/과/랑/의 are intentionally EXCLUDED — they collide with common
# noun endings (바닷가, 제주도, 사과, 사랑, 종로, 회의, 강의 …). 와 is kept because
# a noun rarely ends in the syllable 와 (whereas 과 ends 사과/효과 …).
_SINGLE_PARTICLES: frozenset[str] = frozenset({"은", "는", "을", "를", "에", "와"})

# Conjugated verb/adjective endings — a token ending this way is a predicate,
# not a memory keyword. Multi-char to keep false positives near zero.
_PREDICATE_ENDINGS: tuple[str, ...] = (
    "습니다", "ㅂ니다", "니다", "어요", "아요", "여요", "해요", "에요", "예요",
    "세요", "지요", "네요", "군요", "나요", "까요", "대요", "래요", "려요",
    "워요", "와요", "셔요", "이요", "었어", "았어", "였어", "겠어", "어서",
    "아서", "지만", "는데", "으며", "면서", "거나", "더니", "거든", "잖아",
    "았다", "었다", "였다", "겠다", "더라", "드라",
    # honorific / past connectives (… 하셨고, 끝나고, 됐고 …)
    "셨고", "셨어", "셨다", "셨지", "으셨", "하고", "했고", "하며", "되고",
    "됐고", "드렸", "계셨", "았고", "었고", "였고", "나고",
)


def _strip_particle(token: str) -> str:
    """Strip one trailing Korean particle from a noun token.

    Multi-char particles keep a >= 2 stem; a safe single-char particle is
    removed from any 2+ char token (a resulting 1-char stem is dropped later by
    the length filter, e.g. ``년에`` -> ``년`` -> dropped).
    """
    for p in _MULTI_PARTICLES:
        if token.endswith(p) and len(token) - len(p) >= 2:
            return token[: -len(p)]
    if len(token) >= 2 and token[-1] in _SINGLE_PARTICLES:
        return token[:-1]
    return token

# Seed memory phrases the mock scenario can latch onto. These let the cosine
# search return something meaningful even before any real memory is stored.
SEED_MEMORIES: tuple[str, ...] = (
    "젊은 시절 동네 시장에서 채소 가게를 하셨다.",
    "딸 둘과 손주 셋이 있다.",
    "옛날 트로트와 흑백 영화를 좋아하셨다.",
    "장날이면 시장 골목이 사람들로 북적였다.",
)


class MemoryService:
    """Tier-1 extraction, embedding, and cosine retrieval over the store."""

    def __init__(self, providers: Providers, store: Store) -> None:
        self._providers = providers
        self._store = store

    # -- Tier 1: keyword extraction ---------------------------------------
    def extract_keywords(self, text: str, limit: int = 6) -> list[str]:
        """Extract candidate memory keywords from a single user utterance.

        Heuristic and synchronous (no LLM): split on non-Korean/alnum runs,
        drop stop-words and very short tokens, keep first-seen order.
        """
        if not text:
            return []
        # Hangul runs, or a latin-led alnum token (excludes bare numbers/years).
        raw_tokens = re.findall(r"[가-힣]+|[A-Za-z][A-Za-z0-9]*", text)
        seen: list[str] = []
        for tok in raw_tokens:
            t = tok.strip()
            if len(t) < 2:
                continue
            # Drop conjugated verbs/adjectives (predicates), not memory nouns.
            if any(t.endswith(e) for e in _PREDICATE_ENDINGS):
                continue
            # Bare the noun by removing a trailing particle (조사).
            t = _strip_particle(t)
            if len(t) < 2 or t in _STOPWORDS:
                continue
            if t not in seen:
                seen.append(t)
            if len(seen) >= limit:
                break
        return seen

    # -- embeddings + cosine search ---------------------------------------
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self._providers.embedding.embed(texts)

    async def store_memory(
        self,
        patient_id: str,
        text: str,
        keywords: list[str] | None = None,
        recall_status: str = "unrecalled",
    ) -> Memory:
        """Tier-3 persistence: embed the text and store the memory + vector."""
        vectors = await self._providers.embedding.embed([text])
        embedding = vectors[0] if vectors else None
        return self._store.add_memory(
            patient_id=patient_id,
            text=text,
            keywords=keywords or self.extract_keywords(text),
            recall_status=recall_status,
            embedding=embedding,
        )

    async def search(
        self, patient_id: str, query: str, top_k: int = 3
    ) -> list[tuple[Memory, float]]:
        """Cosine-similarity search over the patient's stored memory vectors."""
        pairs = self._store.list_memory_vectors(patient_id)
        if not pairs:
            return []
        q_vec = (await self._providers.embedding.embed([query]))[0]
        q = np.asarray(q_vec, dtype=np.float32)
        q_norm = float(np.linalg.norm(q)) or 1.0

        scored: list[tuple[Memory, float]] = []
        for mem, vec in pairs:
            v = np.asarray(vec, dtype=np.float32)
            denom = (float(np.linalg.norm(v)) or 1.0) * q_norm
            sim = float(np.dot(q, v) / denom)
            scored.append((mem, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    # -- persona context (per-patient, data-driven) -----------------------
    def persona_brief(self, patient_id: str) -> str:
        """A compact "what the friend knows about this 어르신" brief, built from
        the ACCUMULATING store (survey profile + recalled memories + keywords).

        This is what personalizes the companion per person and grows over time:
        the more the patient recalls, the more of their real life the friend can
        warmly reference — without inventing anything. Returns "" for an unknown
        patient or before any data exists.
        """
        patient = self._store.get_patient(patient_id)
        if patient is None:
            return ""
        parts: list[str] = [f"성함: {patient.name}"]
        if patient.persona_profile:
            parts.append(f"프로필: {patient.persona_profile}")

        result = self._store.get_survey_result(patient_id)
        if result is not None:
            if result.recallable_keywords:
                parts.append(
                    "또렷이 기억하시는 것: "
                    + ", ".join(result.recallable_keywords[:8])
                )
            if result.unrecallable_topics:
                parts.append(
                    "아직 흐릿한 주제(억지로 캐묻지 말 것): "
                    + ", ".join(result.unrecallable_topics[:5])
                )

        recalled = [
            m.text.strip()
            for m in self._store.list_memories(patient_id)
            if m.recall_status == "recalled" and m.text.strip()
        ]
        if recalled:
            parts.append("함께 떠올린 추억: " + " / ".join(recalled[-6:]))
        return "\n".join(parts)

    def recall_anchors(self, patient_id: str) -> list[str]:
        """This patient's REAL recall targets, deduped and insertion-ordered.

        Sourced from the SAME accumulating store as :meth:`persona_brief` — the
        survey's ``recallable_keywords`` plus the keywords of memories already
        recalled this/earlier sessions. The reasoner unions these with the demo's
        generic place baseline so the patient's OWN memories (나물·딸·…) count as
        a successful recall, not only the scripted 시장 keywords. Empty for an
        unsurveyed demo patient — which keeps the 시장 baseline behavior intact.
        """
        anchors: list[str] = []

        def _add(kw: str) -> None:
            kw = (kw or "").strip()
            if kw and kw not in anchors:
                anchors.append(kw)

        result = self._store.get_survey_result(patient_id)
        if result is not None:
            for kw in result.recallable_keywords:
                _add(kw)
        for mem in self._store.list_memories(patient_id):
            if mem.recall_status == "recalled":
                for kw in mem.keywords:
                    _add(kw)
        return anchors

    # -- Tier 2 stub -------------------------------------------------------
    def summarize_session(self, state_user_texts: list[str]) -> str:
        """Lightweight session summary used at Stage-3 close (Tier-2 placeholder).

        Concatenates the most informative utterances; the M1 pipeline replaces
        this with an LLM deep-extraction pass.
        """
        meaningful = [t for t in state_user_texts if len(t.strip()) > 2]
        return " ".join(meaningful[-4:]) if meaningful else ""
