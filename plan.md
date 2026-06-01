# Memory Rhythm — 웹 데모 개발 계획서 (plan.md)

> 치매 인지 동반자 AI · 2026 인공지능 루키 대회 (국내 AI 트랙)
> 본 문서는 **제안서의 하드웨어 제품(D1 수화기 + D2 자서전 디스플레이)을 웹 브라우저에서 시뮬레이션**하여,
> 핵심 소프트웨어 파이프라인(이중 LLM, 트리플 레이어 기억 유도, 자서전 그림책)을 실제로 구현·시연하기 위한 개발 계획이다.
> 담당: 프로그래밍 전반 (팀장) · 작성일 기준: 2026-06-01
>
> ⚙️ **이번 데모의 AI 정책**: 개발 속도를 위해 **사용하기 편한 외산 API(OpenAI 중심)** 로 먼저 구현한다.
> 단, 대회 제출본은 **국내 AI 트랙**이므로 모든 AI 호출은 어댑터 패턴으로 추상화해 **국내 AI(KT/Upstage/LG/NC)로 1:1 교체 가능**하게 만든다.
> (즉 데모는 외산, 최종 제출은 국내 — 흐름 코드는 동일)

---

## 1. 데모의 목적과 한 줄 정의

**"전화기 모양의 화면으로 환자와 대화하며 기억을 끌어내고, 그 기억이 자서전 그림책으로 채워지는 과정을 심사위원이 직접 눈으로 보게 한다."**

- 제안서의 추상적 메커니즘(감각 priming → 대화형 인출 → 행동 수행)을 **실제로 작동하는 화면**으로 증명한다.
- 하드웨어 펌웨어/BLE는 본 데모 범위에서 제외하고, **웹 UI가 D1·D2를 대체**한다.
- 본선(8/19~8/27) 시연 영상과 결선(11/3~11/5) 라이브 데모의 기반 코드가 된다.

---

## 2. 웹 데모의 범위 (Scope)

### 2.1 하드웨어 → 웹 매핑

| 제안서 하드웨어 | 웹 데모에서의 대체 | 비고 |
|---|---|---|
| D1 수화기형 본체 (다이얼 8단계) | 화면 왼쪽 **전화 UI** (다이얼/통화 버튼) | 클릭으로 기능 선택 |
| 수화기 마이크 → KT STT | 브라우저 마이크 → **OpenAI Whisper API** | 한국어 인식 강함, 키 하나로 즉시 사용 |
| 수화기 스피커 40Hz + TTS | Web Audio API (40Hz gamma tone) + **OpenAI/ElevenLabs TTS** | ⚠️ 광·청각 자극 안전 고지 필수 |
| PPG 심박 센서 | 슬라이더/모의 BPM 생성기 | 실제 센서값 대신 시뮬레이션 |
| D2 e-book 자서전 디스플레이 | 화면 오른쪽 **그림책 패널** + 40Hz 백라이트 플리커 | CSS/Canvas 플리커 시뮬레이션 |

> **레이아웃 핵심**: 한 화면을 **좌(통화) · 우(자서전)** 로 분할 → 듀얼 디바이스를 그대로 재현.

### 2.2 In Scope (데모에 반드시 들어가는 것)
- 대화형 초기 설문(STEP 1) — AI 페르소나와의 대화로 기억 키워드 수집
- 3단계 치료 흐름(Stage 1·2·3) — 정서 안정화 → 힌트 0~4단계 인출 → 행동 수행
- **이중 LLM 아키텍처**(두뇌 Reasoning / 입 Dialogue) 분리 호출
- 3-Tier 메모리(실시간 추출 / 세션 후 심층 추출 / 저장소)
- 자서전 그림책 자동 생성(이미지 + narrative)
- 1·3·7·21일 망각 곡선 기반 재질문 큐(데모에선 시간 가속 토글)
- 가상 또래 페르소나 그룹 대화 시뮬레이션(STEP 3 커뮤니티 cold-start)

### 2.3 Out of Scope (데모에서 제외/모킹)
- 펌웨어(FreeRTOS/Zephyr), BLE 5.0 GATT, OTA
- 실제 PPG/HealthKit 생체 연동 → 모의값
- WebRTC 실시간 다자 통화(Janus/LiveKit) → 페르소나는 서버측 시뮬레이션
- 프로덕션 배포 → 로컬 docker-compose + 단일 데모 서버

---

## 3. 시스템 아키텍처

```
[Browser - React (Vite) + TypeScript]
  ├─ 좌: Handset View (다이얼/통화/마이크/40Hz tone)
  ├─ 우: Autobiography View (그림책/플리커)
  └─ 보호자 포털 (문진 입력, 기억 그래프, 알림)
        │  WebSocket(대화 스트리밍) + REST
        ▼
[Backend - FastAPI (Python 3.12, async)]
  ├─ Dialogue Orchestrator  ── 입(Dialogue)  : GPT-4o-mini  (매 턴, 빠른 한국어 응답)
  ├─ Therapy Reasoner       ── 두뇌(Reasoning): GPT-4o / o-series (의사결정 시점만)
  ├─ STT Service            ── OpenAI Whisper (whisper-1 / gpt-4o-transcribe)
  ├─ TTS Service            ── OpenAI TTS (tts-1) · 선택: ElevenLabs(한국어 자연도↑)
  ├─ Autobiography Builder  ── 이미지: gpt-image-1(DALL·E) + narrative: GPT-4o
  ├─ Memory Service (3-Tier) ── 임베딩: text-embedding-3-large
  └─ Persona / Community Simulator
        │
        ▼
[Data Layer]
  ├─ PostgreSQL 16 + pgvector  (에피소드 기억 + 임베딩 검색)
  ├─ Neo4j                     (시맨틱 기억 그래프 · multi-hop 회상 단서 추론)
  └─ Redis 7                   (대화 state machine, hint level, 세션 캐시)
```

### 3.1 이중 LLM 분리 — 데모에서의 핵심 설명 포인트
- **두뇌(Reasoning, GPT-4o/o-series)**: Stage 전이 판단, hint 수위 escalation, 정답 판정, 모순 처리, 보호자 알림 triage. → **호출 빈도 낮음(의사결정 시점)**.
- **입(Dialogue, GPT-4o-mini)**: 두뇌의 결정을 자연스러운 한국어 발화로 표현, turn-taking. → **매 턴 호출, 지연 최소화**.
- **분리 이유(데모 멘트)**: 치매 환자에게 긴 침묵은 불안을 유발 → 무거운 추론을 대화 경로에서 분리해 응답 지연을 줄인다.
- **제출본 매핑**: 두뇌 → LG EXAONE 4.0 32B, 입 → Upstage Solar Pro 3. (어댑터만 교체)

---

## 4. 기술 스택

| 영역 | 선택 (데모) | 제출본 교체 대상 | 비고 |
|---|---|---|---|
| Frontend | **React 18 + Vite + TypeScript + Tailwind** | 동일 | 단일 SPA, 환자 시뮬/보호자 포털 라우트 분리 |
| 오디오 | Web Audio API (40Hz tone), Canvas/CSS(플리커) | 동일 | 안전 고지 모듈 포함 |
| Backend | FastAPI 3.12, async, WebSocket, Pydantic v2 | 동일 | Flask 경험 기반, async 신규 학습 |
| 작업 큐 | Celery + Redis | 동일 | 자서전 빌드·심층 추출 비동기 |
| RDB | PostgreSQL 16 + pgvector | 동일 | 에피소드 기억 의미 검색 |
| Graph | Neo4j Community (or Aura free) | 동일 | M3에서 도입 |
| Cache | Redis 7 | 동일 | 대화 상태머신, hint level |
| 오브젝트 | 로컬 / MinIO (S3 호환) | AWS S3 | 자서전 이미지 저장 |
| **STT** | OpenAI Whisper | KT 기가지니 STT | 한국어/노년층 |
| **Dialogue LLM(입)** | OpenAI GPT-4o-mini | Upstage Solar Pro 3 | 매 턴 발화 |
| **Reasoning LLM(두뇌)** | OpenAI GPT-4o / o-series | LG EXAONE 4.0 32B | 의사결정 |
| **TTS** | OpenAI TTS (선택 ElevenLabs) | NC VARCO Voice | 페르소나 음성 |
| **Image** | OpenAI gpt-image-1 (DALL·E) | NC VARCO Vision | 자서전 그림 |
| **Embedding** | OpenAI text-embedding-3-large (3072d) | Upstage Solar Embedding 1 Large | RAG 의미 검색 |
| 개발환경 | docker-compose(postgres/neo4j/redis/minio), uv/poetry | 동일 | 1-command 부팅 목표 |

> **단일 벤더 우선**: 데모는 STT·LLM·TTS·이미지·임베딩을 **OpenAI 키 하나**로 통일해 셋업을 최소화한다.
> TTS 한국어 자연도가 아쉬우면 ElevenLabs만 부분 교체.

---

## 5. 핵심 기능 (제안서 STEP·Stage 대응)

### STEP 1 — 초기 설문 (대화형)
- 세계관 가진 AI 페르소나가 사건/감정 데이터를 대화로 수집
- 치매 종류별(알츠하이머/혈관성/루이체) 질문 양식 분기
- **기억 가능 / 불가능 키워드** 빈도 기반 분별 → Tier 1 추출
- 보호자 문진은 별도 폼(구조화 파싱)

### STEP 2 — 치료법 (3단계 흐름 = 트리플 레이어)
- **Stage 1 정서 안정화**: 40Hz tone + 과거 음악/사진 priming
- **Stage 2 대화형 인출**: 정답 강요 ❌ → 힌트 **0→4단계 점진 제공**
  - 0: 질문만 / 1: 카테고리 단서 / 2: 주변 기억 / 3: 시각 단서(약병 사진 등) / 4: 직접 단서
  - 주변 기억(peripheral)으로 중심 기억(core) 회상 유도
- **Stage 3 행동 수행**: 안내 후 **세션 종료 시 자서전 페이지 자동 생성**

### STEP 2(3) — 이미지 기반 기억 도출 (자서전 그림책)
- 수집된 기억 → 이미지 생성(gpt-image-1), narrative 응축(GPT-4o)
- 그림책이 점점 채워지는 것을 우측 패널에 정기 노출 → 서사 복기

### STEP 3 — 소속 공동체
- 가상 또래 페르소나 N명을 서버에서 생성(단일 LLM system prompt 분리)
- 회복된 키워드를 주제로 그룹 대화 시뮬레이션 → 의미 기억(semantic) 전환

### 망각 곡선 엔진
- 회상 성공 기억을 **1·3·7·21일** 후 재질문 큐에 자동 등록
- 데모용 **"시간 가속" 토글**로 며칠 뒤 재질문을 즉석 시연

---

## 6. 데이터 모델 (초안)

**PostgreSQL**
- `patients(id, name, dementia_type, persona_profile_jsonb, created_at)`
- `sessions(id, patient_id, stage, started_at, ended_at, summary)`
- `episodic_memories(id, patient_id, text, embedding vector(3072), recall_status, source_turn, created_at)`
- `recall_queue(id, memory_id, due_at, interval_stage)`  ← 1/3/7/21
- `autobiography_pages(id, patient_id, session_id, image_url, narrative, order_idx)`
- `caregiver_intake(id, patient_id, structured_jsonb)`

**Neo4j** (시맨틱 그래프)
- `(:Memory)-[:RELATES_TO]->(:Memory)`, `(:Memory)-[:ABOUT]->(:Entity)`
- multi-hop 질의로 다음 회상 단서 자동 생성

**Redis**
- `session:{id}:state` (현재 Stage, hint_level, 마지막 발화 시각)

> 임베딩 차원은 사용 모델에 맞춤: text-embedding-3-large=3072, -small=1536. 제출본 Solar Embedding으로 교체 시 차원 마이그레이션 필요.

---

## 7. 디렉터리 구조 (제안)

```
memory-rhythm/
├─ docker-compose.yml          # postgres+pgvector, neo4j, redis, minio
├─ plan.md
├─ .env.example                # OPENAI_API_KEY, (ELEVENLABS_API_KEY)
├─ backend/
│  ├─ app/
│  │  ├─ main.py               # FastAPI + WebSocket 엔트리
│  │  ├─ routers/              # chat, session, autobiography, caregiver, community
│  │  ├─ services/
│  │  │  ├─ orchestrator.py    # 대화 흐름 상태머신
│  │  │  ├─ reasoner.py        # 두뇌: GPT-4o/o-series (의사결정)
│  │  │  ├─ dialogue.py        # 입: GPT-4o-mini (발화)
│  │  │  ├─ stt.py / tts.py    # Whisper / OpenAI TTS(or ElevenLabs)
│  │  │  ├─ memory.py          # 3-Tier 추출·저장·검색 + 임베딩
│  │  │  ├─ autobiography.py   # gpt-image-1 + narrative
│  │  │  └─ community.py       # 가상 페르소나 시뮬레이터
│  │  ├─ providers/            # ★ AI 어댑터: openai_*.py | (국내) kt_*.py, upstage_*.py ...
│  │  ├─ models/               # SQLAlchemy + pydantic
│  │  └─ db/                   # pg, neo4j, redis 클라이언트
│  └─ tasks/                   # Celery (자서전 빌드, 심층 추출)
└─ frontend/                   # Vite React SPA
   ├─ index.html
   ├─ src/
   │  ├─ main.tsx
   │  ├─ App.tsx               # 라우팅: /patient, /caregiver
   │  ├─ pages/Patient.tsx     # 좌 Handset + 우 Autobiography
   │  ├─ pages/Caregiver.tsx   # 보호자 포털 (문진, 그래프, 알림)
   │  ├─ components/{Handset, Ebook, GammaTone, MemoryGraph}.tsx
   │  └─ lib/ws.ts             # WebSocket 클라이언트
   └─ vite.config.ts
```

> **`providers/` 가 교체 지점**: `LLMProvider`, `STTProvider`, `TTSProvider`, `ImageProvider`, `EmbeddingProvider` 인터페이스를 두고 데모는 `openai_*` 구현만 등록. 제출 시 국내 구현으로 환경변수 스위치.

---

## 8. AI API 연동 계획

- **공통 인터페이스 우선**: `providers/base.py`에 5개 Provider 추상클래스 정의 → 흐름 코드는 인터페이스에만 의존.
- **데모(지금~)**: OpenAI 키 하나로 5개 전부 충족(Whisper/GPT-4o/GPT-4o-mini/TTS/gpt-image-1/embedding). 가장 빠른 셋업.
  - 한국어 TTS 자연도가 부족하면 `tts.py`만 ElevenLabs로 교체(키 추가).
- **제출본(국내 AI 트랙)**: `providers/`에 KT STT, Solar Pro 3, EXAONE, VARCO 구현을 추가하고 환경변수로 스위치. **흐름·UI 변경 0**.
- 모든 AI 호출은 백엔드 경유(키는 서버 환경변수). 프런트엔드에 키 노출 금지.
- 비용/지연 관리: 두뇌(GPT-4o)는 의사결정 시점만, 입(GPT-4o-mini)은 매 턴. 호출 카운터·지연 로그를 데모 화면(reasoning chain 패널)에 노출해 "분리 설계"를 시각적으로 증명.

---

## 9. 개발 마일스톤 (대회 일정 정렬)

| 단계 | 기간 | 목표 (프로그래밍) |
|---|---|---|
| **M0 스캐폴딩** | 06/01~06/03 | 레포·docker-compose·FastAPI/Vite-React 골격, Provider 인터페이스 + OpenAI 구현, "마이크→Whisper→GPT-4o-mini→TTS→화면" 한 바퀴 |
| **M1 핵심 루프** | 06/04(워크숍)~07월 | 이중 LLM 분리(GPT-4o/4o-mini), Stage 1·2·3 상태머신, 힌트 0~4, 3-Tier 메모리 기본 저장, pgvector 검색 |
| **M2 본선 데모** | ~08/19 본선 | 자서전 그림책 v1(gpt-image-1), 페르소나 완성, 듀얼 디바이스 웹 UI 완성, **시연 영상** 제작 |
| **M3 결선 데모** | 09월~11/03 결선 | 메모리 그래프 시각화(Neo4j), 커뮤니티 시뮬레이션, 보호자 포털, 망각곡선 재질문, 자서전 빌더 완성. **국내 AI provider 교체 검증** |

> 팀원(박은총)의 하드웨어(수화기 3D/PPG)는 별도 트랙. 웹 데모는 그 전에 소프트웨어 가치를 단독 증명한다.

---

## 10. 데모 시나리오 (심사위원이 보는 90초~3분 흐름)

1. 좌측 전화기에서 "통화" 클릭 → AI 페르소나가 따뜻하게 말을 건다 (Stage 1, 40Hz tone 켜짐, 안전 고지 후).
2. "옛날에 자주 가시던 곳이 있나요?" → 환자가 머뭇거리면 **힌트가 0→2단계로 자연스럽게 올라간다** (두뇌가 hint escalation 결정, 입이 부드럽게 표현 — 로그 패널에 실시간 표시).
3. "시장"이라는 키워드 회상 성공 → 우측 패널에 그 장면 **그림 한 장이 그려지고 narrative 한 문장이 추가**된다.
4. 세션 종료 → 자서전 페이지가 저장되고, **"3일 뒤"** 토글을 누르면 재질문 큐에서 "그 시장 이야기 더 들려주실래요?"가 뜬다.
5. (결선) 같은 키워드를 가진 가상 또래와의 그룹 대화로 전환 → 공동체 소속감 회복 메시지.

---

## 11. 리스크 및 대응

| 리스크 | 대응 |
|---|---|
| **데모(외산) ↔ 제출(국내) 트랙 정합성** | Provider 어댑터로 분리, 결선 전(M3) 국내 AI 교체·검증 완료. 심사 제출본은 국내 100% |
| 이중 LLM 응답 지연(침묵 불안) | 두뇌 비동기·세션 사이 호출, 입만 실시간. 지연 측정 후 호출 빈도 튜닝 |
| 40Hz 시청각 자극 안전성 | **광과민성 발작 경고/동의 절차**, 강도 제한, 끄기 버튼 상시 노출 |
| Cold Start(환자·커뮤니티 데이터 없음) | 가상 환자 시나리오 수동 작성 + 페르소나 시뮬레이션으로 부트스트랩 |
| 의료/개인정보 | 데모는 합성 데이터만, 실데이터 미사용. 모든 AI 호출 서버 경유 |
| 임베딩 차원 불일치(외산↔국내 교체 시) | 임베딩 차원/거리계산을 설정값화, 교체 시 재인덱싱 스크립트 준비 |
| 그래프 DB 과설계 | 데모 초기엔 pgvector만으로 회상 단서 → Neo4j는 M3에서 도입 |

---

## 12. 다음 액션 (이번 주)
- [ ] 레포 생성 + `docker-compose up`으로 postgres(pgvector)/neo4j/redis/minio 부팅 확인
- [ ] `providers/base.py` 5개 인터페이스 + `openai_*` 구현 + `.env`(OPENAI_API_KEY)
- [ ] WebSocket으로 "마이크 → Whisper → GPT-4o-mini 응답 → TTS → 화면" 한 바퀴 동작
- [ ] Vite React 좌/우 분할 더미 UI (Handset + Ebook) 렌더
- [ ] 6/4 워크숍에서 국내 API 스펙 확보 → `providers/`에 국내 구현 추가(M3 교체용)
