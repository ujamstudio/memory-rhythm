"""Real ElevenLabs-backed TTS provider.

Used only when ``TTS_PROVIDER=elevenlabs`` **and** ``ELEVENLABS_API_KEY`` is set.
Everything else (LLM / STT / Image / Embedding) is unaffected — ElevenLabs only
implements text-to-speech, mirroring how Google omits TTS.

Implementation notes:
  * Uses ``httpx`` (already a hard runtime dependency) — no extra SDK, so a
    ``pip install -r requirements.txt`` stays lean and the default mock path
    never imports anything new. This module is only imported on the
    ``elevenlabs`` branch of the provider factory.
  * Model defaults to ``eleven_flash_v2_5`` — cheap (~0.5 credit/char) and
    multilingual, so it handles Korean. Override via ``ELEVENLABS_MODEL``.
  * Returns **mp3 bytes**, identical to ``OpenAITTS``, so the orchestrator's
    ``audio`` message and the frontend ``<Audio>`` player need zero changes.
  * Runtime errors (network, 401, 429 quota) are NOT swallowed here; the
    orchestrator's ``_maybe_emit_audio`` already wraps ``synthesize`` in
    try/except and treats a failure as "no audio", so a quota 429 degrades to
    silent (same graceful behavior as the Gemini free-tier 429 fallback).
"""

from __future__ import annotations

import httpx

from app.providers.base import TTSProvider

# Defaults (all overridable via env -> Settings -> factory):
DEFAULT_MODEL = "eleven_flash_v2_5"          # cheap + multilingual (Korean-capable)
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"    # "Rachel" — ElevenLabs canonical default voice
OUTPUT_FORMAT = "mp3_44100_128"              # mp3, matches the frontend data:audio/mp3 player
_BASE_URL = "https://api.elevenlabs.io/v1/text-to-speech"
_TIMEOUT = 30.0  # TTS synthesis can take a few seconds


class ElevenLabsTTS(TTSProvider):
    """Text-to-speech -> mp3 bytes via the ElevenLabs HTTP API."""

    backend = "elevenlabs"

    def __init__(
        self,
        api_key: str,
        voice_id: str = DEFAULT_VOICE_ID,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self._api_key = api_key
        self._voice_id = voice_id or DEFAULT_VOICE_ID
        self._model = model or DEFAULT_MODEL

    async def synthesize(self, text: str, voice: str = "alloy") -> bytes:
        if not text:
            return b""
        # The abstract signature defaults ``voice`` to the OpenAI name "alloy";
        # callers pass no voice, so fall back to the configured ElevenLabs id.
        voice_id = voice if (voice and voice != "alloy") else self._voice_id
        url = f"{_BASE_URL}/{voice_id}"
        params = {"output_format": OUTPUT_FORMAT}
        headers = {
            "xi-api-key": self._api_key,
            "accept": "audio/mpeg",
            "content-type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": self._model,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, params=params, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.content or b""
