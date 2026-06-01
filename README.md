# Memory Rhythm — 치매 인지 동반자 AI 웹 데모

> 2026 인공지능 루키 대회 (국내 AI 트랙) · 치매 인지 동반자 AI
> 제안서의 하드웨어 제품(**D1 수화기** + **D2 자서전 e-book**)을 **웹 브라우저에서 시뮬레이션**하여,
> 핵심 소프트웨어 파이프라인(이중 LLM · 트리플 레이어 기억 유도 · 자서전 그림책)을 실제로 작동시키는 데모입니다.

자세한 기획·일정·아키텍처는 [`plan.md`](./plan.md), 모든 인터페이스 계약은 [`CONTRACT.md`](./CONTRACT.md) 를 참고하세요.

---

## 한 줄 정의

**"전화기 모양 화면으로 환자와 대화하며 기억을 끌어내고, 그 기억이 자서전 그림책으로 채워지는 과정을 심사위원이 눈으로 보게 한다."**

화면은 **좌(통화 · Handset) / 우(자서전 · E-book)** 로 분할되어 듀얼 디바이스를 재현합니다.
보호자 포털(문진 · 기억 그래프 · 망각곡선 재질문 큐)은 별도 라우트입니다.

---

## 핵심: 비밀키 0개로 즉시 실행 (Zero-Secret Demo)

백엔드 기본 설정은 **`AI_PROVIDER=mock`, `STORE=memory`** 입니다.

- **데이터베이스 불필요** — 인메모리 저장소(`store.py`)가 환자/세션/기억/자서전/재질문 큐를 모두 보관합니다.
- **API 키 불필요** — `mock` 프로바이더가 결정론적·한국어·데모 친화적 응답을 돌려주므로, 시나리오(아래 §데모 시나리오, plan §10의 "시장" 회상)가 **오프라인으로 그대로 작동**합니다.
- `docker-compose`(postgres/neo4j/redis/minio)는 M1+ 용으로 제공되지만 **데모 실행에는 필요 없습니다.**

실제 모델을 쓰려면 `AI_PROVIDER=openai` + `OPENAI_API_KEY` 만 설정하면 됩니다 (코드/흐름 변경 0).

---

## 투-트랙 AI 정책 (데모 = 외산 · 제출 = 국내)

모든 AI 호출은 `backend/app/providers/` 어댑터 패턴으로 추상화되어 있습니다 (`LLMProvider`,
`STTProvider`, `TTSProvider`, `ImageProvider`, `EmbeddingProvider`). **흐름·UI 코드는 인터페이스에만 의존**합니다.

| 역할 | 데모 — OpenAI | 데모 — Google | 제출본 (국내 AI 트랙) |
|---|---|---|---|
| 두뇌 Reasoning | OpenAI **GPT-4o** | **Gemini 2.5 Flash** | LG EXAONE 4.0 32B |
| 입 Dialogue | OpenAI **GPT-4o-mini** | **Gemini 2.5 Flash** | Upstage Solar Pro 3 |
| STT | OpenAI Whisper | **Google Cloud STT** | KT 기가지니 STT |
| TTS | OpenAI TTS (선택 ElevenLabs) | — (무음 mock) | NC VARCO Voice |
| Image | OpenAI gpt-image-1 | **Imagen 3** | NC VARCO Vision |
| Embedding | OpenAI text-embedding-3-large | **gemini-embedding-001** | Upstage Solar Embedding |

세 번째 트랙 **`mock`** 은 위 어떤 키도 없이 데모를 돌리기 위한 결정론적 구현입니다.
프로바이더는 **역량별로** 섞을 수 있습니다(예: TTS만 mock, 나머지는 Google) —
아래 [AI provider configuration](#ai-provider-configuration-역량별-프로바이더-선택)
참고. 제출 시에는 `providers/` 에 국내 구현을 추가하고 `*_PROVIDER` 환경변수만
바꾸면 됩니다.

---

## 실행 방법

> **사전 요구사항**: Python 3.12 + [`uv`](https://docs.astral.sh/uv/) (백엔드).
> 프런트엔드에는 **Node.js 18+** 이 필요합니다.
> ⚠️ **이 머신에는 Node 가 설치되어 있지 않습니다.** 프런트엔드를 실행하려면 먼저
> [nodejs.org](https://nodejs.org/) 에서 Node 18+ (LTS 권장) 를 설치하세요. 백엔드만으로도
> REST/WebSocket API 는 완전히 동작하므로, Node 없이도 백엔드 테스트는 가능합니다.

### (A) 백엔드 — mock 모드, 키 없이 부팅

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

- 기본값 `AI_PROVIDER=mock`, `STORE=memory` 로 즉시 부팅합니다.
- 헬스 체크: <http://localhost:8000/api/health> → `{"status":"ok","provider":"mock","store":"memory"}`
- WebSocket 대화: `ws://localhost:8000/ws/session/{session_id}`

### (B) 프런트엔드 — Vite dev 서버

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 (Vite가 /api·/ws 를 :8000 으로 프록시)
```

브라우저에서 <http://localhost:5173> 접속 → 좌 Handset / 우 E-book / `/caregiver` 보호자 포털.

### (C) (선택) 데이터베이스 스택 — M1+ 에서만

```bash
docker compose up -d   # postgres(pgvector) + neo4j + redis + minio
```

데모 실행에는 **필요 없습니다.** 영속 계층을 붙이기 시작하는 M1 이후에만 사용하세요.

---

## 실제 OpenAI 로 전환하기

```bash
# 1) 환경 템플릿 복사
cp .env.example backend/.env

# 2) backend/.env 편집
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...        # 본인 키
# (선택) ELEVENLABS_API_KEY=...   # 한국어 TTS 자연도 향상용

# 3) 평소처럼 실행
cd backend && uv run uvicorn app.main:app --reload --port 8000
```

전환 후 동일한 흐름으로 실제 GPT-4o(두뇌) / GPT-4o-mini(입) / Whisper(STT) /
TTS / gpt-image-1(자서전 이미지) / text-embedding-3-large(임베딩) 가 사용됩니다.
키는 **백엔드 서버 환경변수로만** 다루며 프런트엔드에 노출되지 않습니다.

---

## AI provider configuration (역량별 프로바이더 선택)

프로바이더는 **역량(capability)별로 따로** 고를 수 있습니다. 전역 기본값
`AI_PROVIDER` 가 모든 역량의 기본 백엔드를 정하고, 각 역량은 아래 환경변수로
독립적으로 덮어쓸 수 있습니다. 유효 값은 모두 `mock | openai | google` 입니다.

| 역량 | 환경변수 | 기본값 | `mock` | `openai` | `google` |
|---|---|---|---|---|---|
| 두뇌+입 (LLM) | `LLM_PROVIDER` | `AI_PROVIDER` | 결정론적 한국어 | GPT-4o / GPT-4o-mini | Gemini 2.5 Flash (Gemini API) |
| STT | `STT_PROVIDER` | `AI_PROVIDER` | 더미 텍스트 | Whisper | **Google Cloud Speech-to-Text** |
| TTS | `TTS_PROVIDER` | `AI_PROVIDER` | 무음 (빈 오디오) | OpenAI TTS | — (Google TTS 미구현 → mock 무음) |
| Image | `IMAGE_PROVIDER` | `AI_PROVIDER` | 오프라인 SVG 플레이스홀더 | gpt-image-1 | Imagen 3 (Gemini API) |
| Embedding | `EMBEDDING_PROVIDER` | `AI_PROVIDER` | 해시 의사벡터(256) | text-embedding-3-large | gemini-embedding-001(768) |

### Mock 폴백 (비밀키 0개로도 절대 죽지 않음)

선택한 프로바이더의 **자격증명 또는 SDK 가 없으면**, 해당 역량만 조용히 `mock`
구현으로 폴백합니다(앱은 절대 크래시하지 않음). 예: `IMAGE_PROVIDER=google`
인데 `GOOGLE_API_KEY` 가 없으면 그 역량만 mock 이미지로 떨어지고 나머지는
정상 동작합니다. Google/OpenAI SDK 는 **지연 import** 되므로 mock 데모에는
어떤 SDK 도 설치할 필요가 없습니다. 실제 백엔드 확인은
`GET /api/health` 응답의 `providers` 필드(`{llm, stt, tts, image, embedding}`)로
할 수 있습니다 — 폴백이 일어났다면 여기에 `mock` 으로 표시됩니다.

### 레시피: TTS만 빼고 전부 Google

이 데모의 권장 Google 구성입니다 — **LLM·Image·Embedding 은 Gemini API
키 하나(`GOOGLE_API_KEY`)**, **STT 는 Google Cloud Speech-to-Text(별도
자격증명)**, **TTS 는 무음 mock**.

```bash
# backend/.env (또는 환경변수)
AI_PROVIDER=google
TTS_PROVIDER=mock                 # Google TTS 는 구현하지 않음 → 무음 mock

# Gemini API 키 (AI Studio) — LLM(두뇌+입) / Image(Imagen) / Embedding
GOOGLE_API_KEY=AIza...            # GEMINI_API_KEY 로 줘도 동일하게 인식

# Google Cloud Speech-to-Text 는 Gemini 키가 아니라 ADC/서비스 계정을 사용
STT_PROVIDER=google
GOOGLE_CLOUD_PROJECT=my-gcp-project
GOOGLE_APPLICATION_CREDENTIALS=C:\path\to\service-account.json
```

- 두뇌·입 모델은 둘 다 `gemini-2.5-flash` 로 자동 해석됩니다(필요하면
  `REASONING_MODEL` / `DIALOGUE_MODEL` 로 덮어쓰기).
- `GOOGLE_API_KEY` 와 `GEMINI_API_KEY` 는 동일 키의 별칭입니다(둘 다 있으면
  `GOOGLE_API_KEY` 우선).
- STT 자격증명은 Gemini 키와 **무관**합니다. `GOOGLE_APPLICATION_CREDENTIALS`
  (또는 ADC) 와 `GOOGLE_CLOUD_PROJECT` 중 하나라도 있으면 Cloud STT 를 사용하고,
  없으면 mock STT 로 폴백합니다.

> **Imagen 주의:** Imagen(이미지 생성)은 Google 프로젝트에 **결제(billing)가
> 활성화**되어 있어야 할 수 있습니다. 키/권한/결제 문제로 호출이 실패하면, 해당
> 자서전 페이지는 오프라인 **SVG 플레이스홀더**로 자동 폴백하여 그림책에 항상
> 그림이 채워집니다.

설정 전체 예시는 [`.env.example`](./.env.example) 의 프리셋 블록을 참고하세요.

---

## 데모 시나리오 (심사위원이 보는 90초~3분 · plan §10)

1. 좌측 전화기에서 **"통화"** 클릭 → AI 페르소나가 따뜻하게 말을 건넨다 (**Stage 1 정서 안정화**, 광과민성 안전 고지·동의 후 40Hz tone ON).
2. "옛날에 자주 가시던 곳이 있나요?" → 환자가 머뭇거리면 **힌트가 0→2단계로 자연스럽게 상승** (두뇌=GPT-4o 가 hint escalation 결정, 입=GPT-4o-mini 가 부드럽게 표현 — Reasoning 패널에 모델·지연·결정이 실시간 표시되어 **이중 LLM 분리**를 증명).
3. **"시장"** 키워드 회상 성공 → 우측 패널에 그 장면 **그림 한 장 + narrative 한 문장**이 추가된다 (**Stage 2 → 자서전 페이지**).
4. **Stage 3 행동 수행** 으로 세션 종료 → 자서전 페이지가 확정되고, **"3일 뒤"(시간 가속)** 토글을 누르면 재질문 큐에서 *"그 시장 이야기 더 들려주실래요?"* 가 뜬다 (1·3·7·21일 망각곡선 엔진).
5. (결선) 같은 키워드를 가진 가상 또래와의 그룹 대화로 전환 → 공동체 소속감 회복.

힌트 단계: `0 질문만 / 1 카테고리 단서 / 2 주변 기억 / 3 시각 단서 / 4 직접 단서`.
치료 단계: `Stage 1 정서 안정화 → Stage 2 대화형 인출 → Stage 3 행동 수행`.

---

## STEP 1 — 초기 설문 (Initial Survey)

통화 치료에 들어가기 **전에**, AI 페르소나가 어르신과 대화하며 삶의 맥락을
끌어내는 **대화형 온보딩**입니다. (plan.md STEP 1) 전용 라우트 `/survey` 에서
진행되며, 치료 흐름(`/patient`)·보호자 문진(`/caregiver`)과는 **별개**입니다.

- **치매 유형별 분기 질문 ~12개** — 알츠하이머 / 혈관성 / 루이체에 따라 질문
  문구와 강조점이 달라집니다. (예: 알츠하이머는 잘 보존된 **먼 과거(유년·청년기)**
  로 자신감을 쌓은 뒤 **최근 기억 탐침**을 사이에 끼워 넣고, 혈관성은 짧고
  **구체적·구조화된** 사실 질문, 루이체는 **장면·시각 중심** 질문과 **기복**
  인정으로 부드럽게 진행).
- **답변마다 Tier-1 키워드 추출 + 회상 가능/불가 분류** — 빈도·머뭇거림
  휴리스틱으로 `recallable` / `unrecallable` 을 즉석에서 판정하여 화면에
  녹색(회상 가능 키워드) / 호박색(회상 못 한 주제) 칩으로 실시간 표시합니다.
- **완료 시 페르소나 프로필 생성 + 환자 데이터 시딩** — 회상 가능한 답변을
  `recall_status="recalled"` 일화 기억으로 **치료와 동일한 인메모리 저장소
  (patient_id 기준)** 에 기록하고, 환자의 `persona_profile` 요약을 설정하며,
  `SurveyResult` 를 보관합니다. 이후 통화·자서전·`/api/patients/{id}/memories`
  가 이 실제 맥락을 자동으로 사용합니다.

### 사용 방법

1. 브라우저에서 <http://localhost:5173/survey> 접속 (상단 내비 **"초기 설문"**).
2. **이름** 입력 + **치매 유형**(알츠하이머 / 혈관성 / 루이체) 선택 → **"설문 시작"**.
3. 페르소나가 던지는 질문 ~12개에 한 줄씩 답합니다. 기억이 안 나면
   **"잘 모르겠어요 / 건너뛰기"** 로 넘어갈 수 있습니다 (해당 주제는 회상 불가로
   분류). 진행률 바와 우측 "수집된 기억 단서" 패널이 함께 차오릅니다.
4. 마지막 답변 후 **페르소나 프로필 카드**(이름·요약·키워드·시딩된 기억 수)가
   뜨고, **"이 어르신과 통화 시작하기 →"** 를 누르면 해당 `patient_id` 를 달고
   `/patient?patient={patient_id}` 로 이동하여 **설문에서 시딩된 맥락 그대로**
   통화 치료가 시작됩니다.

### mock 모드로 완전 동작

설문은 **비밀키 0개**로 끝까지 작동합니다 — 질문은 스크립트, 분류는 휴리스틱,
요약은 mock 에서 템플릿으로 생성됩니다. 실제 LLM 백엔드(`AI_PROVIDER` 가
`mock` 이 아닐 때)에서는 요약만 LLM 이 생성하고, 오류 시 템플릿으로 자동
폴백합니다. 별도 WebSocket 엔드포인트 `ws://localhost:8000/ws/survey/{session_id}`
와 REST `GET /api/patients/{patient_id}/survey` 를 사용하며, 기존 치료
WS/REST 계약은 건드리지 않습니다.

---

## 안전 고지 (40Hz 시청각 자극)

40Hz gamma tone 과 백라이트 플리커는 **광과민성(photosensitive) 발작 경고 + 동의 절차** 뒤에서만 활성화됩니다.
기본값은 **OFF** 이며, **끄기 버튼이 항상 노출**됩니다. 노년층을 위한 따뜻하고 차분한 팔레트와 큰 탭 영역을 사용합니다.

---

## 프로젝트 구조

```
ad_pg_team_pj/
├─ plan.md                 # 개발 계획서
├─ CONTRACT.md             # 인터페이스 계약 (스키마·WS·REST·프로바이더)
├─ docker-compose.yml      # (선택) postgres+pgvector / neo4j / redis / minio
├─ .env.example            # 환경변수 템플릿 (기본 mock, 키 불필요)
├─ backend/                # FastAPI (Python 3.12, async) — import root = "app"
│  └─ app/
│     ├─ main.py           # FastAPI 앱 + CORS + 라우터 + WS + /api/health
│     ├─ config.py         # get_settings()
│     ├─ schemas.py        # 모든 pydantic 모델 (WS + REST 계약)
│     ├─ store.py          # 인메모리 저장소 싱글톤
│     ├─ ws.py             # WebSocket 엔드포인트
│     ├─ providers/        # AI 어댑터 (mock | openai), base.py 인터페이스
│     ├─ services/         # orchestrator / reasoner / dialogue / memory /
│     │                    #   autobiography / community
│     └─ routers/          # patients / autobiography / caregiver / community
└─ frontend/               # React 18 + Vite + TypeScript + Tailwind
   └─ src/
      ├─ protocol.ts        # schemas.py 와 필드명 1:1 미러
      ├─ pages/             # Patient.tsx (좌 Handset / 우 Ebook), Caregiver.tsx
      └─ components/        # Handset / Ebook / GammaTone / SafetyNotice /
                            #   ReasoningPanel / IntakeForm / MemoryGraph / RecallQueue
```

---

## 라이선스 / 데이터

데모는 **합성 데이터만** 사용하며 실제 환자 정보를 다루지 않습니다.
모든 AI 호출은 백엔드를 경유하고, API 키는 서버 환경변수로만 관리됩니다.
