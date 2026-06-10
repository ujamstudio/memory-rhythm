"""Amazon Polly TTS provider (Korean neural/generative voices).

Used when ``TTS_PROVIDER=polly``. Polly has native Korean voices — **Seoyeon**
(standard | neural | generative) and **Jihye** (neural) — so it is the natural
TTS for this Korean demo. Returns mp3 bytes exactly like the other TTS adapters,
so the orchestrator audio path and the frontend player need no change.

Credentials: boto3's default chain. On EC2 this resolves the **instance role**
(no keys in env — see deploy-aws.ps1 -Polly, which attaches an instance profile
granting polly:SynthesizeSpeech); locally it uses your ``aws configure`` creds.
If credentials/permissions are missing the call raises and the orchestrator's
try/except degrades to silent — never crashes the demo.

boto3's client is synchronous, so synthesize() runs it in a worker thread to
avoid blocking the asyncio event loop.
"""

from __future__ import annotations

import asyncio

from app.providers.base import TTSProvider

DEFAULT_VOICE = "Seoyeon"   # Korean female; also supports the 'generative' engine
DEFAULT_ENGINE = "neural"   # neural | generative | standard
DEFAULT_REGION = "ap-northeast-2"


class PollyTTS(TTSProvider):
    """Text-to-speech -> mp3 bytes via Amazon Polly."""

    backend = "polly"

    def __init__(
        self,
        region: str = DEFAULT_REGION,
        voice: str = DEFAULT_VOICE,
        engine: str = DEFAULT_ENGINE,
    ) -> None:
        self._region = region or DEFAULT_REGION
        self._voice = voice or DEFAULT_VOICE
        self._engine = engine or DEFAULT_ENGINE
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import boto3  # lazy: only imported on the polly branch

            self._client = boto3.client("polly", region_name=self._region)
        return self._client

    async def synthesize(self, text: str, voice: str = "alloy") -> bytes:
        if not text:
            return b""
        # The abstract signature defaults ``voice`` to OpenAI's "alloy"; callers
        # pass no voice, so fall back to the configured Polly voice id.
        voice_id = voice if (voice and voice != "alloy") else self._voice

        def _call() -> bytes:
            resp = self.client.synthesize_speech(
                Text=text,
                VoiceId=voice_id,
                Engine=self._engine,
                OutputFormat="mp3",
                LanguageCode="ko-KR",
            )
            stream = resp.get("AudioStream")
            return stream.read() if stream is not None else b""

        return await asyncio.to_thread(_call)
