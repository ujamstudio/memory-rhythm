"""Real Google-backed providers.

Two distinct Google access surfaces are used here:

  * **Gemini API** (``google-genai``, a single ``GOOGLE_API_KEY`` from AI Studio)
    powers the LLM ("두뇌"+"입"), Image (Imagen), and Embedding capabilities.
  * **Google Cloud Speech-to-Text** (``google-cloud-speech``) powers STT and
    authenticates via Application Default Credentials / a service account
    (``GOOGLE_APPLICATION_CREDENTIALS``) — NOT the Gemini API key.

There is intentionally **no GoogleTTS**: TTS stays off Google (mock/silent).

Both Google SDKs are imported lazily (inside ``__init__`` / methods) so the
default offline ``mock`` mode never needs them. Every concrete class sets a
``backend = "google"`` class attribute; callers use that tag (NOT ``isinstance``
or settings) to tell a real provider from a mock one — which stays correct even
after a transparent credential/SDK fallback.

Models:
  * LLM completions / reasoning : ``gemini-2.5-flash`` (GEMINI_LLM_DEFAULT)
  * STT                         : Cloud Speech-to-Text ``latest_long`` (ko-KR)
  * Image                       : ``imagen-3.0-generate-002`` (IMAGEN_MODEL)
  * Embeddings                  : ``gemini-embedding-001`` (GEMINI_EMBED_MODEL)
"""

from __future__ import annotations

import base64
import json

from app.providers.base import (
    EmbeddingProvider,
    ImageProvider,
    LLMProvider,
    STTProvider,
)

# Module model-name constants (Google-specific; base.py keeps the OpenAI ones).
GEMINI_LLM_DEFAULT = "gemini-2.5-flash"      # the "두뇌"+"입": reasoning + dialogue
GEMINI_EMBED_MODEL = "gemini-embedding-001"  # 768-dim embeddings by default
IMAGEN_MODEL = "imagen-3.0-generate-002"     # Imagen image generation

# Default embedding output dimensionality for gemini-embedding-001.
GOOGLE_EMBED_DIM = 768


def _make_genai_client(api_key: str):
    """Create a google-genai Client. Imported lazily so mock mode never needs the SDK."""
    try:
        from google import genai  # type: ignore
    except ImportError as exc:  # pragma: no cover - only hit in google mode w/o SDK
        raise RuntimeError(
            "google 공급자(LLM/Image/Embedding)를 사용하려면 'google-genai' 패키지가 "
            "필요합니다. (uv add google-genai)"
        ) from exc
    return genai.Client(api_key=api_key)


def _genai_types():
    """Lazily import ``google.genai.types``."""
    try:
        from google.genai import types  # type: ignore
    except ImportError as exc:  # pragma: no cover - only hit in google mode w/o SDK
        raise RuntimeError(
            "google 공급자(LLM/Image/Embedding)를 사용하려면 'google-genai' 패키지가 "
            "필요합니다. (uv add google-genai)"
        ) from exc
    return types


def _split_messages(messages: list[dict]) -> tuple[str, list]:
    """Translate OpenAI-style messages to a Gemini (system_instruction, contents) pair.

    ``role=="system"`` messages are concatenated into a single system instruction.
    Remaining ``user``/``assistant`` messages map to Gemini ``contents`` with roles
    ``"user"``/``"model"`` (the SDK accepts a list of {role, parts:[{text}]} dicts).
    """
    system_parts: list[str] = []
    contents: list[dict] = []
    for m in messages:
        role = m.get("role")
        text = str(m.get("content", ""))
        if role == "system":
            if text:
                system_parts.append(text)
            continue
        gem_role = "model" if role == "assistant" else "user"
        contents.append({"role": gem_role, "parts": [{"text": text}]})
    return "\n\n".join(system_parts), contents


def _parse_json_loose(content: str) -> dict:
    """Best-effort JSON parsing mirroring the OpenAI provider's robustness.

    Tries a direct parse, then slices the outermost ``{...}`` or ``[...]`` block.
    Returns ``{}`` on total failure (a list is wrapped so the return stays a dict-ish
    JSON value as produced by the model; callers expect a dict for decisions).
    """
    content = (content or "").strip()
    if not content:
        return {}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    # Slice the outermost object or array, whichever appears first.
    candidates = []
    obj_start, obj_end = content.find("{"), content.rfind("}")
    if 0 <= obj_start < obj_end:
        candidates.append(content[obj_start : obj_end + 1])
    arr_start, arr_end = content.find("["), content.rfind("]")
    if 0 <= arr_start < arr_end:
        candidates.append(content[arr_start : arr_end + 1])
    for snippet in candidates:
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            continue
    return {}


class GoogleLLM(LLMProvider):
    """Gemini chat completions (``gemini-2.5-flash``) via google-genai."""

    backend = "google"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = _make_genai_client(self._api_key)
        return self._client

    async def complete(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        types = _genai_types()
        system_instruction, contents = _split_messages(messages)
        config = types.GenerateContentConfig(
            system_instruction=system_instruction or None,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        resp = await self.client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
        return (resp.text or "").strip()

    async def complete_json(
        self,
        messages: list[dict],
        model: str,
        schema_hint: str = "",
    ) -> dict:
        """Return parsed JSON using Gemini's JSON response mime type.

        ``schema_hint`` (if provided) is appended to the system instruction so the
        model knows the exact reasoner-decision shape to emit.
        """
        types = _genai_types()
        system_instruction, contents = _split_messages(messages)
        instruction = (
            "반드시 유효한 JSON 객체 하나만 출력하세요. 설명 문장이나 코드펜스는 금지합니다."
        )
        if schema_hint:
            instruction += f"\n다음 스키마(JSON)를 따르세요:\n{schema_hint}"
        if system_instruction:
            instruction = system_instruction + "\n\n" + instruction

        config = types.GenerateContentConfig(
            system_instruction=instruction,
            temperature=0.2,
            response_mime_type="application/json",
        )
        resp = await self.client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
        return _parse_json_loose(resp.text or "")


class GoogleSTT(STTProvider):
    """Google Cloud Speech-to-Text (v1 ``SpeechAsyncClient``, ko-KR).

    Credentials come from Application Default Credentials /
    ``GOOGLE_APPLICATION_CREDENTIALS`` automatically — NOT the Gemini API key.
    """

    backend = "google"

    def __init__(self, project: str | None = None) -> None:
        self._project = project
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                from google.cloud import speech  # type: ignore
            except ImportError as exc:  # pragma: no cover - only hit in google STT mode w/o SDK
                raise RuntimeError(
                    "STT_PROVIDER=google 를 사용하려면 'google-cloud-speech' 패키지가 "
                    "필요합니다. (uv add google-cloud-speech)"
                ) from exc
            self._client = speech.SpeechAsyncClient()
        return self._client

    async def transcribe(self, audio: bytes, mime: str = "audio/webm") -> str:
        from google.cloud import speech  # type: ignore

        encoding, sample_rate = _encoding_for_mime(speech, mime)
        config_kwargs = dict(
            encoding=encoding,
            language_code="ko-KR",
            model="latest_long",
            enable_automatic_punctuation=True,
        )
        if sample_rate is not None:
            config_kwargs["sample_rate_hertz"] = sample_rate
        config = speech.RecognitionConfig(**config_kwargs)

        resp = await self.client.recognize(
            config=config,
            audio=speech.RecognitionAudio(content=audio),
        )
        parts: list[str] = []
        for result in resp.results:
            if result.alternatives:
                parts.append(result.alternatives[0].transcript)
        return " ".join(p.strip() for p in parts if p).strip()


class GoogleImage(ImageProvider):
    """Imagen image generation via google-genai.

    Falls back to the offline :class:`MockImage` placeholder on ANY error so the
    e-book always shows a picture (Imagen may require billing on the project).
    """

    backend = "google"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = _make_genai_client(self._api_key)
        return self._client

    async def generate(self, prompt: str) -> str:
        try:
            types = _genai_types()
            resp = await self.client.aio.models.generate_images(
                model=IMAGEN_MODEL,
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="4:3",
                ),
            )
            image_bytes = resp.generated_images[0].image.image_bytes
            b64 = base64.b64encode(image_bytes).decode("ascii")
            return "data:image/png;base64," + b64
        except Exception:
            # Any failure (missing SDK, no billing, network, empty result) ->
            # deterministic offline SVG so the e-book page is never blank.
            from app.providers.mock_provider import MockImage

            return await MockImage().generate(prompt)


class GoogleEmbedding(EmbeddingProvider):
    """``gemini-embedding-001`` embeddings via google-genai."""

    backend = "google"

    def __init__(self, api_key: str, dim: int = GOOGLE_EMBED_DIM) -> None:
        self._api_key = api_key
        self._client = None
        self.dim = dim or GOOGLE_EMBED_DIM

    @property
    def client(self):
        if self._client is None:
            self._client = _make_genai_client(self._api_key)
        return self._client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        types = _genai_types()
        # Defensive against a single-string vs list shape.
        contents = [texts] if isinstance(texts, str) else list(texts)
        resp = await self.client.aio.models.embed_content(
            model=GEMINI_EMBED_MODEL,
            contents=contents,
            config=types.EmbedContentConfig(output_dimensionality=self.dim),
        )
        return [list(e.values) for e in resp.embeddings]


def _encoding_for_mime(speech, mime: str):
    """Map a browser/upload MIME type to a (RecognitionConfig encoding, sample_rate).

    Returns ``sample_rate=None`` to omit ``sample_rate_hertz`` for formats where the
    sample rate is read from the audio header / is unknown.
    """
    enc = speech.RecognitionConfig.AudioEncoding
    m = (mime or "").split(";")[0].strip().lower()
    if m in ("audio/webm", "audio/ogg"):
        return enc.WEBM_OPUS, 48000
    if m in ("audio/wav", "audio/x-wav"):
        return enc.LINEAR16, None
    if m in ("audio/mp3", "audio/mpeg"):
        return enc.MP3, None
    return enc.ENCODING_UNSPECIFIED, None


__all__ = [
    "GoogleLLM",
    "GoogleSTT",
    "GoogleImage",
    "GoogleEmbedding",
    "GEMINI_LLM_DEFAULT",
    "GEMINI_EMBED_MODEL",
    "IMAGEN_MODEL",
    "GOOGLE_EMBED_DIM",
]
