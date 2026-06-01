# Memory Rhythm — SHARED CONTRACT

Authoritative interface spec for the **Memory Rhythm** dementia cognitive-companion
web demo (Korean AI Rookie competition). This demo simulates a hardware product
(D1 phone-handset + D2 autobiography e-book) entirely in the browser.

All later agents MUST build against the symbols, field names and behaviors defined
here. Field names are **byte-for-byte identical** between `backend/app/schemas.py`
and `frontend/src/protocol.ts`.

---

## 0. TOP PRIORITY — RUN WITH ZERO SECRETS

- Backend default config: `AI_PROVIDER=mock`, `STORE=memory`.
- It MUST boot and serve a full conversation loop with **no database** and **no API keys**.
- Set `AI_PROVIDER=openai` (+ `OPENAI_API_KEY`) to use real GPT-4o / GPT-4o-mini /
  Whisper / TTS / gpt-image-1 / embeddings.
- The `mock` provider returns deterministic, **Korean**, demo-friendly canned/templated
  responses so the scripted demo scenario (plan §10, the "시장"/market recall) works offline.
- `docker-compose` (postgres+pgvector / neo4j / redis / minio) is provided for M1+,
  but the app must NOT require it. An in-memory store (`store.py`) backs everything.
- Python 3.12, managed via `uv`. Frontend: React 18 + Vite + TypeScript + Tailwind.

### Language
All user-facing strings, AI prompts, and mock responses are in **Korean**.
Code identifiers/comments in English (concise).

### Run commands
```
# backend (from backend/ dir)
uv run uvicorn app.main:app --reload --port 8000

# frontend (from frontend/ dir)
npm install && npm run dev      # Vite at http://localhost:5173, proxies /api and /ws -> :8000
```

---

## 1. ENVIRONMENT / CONFIG (`app/config.py` -> `get_settings()`)

| Setting        | Env var          | Default    | Notes                                   |
|----------------|------------------|------------|-----------------------------------------|
| `ai_provider`  | `AI_PROVIDER`    | `mock`     | global default: `mock` \| `openai` \| `google` |
| `store`        | `STORE`          | `memory`   | `memory` (only one needed for demo)     |
| `openai_api_key` | `OPENAI_API_KEY` | `None`   | required only when an openai capability is selected |
| `cors_origin`  | —                | `http://localhost:5173` |                            |

> **Per-capability provider selection (additive).** Provider choice is per
> capability; `AI_PROVIDER` is just the global default. Each capability may be
> overridden via `LLM_PROVIDER` / `STT_PROVIDER` / `TTS_PROVIDER` /
> `IMAGE_PROVIDER` / `EMBEDDING_PROVIDER` (each `mock | openai | google`, default
> = `AI_PROVIDER`). Google uses the Gemini API key (`GOOGLE_API_KEY` /
> `GEMINI_API_KEY`) for LLM/Image/Embedding and Google Cloud Speech-to-Text
> (`GOOGLE_APPLICATION_CREDENTIALS` / `GOOGLE_CLOUD_PROJECT`) for STT; there is
> **no Google TTS** (google TTS → silent mock). If a selected provider's
> credentials/SDK are missing, that capability transparently falls back to
> `mock` (the app never crashes). `GET /api/health` reports the effective
> backends via the additive `providers` field. See README "AI provider
> configuration" and `.env.example`.

---

## 2. PROVIDER INTERFACES (`app/providers/base.py`)

Model-name constants (centralized; mock ignores them):
```
REASONING_MODEL = "gpt-4o"        # the "두뇌": reasoner
DIALOGUE_MODEL  = "gpt-4o-mini"   # the "입": natural utterance
```

Abstract classes (exact method signatures):
```python
class LLMProvider(ABC):
    async def complete(self, messages: list[dict], model: str,
                       temperature: float = 0.7, max_tokens: int | None = None) -> str
    async def complete_json(self, messages: list[dict], model: str,
                            schema_hint: str = "") -> dict      # parsed JSON dict (reasoner uses this)

class STTProvider(ABC):
    async def transcribe(self, audio: bytes, mime: str = "audio/webm") -> str

class TTSProvider(ABC):
    async def synthesize(self, text: str, voice: str = "alloy") -> bytes   # mp3 bytes; mock returns b""

class ImageProvider(ABC):
    async def generate(self, prompt: str) -> str   # image URL or data: URI; mock = deterministic placeholder

class EmbeddingProvider(ABC):
    async def embed(self, texts: list[str]) -> list[list[float]]
    # mock: deterministic hashed pseudo-vector (dim 256); openai: text-embedding-3-large
```

Bundle + factory:
```python
@dataclass
class Providers:
    llm: LLMProvider
    stt: STTProvider
    tts: TTSProvider
    image: ImageProvider
    embedding: EmbeddingProvider

# providers/__init__.py
def get_providers(settings) -> Providers   # choose openai_provider | mock_provider by settings.ai_provider
```

`EMBEDDING_DIM = 256` (mock pseudo-vector dimension).

---

## 3. WEBSOCKET PROTOCOL — `ws://localhost:8000/ws/session/{session_id}`

All messages are JSON text. A `"type"` field discriminates. Models live in
`app/schemas.py`; the TS mirror is in `frontend/src/protocol.ts`.

### Client -> Server
| `type`          | fields                              | meaning |
|-----------------|-------------------------------------|---------|
| `start_session` | `patient_id: string`                | optional; server may auto-create a demo patient if omitted/unknown |
| `user_message`  | `text: string`                      | a turn from the patient |
| `advance_time`  | `days: number`                      | time-acceleration; emits `recall_prompt`(s) now due |
| `toggle_tone`   | `on: boolean`                       | 40Hz gamma tone on/off (server just acks; frontend plays audio) |

### Server -> Client (several may be emitted per user turn, in THIS order)
| `type`               | fields | when |
|----------------------|--------|------|
| `reasoning`          | `decision: object, latency_ms: number, model: string` | the 두뇌 decision, shown in reasoning-chain panel. `decision` = `{stage, next_stage, hint_level, recall_detected, keywords, reason}` |
| `stage_change`       | `stage: number, label: string` | only when stage changes |
| `assistant_message`  | `text: string, stage: number, hint_level: number` | the 입 utterance |
| `autobiography_page` | `page: {id, image_url, narrative, order_idx}` (plus `patient_id`, `session_id`) | when a memory is recalled |
| `recall_prompt`      | `text: string, memory_id: string` | forgetting-curve re-question (also via `advance_time`) |
| `audio`              | `format:"mp3", b64: string` | optional TTS; omit if mock/empty |
| `error`              | `message: string` | error |

### Stages
| stage | label        |
|-------|--------------|
| 1     | 정서 안정화   |
| 2     | 대화형 인출   |
| 3     | 행동 수행     |

Hint escalation (Stage 2), `hint_level` 0..4:
`0 질문만 / 1 카테고리 단서 / 2 주변 기억 / 3 시각 단서 / 4 직접 단서`.

---

## 4. REST API (prefix `/api`)

| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET  | `/api/health` | — | `{status:"ok", provider: string, store: string}` |
| POST | `/api/patients` | `{name, dementia_type}` | `Patient` |
| GET  | `/api/patients/{id}` | — | `Patient` |
| GET  | `/api/patients/{id}/memories` | — | `Memory[]` |
| GET  | `/api/patients/{id}/autobiography` | — | `AutobiographyPage[]` |
| GET  | `/api/patients/{id}/recall-queue` | — | `RecallItem[]` |
| POST | `/api/caregiver/intake` | `{patient_id, structured: object}` | `{ok:true}` |
| POST | `/api/community/simulate` | `{patient_id, topic}` | `{turns: [{persona, text}]}` |
| POST | `/api/stt` (optional) | multipart file `audio` | `{text: string}` |

---

## 5. DATA SHAPES (`schemas.py` + `protocol.ts`, identical field names)

```
Patient            {id, name, dementia_type, persona_profile, created_at}
                   # dementia_type in {"alzheimer","vascular","lewy"}
Memory             {id, patient_id, text, keywords: string[], recall_status, created_at}
                   # recall_status in {"unrecalled","recalled"}
AutobiographyPage  {id, patient_id, session_id, image_url, narrative, order_idx}
RecallItem         {id, memory_id, text, due_at, interval_stage}
                   # interval_stage in {1,3,7,21}
CaregiverIntake    {patient_id, structured: object}
ReasoningDecision  {stage, next_stage, hint_level, recall_detected, keywords, reason}
CommunityTurn      {persona, text}
```

---

## 6. ORCHESTRATOR BEHAVIOR (`services/orchestrator.py`)

Per `user_message`:
1. `reasoner.decide(session_state, user_text)` -> `decision` dict
   `{stage, next_stage, hint_level, recall_detected, keywords, reason}`.
   Emit `reasoning` with measured `latency_ms` + `model`.
2. If `next_stage != stage` -> update state, emit `stage_change`.
3. `memory`: extract keywords (Tier1). If `recall_detected`: mark/create a recalled
   `Memory`, then `autobiography.build_page(...)` -> emit `autobiography_page`.
4. `dialogue.say(decision, context)` -> Korean utterance. Emit `assistant_message`
   with `stage` + `hint_level`. (Optional: `tts` -> `audio`.)
5. On recall success, register 1/3/7/21-day items in `recall_queue`.

Stages: Stage1 정서 안정화 (40Hz tone + warm priming) -> Stage2 대화형 인출 (hint 0->4
escalation) -> Stage3 행동 수행 (세션 종료 시 자서전 페이지 확정).

MOCK reasoner must make the scripted "시장"(market) recall scenario work: escalate
hints if the user hesitates, then detect recall when a concrete place/keyword appears.
Keep in-memory per-session state (stage, hint_level, last user texts, collected
keywords) keyed by `session_id` in `store.py`.

ID/timestamp generation: `uuid4().hex` + a store-managed monotonic counter; the app
runtime (uvicorn) may use stdlib `datetime`/`uuid` freely.

---

## 7. SAFETY (40Hz audio + flicker)

- Prominent Korean 광과민성(photosensitive) seizure warning + consent gate before tone.
- Always-available OFF control. Default tone OFF until consent.
- Warm/calm palette, large tap targets for elderly users.

---

## 8. EXPORTED SYMBOL NAMES (for imports)

`app/schemas.py`:
`DementiaType`, `RecallStatus`, `IntervalStage`,
`Patient`, `Memory`, `AutobiographyPage`, `RecallItem`, `CaregiverIntake`,
`ReasoningDecision`, `CommunityTurn`,
`StartSession`, `UserMessage`, `AdvanceTime`, `ToggleTone`, `ClientMessage`,
`ReasoningMsg`, `StageChange`, `AssistantMessage`, `AutobiographyPageMsg`,
`RecallPrompt`, `AudioMsg`, `ErrorMsg`, `ServerMessage`,
`CreatePatientRequest`, `MemoriesResponse`, `AutobiographyResponse`,
`RecallQueueResponse`, `CaregiverIntakeRequest`, `OkResponse`,
`CommunitySimulateRequest`, `CommunitySimulateResponse`, `SttResponse`, `HealthResponse`,
`STAGE_LABELS`, `stage_label`.

`app/providers/base.py`:
`LLMProvider`, `STTProvider`, `TTSProvider`, `ImageProvider`, `EmbeddingProvider`,
`Providers`, `REASONING_MODEL`, `DIALOGUE_MODEL`, `EMBEDDING_DIM`.

`frontend/src/protocol.ts`:
types `DementiaType`, `RecallStatus`, `IntervalStage`,
`Patient`, `Memory`, `AutobiographyPage`, `RecallItem`, `CaregiverIntake`,
`ReasoningDecision`, `CommunityTurn`,
`StartSession`, `UserMessage`, `AdvanceTime`, `ToggleTone`, `ClientMessage`,
`ReasoningMsg`, `StageChange`, `AssistantMessage`, `AutobiographyPageMsg`,
`RecallPrompt`, `AudioMsg`, `ErrorMsg`, `ServerMessage`,
`CreatePatientRequest`, `CaregiverIntakeRequest`, `OkResponse`,
`CommunitySimulateRequest`, `CommunitySimulateResponse`, `SttResponse`, `HealthResponse`,
const `STAGE_LABELS`, const `REASONING_MODEL`, `DIALOGUE_MODEL`.

Survey additions (STEP 1, see §9):
- `app/schemas.py`: `SurveyQuestionData`, `SurveyResult`,
  `StartSurvey`, `SurveyAnswer`, `SkipQuestion`, `SurveyClientMessage`,
  `SurveyCaptureMsg`, `SurveyQuestionMsg`, `SurveyCompleteMsg`, `SurveyServerMessage`
  (`ErrorMsg` is reused for survey errors).
- `frontend/src/protocol.ts`: same names as TS types/interfaces.

---

## 9. STEP 1 — 초기 설문 (Survey) — ADDITIVE

A **patient-facing AI-persona conversational onboarding** that SETS THE USER'S
CONTEXT for the therapy flow. It lives at a NEW dedicated frontend route
`/survey` (separate from `/patient` therapy and `/caregiver` structured intake).
It conducts a thorough ~10-12 question survey across life domains, with question
text/emphasis **branched by dementia type**, classifies each answer as
recallable / unrecallable, builds a `persona_profile`, and **seeds** the
patient's data so the therapy call uses real context.

This is **purely additive**. It does NOT change the therapy WS/REST shapes, the
Stage 1/2/3 flow, the provider system, or the google/per-capability work. The
survey uses its OWN WS endpoint and its OWN message unions (separate pydantic
discriminated unions `SurveyClientMessage` / `SurveyServerMessage`). Works FULLY
OFFLINE in mock mode (scripted questions, heuristic classification, templated
Korean summary; LLM-generated summary when the LLM backend is real).

### 9.1 WebSocket — `ws://localhost:8000/ws/survey/{session_id}`

All messages are JSON text; a `"type"` field discriminates. Per-session state is
kept in `store.py` keyed by `session_id`.

**Client -> Server** (`SurveyClientMessage`, discriminator `type`)

| `type`            | fields                                                                   | meaning |
|-------------------|--------------------------------------------------------------------------|---------|
| `start_survey`    | `patient_id: string \| null`, `name: string`, `dementia_type: DementiaType` | begin: create/get patient, init state, emit first `survey_question` |
| `survey_answer`   | `text: string`                                                           | the patient's answer to the current question |
| `skip_question`   | —                                                                        | optional; treat as an unrecallable/declined answer and advance |

**Server -> Client** (`SurveyServerMessage`, discriminator `type`) — per turn, in THIS order:

| `type`             | fields | when |
|--------------------|--------|------|
| `survey_capture`   | `domain: string`, `answer: string`, `keywords: string[]`, `recallable: boolean` | emitted for the PREVIOUS answer (NOT on the very first question) |
| `survey_question`  | `index, total, domain, text, preface` (= `SurveyQuestionData`) | the next question; on start, the first question (no preceding capture). `preface` = optional warm persona reaction to the previous answer ("" first) |
| `survey_complete`  | `result: SurveyResult` | after the last answer; REPLACES `survey_question` |
| `error`            | `message: string` | error (reuses therapy `ErrorMsg`) |

### 9.2 REST (prefix `/api`)

| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET | `/api/patients/{patient_id}/survey` | — | `SurveyResult` (404 if none yet) |

### 9.3 Data shapes (`schemas.py` + `protocol.ts`, identical field names)

```
SurveyQuestionData {index, total, domain, text, preface}
                   # preface = warm persona reaction to previous answer ("" first)
SurveyResult       {patient_id, name, dementia_type, profile: object,
                    recallable_keywords: string[], unrecallable_topics: string[],
                    summary: string, seeded_memory_count: number, completed_at: string}
                   # profile = {name, era, dementia_type, domains:{domainKey: answerText},
                   #            recallable_keywords:[...], unrecallable_topics:[...], summary}
```

### 9.4 Question bank (branched by dementia type)

~12 domains per type; suggested keys: `name_era, childhood_place, family, work,
daily_routine, food, music_media, season_nature, relationships, hardship,
cherished_memory, hope_message`. Branching is the whole point:
- **alzheimer**: lead with well-preserved REMOTE memories (childhood/youth) to
  build confidence, then INTERSPERSE 1-2 RECENT-memory probes (likely classified
  UNRECALLABLE). Warm, repetition-tolerant phrasing.
- **vascular**: shorter, more CONCRETE/STRUCTURED, fact-oriented questions (one
  clear thing at a time); fewer open-ended; gentle, sequential.
- **lewy**: VISUAL/scene-based prompts and acknowledge FLUCTUATION; gentler pacing.

### 9.5 Classification + seeding (deterministic; no LLM required)

Per answer:
- `keywords = MemoryService.extract_keywords(answer)`
- `hesitated` = empty/skip OR contains a hesitation marker
  (`모르`, `기억 안`, `기억이 안`, `글쎄`, `생각이 안`, `잘 모`, `몰라`, `가물`, `흐릿`, `...`)
  OR no substantive keyword.
- `recallable = (not hesitated) and len(keywords) >= 1`
- accumulate a keyword frequency Counter across recallable answers.

On completion:
- `recallable_keywords` = keywords ranked by frequency desc then first-seen,
  deduped, top ~12.
- `unrecallable_topics` = human Korean label of each domain classified
  unrecallable (domain->label map).
- SEED: for each RECALLABLE answer,
  `await MemoryService.store_memory(patient_id, text=answer, keywords=..., recall_status="recalled")`;
  count as `seeded_memory_count`.
- `profile` = `{name, era, dementia_type, domains, recallable_keywords, unrecallable_topics, summary}`.
- `summary`: mock -> templated 2-3 sentence Korean narrative from name + top
  keywords + count; real LLM -> warm 2-3 Korean sentences via
  `providers.llm.complete` (settings.reasoning_model), deterministic fallback to
  the template on error.
- persist: `store.save_survey_result(patient_id, result)` and
  `store.update_patient_profile(patient_id, summary)` (Patient.persona_profile
  becomes the summary string; field stays `str`). Seeded memories live under the
  same `patient_id`, so the therapy flow + autobiography + `/api/patients/{id}/memories`
  automatically see them.

### 9.6 Frontend wiring

- Route `/survey` -> `Survey.tsx`; top-nav link "초기 설문".
- `src/lib/ws.ts`: add a `SurveySocket` (typed over `SurveyClientMessage` /
  `SurveyServerMessage`) targeting `/ws/survey/{id}` WITHOUT breaking the therapy
  `WSClient`; helpers `startSurvey(patientId, name, type)`, `sendSurveyAnswer(text)`,
  `skipQuestion()`, `onMessage(cb)`.
- `src/lib/api.ts`: add `getSurvey(patientId)` -> GET `/api/patients/{id}/survey`.
- `src/pages/Patient.tsx`: accept optional `?patient=` query param; if present,
  use it as `patient_id` in `start_session` + REST calls so the surveyed patient's
  seeded context is used. If absent, current default demo behavior is unchanged.
- `SurveyProfileCard` "이 어르신과 통화 시작하기 →" navigates to `/patient?patient={patient_id}`.
