"""Provider factory.

``get_providers(settings) -> Providers`` selects the concrete implementation
**per capability** (LLM / STT / TTS / Image / Embedding). Each capability reads
its own ``*_provider`` setting (which defaults to ``settings.ai_provider``):

  * ``"openai"`` (with a valid ``OPENAI_API_KEY``)            -> real OpenAI providers.
  * ``"google"`` (with the right Google creds for that cap)   -> real Google providers.
  * anything else / missing creds                             -> deterministic offline mock.

The OpenAI and Google SDK modules are imported lazily, only on the branch that
actually needs them, so the default demo path never requires ``openai``,
``google-genai`` or ``google-cloud-speech`` to be installed. If a real provider
is selected but its credentials/SDK are missing, that single capability
transparently falls back to its mock implementation so the demo always boots
with zero secrets (never crashes).

Notes on Google capabilities:
  * LLM / Image / Embedding use the **Gemini API** (single ``GOOGLE_API_KEY``).
  * STT uses **Google Cloud Speech-to-Text** (ADC / service-account credentials,
    NOT the Gemini key) -> gated on ``GOOGLE_APPLICATION_CREDENTIALS`` or
    ``GOOGLE_CLOUD_PROJECT`` being present.
  * There is intentionally **no Google TTS**; selecting ``google`` for TTS falls
    back to the silent mock. For real voice, set ``TTS_PROVIDER=elevenlabs`` with
    ``ELEVENLABS_API_KEY`` (ElevenLabs is TTS-only) -> mp3, same as OpenAI TTS.

The shared abstract types / constants / the ``Providers`` dataclass are re-exported
from :mod:`app.providers.base` for convenient ``from app.providers import ...``.
"""

from __future__ import annotations

from app.providers.base import (
    DIALOGUE_MODEL,
    EMBEDDING_DIM,
    REASONING_MODEL,
    EmbeddingProvider,
    ImageProvider,
    LLMProvider,
    Providers,
    STTProvider,
    TTSProvider,
)
from app.providers.mock_provider import (
    MockEmbedding,
    MockImage,
    MockLLM,
    MockSTT,
    MockTTS,
)


def get_providers(settings) -> Providers:
    """Build the :class:`Providers` bundle, selecting each capability's backend
    independently with transparent mock fallback when creds/SDKs are missing."""
    openai_api_key = getattr(settings, "openai_api_key", None)
    google_api_key = getattr(settings, "google_api_key", None)
    google_app_credentials = getattr(settings, "google_app_credentials", None)
    google_cloud_project = getattr(settings, "google_cloud_project", None)
    embed_dim = getattr(settings, "embed_dim", EMBEDDING_DIM)
    google_embed_dim = getattr(settings, "google_embed_dim", 768)

    llm_provider = getattr(settings, "llm_provider", "mock")
    stt_provider = getattr(settings, "stt_provider", "mock")
    tts_provider = getattr(settings, "tts_provider", "mock")
    image_provider = getattr(settings, "image_provider", "mock")
    embedding_provider = getattr(settings, "embedding_provider", "mock")

    # ---- LLM (두뇌 + 입) -------------------------------------------------
    if llm_provider == "openai" and openai_api_key:
        from app.providers.openai_provider import OpenAILLM

        llm: LLMProvider = OpenAILLM(openai_api_key)
    elif llm_provider == "google" and google_api_key:
        from app.providers.google_provider import GoogleLLM

        llm = GoogleLLM(google_api_key)
    else:
        llm = MockLLM()

    # ---- STT -------------------------------------------------------------
    if stt_provider == "openai" and openai_api_key:
        from app.providers.openai_provider import OpenAISTT

        stt: STTProvider = OpenAISTT(openai_api_key)
    elif stt_provider == "google" and (google_app_credentials or google_cloud_project):
        # Google Cloud Speech-to-Text uses ADC / service-account creds, not the
        # Gemini key. Gate on creds/project presence.
        from app.providers.google_provider import GoogleSTT

        stt = GoogleSTT(project=google_cloud_project)
    else:
        stt = MockSTT()

    # ---- TTS (no Google TTS: google -> silent mock) ----------------------
    elevenlabs_api_key = getattr(settings, "elevenlabs_api_key", None)
    if tts_provider == "openai" and openai_api_key:
        from app.providers.openai_provider import OpenAITTS

        tts: TTSProvider = OpenAITTS(openai_api_key)
    elif tts_provider == "elevenlabs" and elevenlabs_api_key:
        from app.providers.elevenlabs_provider import (
            DEFAULT_MODEL,
            DEFAULT_VOICE_ID,
            ElevenLabsTTS,
        )

        tts = ElevenLabsTTS(
            elevenlabs_api_key,
            voice_id=getattr(settings, "elevenlabs_voice_id", None) or DEFAULT_VOICE_ID,
            model=getattr(settings, "elevenlabs_model", None) or DEFAULT_MODEL,
        )
    else:
        tts = MockTTS()

    # ---- Image -----------------------------------------------------------
    if image_provider == "openai" and openai_api_key:
        from app.providers.openai_provider import OpenAIImage

        image: ImageProvider = OpenAIImage(openai_api_key)
    elif image_provider == "google" and google_api_key:
        from app.providers.google_provider import GoogleImage

        image = GoogleImage(google_api_key)
    else:
        image = MockImage()

    # ---- Embedding -------------------------------------------------------
    if embedding_provider == "openai" and openai_api_key:
        from app.providers.openai_provider import OpenAIEmbedding

        embedding: EmbeddingProvider = OpenAIEmbedding(openai_api_key, dim=embed_dim)
    elif embedding_provider == "google" and google_api_key:
        from app.providers.google_provider import GoogleEmbedding

        embedding = GoogleEmbedding(google_api_key, dim=google_embed_dim)
    else:
        embedding = MockEmbedding(dim=embed_dim)

    return Providers(
        llm=llm,
        stt=stt,
        tts=tts,
        image=image,
        embedding=embedding,
    )


__all__ = [
    "get_providers",
    # re-exported shared symbols
    "Providers",
    "LLMProvider",
    "STTProvider",
    "TTSProvider",
    "ImageProvider",
    "EmbeddingProvider",
    "REASONING_MODEL",
    "DIALOGUE_MODEL",
    "EMBEDDING_DIM",
]
