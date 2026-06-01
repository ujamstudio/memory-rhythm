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
        "그리고", "그래서", "하지만", "그런데", "저는", "제가", "나는", "내가",
        "그냥", "정말", "조금", "아주", "매우", "너무", "그게", "이게", "저게",
        "거기", "여기", "저기", "그거", "이거", "저거", "음", "어", "아", "네",
        "예", "응", "글쎄", "잘", "좀", "더", "또", "다시", "있어요", "없어요",
        "같아요", "이에요", "예요", "거예요", "했어요", "해요", "그때", "그분",
        "당신", "우리", "그것", "무엇", "뭐", "왜", "어디", "언제", "누구",
        "기억", "생각", "모르겠어요", "모르겠네", "글쎄요", "그러게", "맞아요",
    }
)

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
        # Split on whitespace + punctuation, keep Hangul/alnum chunks.
        raw_tokens = re.findall(r"[가-힣]+|[A-Za-z0-9]+", text)
        seen: list[str] = []
        for tok in raw_tokens:
            t = tok.strip()
            if len(t) < 2:
                continue
            if t in _STOPWORDS:
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

    # -- Tier 2 stub -------------------------------------------------------
    def summarize_session(self, state_user_texts: list[str]) -> str:
        """Lightweight session summary used at Stage-3 close (Tier-2 placeholder).

        Concatenates the most informative utterances; the M1 pipeline replaces
        this with an LLM deep-extraction pass.
        """
        meaningful = [t for t in state_user_texts if len(t.strip()) > 2]
        return " ".join(meaningful[-4:]) if meaningful else ""
