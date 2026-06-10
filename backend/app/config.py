"""Runtime configuration for the Memory Rhythm backend.

The demo MUST boot with zero secrets: the defaults select the offline ``mock``
provider and the in-memory store, so no API key and no database are required.

Provider selection is **per capability**. A global ``AI_PROVIDER`` sets the
default backend for every capability; each capability may then be overridden
independently via ``LLM_PROVIDER`` / ``STT_PROVIDER`` / ``TTS_PROVIDER`` /
``IMAGE_PROVIDER`` / ``EMBEDDING_PROVIDER``. Valid values are ``mock`` |
``openai`` | ``google``; anything else falls back to ``mock``.

This makes mixed setups possible, e.g. Google (Gemini API) for LLM, Image and
Embedding, Google Cloud Speech-to-Text for STT, and a silent ``mock`` TTS.

Settings are read from the process environment exactly once and cached.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from app.providers.base import EMBEDDING_DIM

# Valid provider backends for any capability.
_VALID_PROVIDERS = ("mock", "openai", "google")
# TTS additionally accepts "elevenlabs" (TTS-only — it implements no other
# capability, so it is intentionally not in the shared set above).
_VALID_TTS_PROVIDERS = _VALID_PROVIDERS + ("elevenlabs",)

# Mock pseudo-vector dimension default (kept for back-compat with EMBEDDING_DIM).
_DEFAULT_EMBED_DIM = EMBEDDING_DIM
# gemini-embedding-001 output_dimensionality default.
_DEFAULT_GOOGLE_EMBED_DIM = 768

# Resolved reasoning/dialogue model names per LLM backend.
_MODELS_BY_PROVIDER: dict[str, tuple[str, str]] = {
    "openai": ("gpt-4o", "gpt-4o-mini"),
    "google": ("gemini-2.5-flash-lite", "gemini-2.5-flash-lite"),
    "mock": ("mock-reasoner", "mock-dialogue"),
}


def _env(name: str, default: str) -> str:
    """Read an env var, treating empty/whitespace-only values as unset."""
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _env_opt(name: str) -> str | None:
    """Read an optional env var; empty/whitespace-only -> ``None``."""
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _provider(name: str, default: str, valid: tuple = _VALID_PROVIDERS) -> str:
    """Read a per-capability provider env var, lowercased and validated.

    Anything outside ``valid`` (including unset) falls back to ``default`` if
    that is valid, otherwise ``"mock"``. ``valid`` defaults to {mock, openai,
    google}; TTS passes the wider set that also allows ``elevenlabs``.
    """
    value = _env(name, default).lower()
    if value not in valid:
        return default if default in valid else "mock"
    return value


@dataclass(frozen=True)
class Settings:
    """Immutable view of the backend configuration."""

    ai_provider: str = "mock"               # global default: mock | openai | google
    llm_provider: str = "mock"              # 두뇌 + 입 (LLM)
    stt_provider: str = "mock"              # speech-to-text
    tts_provider: str = "mock"              # text-to-speech
    image_provider: str = "mock"           # image generation
    embedding_provider: str = "mock"        # text embeddings
    store: str = "sqlite"                   # "sqlite" (persist) | "memory" (ephemeral)
    db_path: str | None = None              # DB_PATH; default backend/data/memory_rhythm.db
    openai_api_key: str | None = None       # OPENAI_API_KEY
    google_api_key: str | None = None       # GOOGLE_API_KEY or GEMINI_API_KEY (Gemini API)
    google_cloud_project: str | None = None  # GOOGLE_CLOUD_PROJECT (Cloud STT)
    google_app_credentials: str | None = None  # GOOGLE_APPLICATION_CREDENTIALS path
    elevenlabs_api_key: str | None = None   # ELEVENLABS_API_KEY (TTS only)
    elevenlabs_voice_id: str | None = None  # ELEVENLABS_VOICE_ID (default in provider)
    elevenlabs_model: str | None = None     # ELEVENLABS_MODEL (default in provider)
    embed_dim: int = _DEFAULT_EMBED_DIM     # mock pseudo-vector dimension
    google_embed_dim: int = _DEFAULT_GOOGLE_EMBED_DIM  # gemini-embedding-001 dim
    cors_origin: str = "http://localhost:5173"
    reasoning_model: str = "mock-reasoner"  # the "두뇌": reasoning / decision LLM
    dialogue_model: str = "mock-dialogue"   # the "입": natural Korean utterance LLM

    @property
    def use_openai(self) -> bool:
        """Back-compat helper. True when the global provider is OpenAI + keyed.

        No longer authoritative: the per-capability ``*_provider`` fields are the
        source of truth. Kept so older callers keep working.
        """
        return self.ai_provider == "openai" and bool(self.openai_api_key)

    @property
    def use_google(self) -> bool:
        """Convenience helper. True when the global provider is Google + keyed."""
        return self.ai_provider == "google" and bool(self.google_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached process-wide :class:`Settings`.

    Reads (with safe defaults so the demo runs offline):
      * ``AI_PROVIDER``        -> ``ai_provider``     (default ``"mock"``)
      * ``LLM_PROVIDER``       -> ``llm_provider``    (default = ai_provider)
      * ``STT_PROVIDER``       -> ``stt_provider``    (default = ai_provider)
      * ``TTS_PROVIDER``       -> ``tts_provider``    (default = ai_provider)
      * ``IMAGE_PROVIDER``     -> ``image_provider``  (default = ai_provider)
      * ``EMBEDDING_PROVIDER`` -> ``embedding_provider`` (default = ai_provider)
      * ``STORE``              -> ``store``           (default ``"memory"``)
      * ``OPENAI_API_KEY``     -> ``openai_api_key``  (default ``None``)
      * ``GOOGLE_API_KEY`` / ``GEMINI_API_KEY`` -> ``google_api_key``
      * ``GOOGLE_CLOUD_PROJECT`` -> ``google_cloud_project``
      * ``GOOGLE_APPLICATION_CREDENTIALS`` -> ``google_app_credentials``
      * ``ELEVENLABS_API_KEY`` -> ``elevenlabs_api_key`` (TTS only; default ``None``)
      * ``ELEVENLABS_VOICE_ID``-> ``elevenlabs_voice_id`` (default in provider)
      * ``ELEVENLABS_MODEL``   -> ``elevenlabs_model``  (default ``eleven_flash_v2_5``)
      * ``EMBED_DIM``          -> ``embed_dim``       (default ``256``)
      * ``GOOGLE_EMBED_DIM``   -> ``google_embed_dim``(default ``768``)
      * ``CORS_ORIGIN``        -> ``cors_origin``     (default localhost:5173)
      * ``REASONING_MODEL``    -> overrides resolved ``reasoning_model``
      * ``DIALOGUE_MODEL``     -> overrides resolved ``dialogue_model``
    """
    ai_provider = _env("AI_PROVIDER", "mock").lower()
    if ai_provider not in _VALID_PROVIDERS:
        ai_provider = "mock"

    # Per-capability providers default to the global provider, then validate.
    llm_provider = _provider("LLM_PROVIDER", ai_provider)
    stt_provider = _provider("STT_PROVIDER", ai_provider)
    tts_provider = _provider("TTS_PROVIDER", ai_provider, _VALID_TTS_PROVIDERS)
    image_provider = _provider("IMAGE_PROVIDER", ai_provider)
    embedding_provider = _provider("EMBEDDING_PROVIDER", ai_provider)

    # Google API key accepts either the canonical name or the AI Studio alias.
    google_api_key = _env_opt("GOOGLE_API_KEY") or _env_opt("GEMINI_API_KEY")

    # Resolve reasoning/dialogue models from the LLM backend, with env overrides.
    default_reasoning, default_dialogue = _MODELS_BY_PROVIDER.get(
        llm_provider, _MODELS_BY_PROVIDER["mock"]
    )
    reasoning_model = _env("REASONING_MODEL", default_reasoning)
    dialogue_model = _env("DIALOGUE_MODEL", default_dialogue)

    return Settings(
        ai_provider=ai_provider,
        llm_provider=llm_provider,
        stt_provider=stt_provider,
        tts_provider=tts_provider,
        image_provider=image_provider,
        embedding_provider=embedding_provider,
        store=_env("STORE", "sqlite").lower(),
        db_path=_env_opt("DB_PATH"),
        openai_api_key=_env_opt("OPENAI_API_KEY"),
        google_api_key=google_api_key,
        google_cloud_project=_env_opt("GOOGLE_CLOUD_PROJECT"),
        google_app_credentials=_env_opt("GOOGLE_APPLICATION_CREDENTIALS"),
        elevenlabs_api_key=_env_opt("ELEVENLABS_API_KEY"),
        elevenlabs_voice_id=_env_opt("ELEVENLABS_VOICE_ID"),
        elevenlabs_model=_env_opt("ELEVENLABS_MODEL"),
        embed_dim=_env_int("EMBED_DIM", _DEFAULT_EMBED_DIM),
        google_embed_dim=_env_int("GOOGLE_EMBED_DIM", _DEFAULT_GOOGLE_EMBED_DIM),
        cors_origin=_env("CORS_ORIGIN", "http://localhost:5173"),
        reasoning_model=reasoning_model,
        dialogue_model=dialogue_model,
    )


__all__ = ["Settings", "get_settings"]
