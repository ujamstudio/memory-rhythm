"""Abstract provider interfaces for the Memory Rhythm demo.

Two concrete implementations live alongside this file:
  * ``mock_provider.py``   -> deterministic, offline, Korean canned responses.
  * ``openai_provider.py`` -> real GPT-4o / GPT-4o-mini / Whisper / TTS /
                              gpt-image-1 / text-embedding-3-large.

``providers/__init__.py`` exposes ``get_providers(settings) -> Providers`` which
selects the implementation **per capability** ("mock" | "openai" | "google"),
transparently falling back to mock when credentials/SDKs are missing.

Every concrete provider sets a ``backend`` class attribute ("mock" | "openai" |
"google"). Callers use that tag (NOT ``isinstance`` or settings) to tell a real
provider from a mock one; it stays correct even after a credential fallback.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

# Centralized model-name constants. The mock provider ignores these.
REASONING_MODEL = "gpt-4o"        # the "두뇌": reasoning / decision LLM
DIALOGUE_MODEL = "gpt-4o-mini"    # the "입": natural Korean utterance LLM

# Embedding vector dimension. Mock produces a deterministic hashed pseudo-vector
# of this size; the OpenAI provider uses text-embedding-3-large.
EMBEDDING_DIM = 256


class LLMProvider(ABC):
    """Text + structured-JSON completion."""

    backend: str = "abstract"

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Return a plain-text completion for the given chat messages."""
        raise NotImplementedError

    @abstractmethod
    async def complete_json(
        self,
        messages: list[dict],
        model: str,
        schema_hint: str = "",
    ) -> dict:
        """Return a parsed JSON object. The reasoner uses this for decisions."""
        raise NotImplementedError


class STTProvider(ABC):
    """Speech-to-text (Whisper)."""

    backend: str = "abstract"

    @abstractmethod
    async def transcribe(self, audio: bytes, mime: str = "audio/webm") -> str:
        """Transcribe audio bytes to Korean text."""
        raise NotImplementedError


class TTSProvider(ABC):
    """Text-to-speech."""

    backend: str = "abstract"

    @abstractmethod
    async def synthesize(self, text: str, voice: str = "alloy") -> bytes:
        """Return MP3 bytes. The mock implementation returns ``b""``."""
        raise NotImplementedError


class ImageProvider(ABC):
    """Image generation (gpt-image-1)."""

    backend: str = "abstract"

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """Return an image URL or ``data:`` URI.

        The mock implementation returns a deterministic placeholder
        ``data:`` URI (or ``/static`` path).
        """
        raise NotImplementedError


class EmbeddingProvider(ABC):
    """Text embeddings used for cosine similarity memory search."""

    backend: str = "abstract"

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector (length ``EMBEDDING_DIM``) per input text.

        Mock: deterministic hashed pseudo-vector.
        OpenAI: text-embedding-3-large.
        """
        raise NotImplementedError


@dataclass
class Providers:
    """Bundle of all provider implementations passed to services."""

    llm: LLMProvider
    stt: STTProvider
    tts: TTSProvider
    image: ImageProvider
    embedding: EmbeddingProvider


__all__ = [
    "REASONING_MODEL",
    "DIALOGUE_MODEL",
    "EMBEDDING_DIM",
    "LLMProvider",
    "STTProvider",
    "TTSProvider",
    "ImageProvider",
    "EmbeddingProvider",
    "Providers",
]
