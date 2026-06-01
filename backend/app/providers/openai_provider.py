"""Real OpenAI-backed providers.

Used only when ``AI_PROVIDER=openai`` and ``OPENAI_API_KEY`` is set. The
``openai`` SDK is imported lazily (inside methods / on first use) so that a
missing key or a missing SDK never breaks the default offline ``mock`` mode.

Models:
  * LLM completions / reasoning : ``gpt-4o`` (REASONING_MODEL), ``gpt-4o-mini`` (DIALOGUE_MODEL)
  * STT                         : ``whisper-1``
  * TTS                         : ``gpt-4o-mini-tts`` -> mp3 bytes
  * Image                       : ``gpt-image-1`` -> data: URI (base64 PNG)
  * Embeddings                  : ``text-embedding-3-large`` (truncated/padded to EMBEDDING_DIM)
"""

from __future__ import annotations

import json

from app.providers.base import (
    EMBEDDING_DIM,
    EmbeddingProvider,
    ImageProvider,
    LLMProvider,
    STTProvider,
    TTSProvider,
)

STT_MODEL = "whisper-1"
TTS_MODEL = "gpt-4o-mini-tts"
IMAGE_MODEL = "gpt-image-1"
EMBEDDING_MODEL = "text-embedding-3-large"


def _make_async_client(api_key: str):
    """Create an AsyncOpenAI client. Imported lazily so mock mode never needs the SDK."""
    try:
        from openai import AsyncOpenAI  # type: ignore
    except ImportError as exc:  # pragma: no cover - only hit in openai mode w/o SDK
        raise RuntimeError(
            "AI_PROVIDER=openai 를 사용하려면 'openai' 패키지가 필요합니다. "
            "(uv add openai)"
        ) from exc
    return AsyncOpenAI(api_key=api_key)


class OpenAILLM(LLMProvider):
    """gpt-4o / gpt-4o-mini chat completions."""

    backend = "openai"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = _make_async_client(self._api_key)
        return self._client

    async def complete(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        resp = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    async def complete_json(
        self,
        messages: list[dict],
        model: str,
        schema_hint: str = "",
    ) -> dict:
        """Return parsed JSON using the JSON response_format.

        ``schema_hint`` (if provided) is appended as a system instruction so the
        model knows the exact reasoner-decision shape to emit. The word "json"
        is guaranteed present (required by the OpenAI json_object mode).
        """
        msgs = list(messages)
        instruction = (
            "반드시 유효한 JSON 객체 하나만 출력하세요. 설명 문장이나 코드펜스는 금지합니다."
        )
        if schema_hint:
            instruction += f"\n다음 스키마(JSON)를 따르세요:\n{schema_hint}"
        msgs.insert(0, {"role": "system", "content": instruction})

        resp = await self.client.chat.completions.create(
            model=model,
            messages=msgs,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or "{}"
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Best-effort recovery: slice the outermost {...}.
            start, end = content.find("{"), content.rfind("}")
            if 0 <= start < end:
                try:
                    return json.loads(content[start : end + 1])
                except json.JSONDecodeError:
                    pass
            return {}


class OpenAISTT(STTProvider):
    """Whisper speech-to-text."""

    backend = "openai"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = _make_async_client(self._api_key)
        return self._client

    async def transcribe(self, audio: bytes, mime: str = "audio/webm") -> str:
        ext = _ext_for_mime(mime)
        # The SDK accepts a (filename, bytes, mime) tuple as the file argument.
        resp = await self.client.audio.transcriptions.create(
            model=STT_MODEL,
            file=(f"audio.{ext}", audio, mime),
            language="ko",
        )
        return (getattr(resp, "text", "") or "").strip()


class OpenAITTS(TTSProvider):
    """Text-to-speech -> mp3 bytes."""

    backend = "openai"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = _make_async_client(self._api_key)
        return self._client

    async def synthesize(self, text: str, voice: str = "alloy") -> bytes:
        if not text:
            return b""
        resp = await self.client.audio.speech.create(
            model=TTS_MODEL,
            voice=voice,
            input=text,
            response_format="mp3",
        )
        # AsyncOpenAI returns a response object whose body holds the audio bytes.
        data = getattr(resp, "content", None)
        if data is None and hasattr(resp, "read"):
            data = await resp.read()
        return data or b""


class OpenAIImage(ImageProvider):
    """gpt-image-1 -> data: URI (base64 PNG)."""

    backend = "openai"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = _make_async_client(self._api_key)
        return self._client

    async def generate(self, prompt: str) -> str:
        resp = await self.client.images.generate(
            model=IMAGE_MODEL,
            prompt=prompt,
            size="1024x1024",
            n=1,
        )
        item = resp.data[0]
        b64 = getattr(item, "b64_json", None)
        if b64:
            return f"data:image/png;base64,{b64}"
        # Some configurations return a hosted URL instead.
        url = getattr(item, "url", None)
        return url or ""


class OpenAIEmbedding(EmbeddingProvider):
    """text-embedding-3-large, sized to ``EMBEDDING_DIM`` to match mock vectors."""

    backend = "openai"

    def __init__(self, api_key: str, dim: int = EMBEDDING_DIM) -> None:
        self._api_key = api_key
        self._client = None
        self.dim = dim or EMBEDDING_DIM

    @property
    def client(self):
        if self._client is None:
            self._client = _make_async_client(self._api_key)
        return self._client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = await self.client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts,
            dimensions=self.dim,  # native truncation to keep parity with mock dim
        )
        # Preserve input order (SDK returns items with an ``index`` field).
        ordered = sorted(resp.data, key=lambda d: d.index)
        return [list(d.embedding) for d in ordered]


def _ext_for_mime(mime: str) -> str:
    mapping = {
        "audio/webm": "webm",
        "audio/ogg": "ogg",
        "audio/mp3": "mp3",
        "audio/mpeg": "mp3",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/mp4": "mp4",
        "audio/m4a": "m4a",
    }
    return mapping.get((mime or "").split(";")[0].strip().lower(), "webm")


__all__ = [
    "OpenAILLM",
    "OpenAISTT",
    "OpenAITTS",
    "OpenAIImage",
    "OpenAIEmbedding",
    "STT_MODEL",
    "TTS_MODEL",
    "IMAGE_MODEL",
    "EMBEDDING_MODEL",
]
