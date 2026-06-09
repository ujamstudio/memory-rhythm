"""Seed virtual demo patients so the app can be demoed with rich, already
accumulated data (no need to walk the survey first).

Creates three realistic Korean elderly personas — each with a survey profile,
recalled & to-be-recalled memories (with offline mock embeddings), autobiography
pages, and a forgetting-curve queue — and persists them to the SQLite store.

Run it (server stopped, so it reloads the seed on next boot):

    python backend/seed_demo.py
    # then (re)start: uvicorn app.main:app --port 8000 ...

Idempotent: re-running purges each demo patient's prior data and rebuilds it.
Offline: uses mock embeddings/images, so it never calls a paid API.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Allow `python backend/seed_demo.py` from the repo root or from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.db.persistence import SqlitePersistence
from app.providers.mock_provider import MockEmbedding, MockImage
from app.schemas import SurveyResult
from app.store import RECALL_INTERVALS, SessionState, get_store, now_iso

# --- the three demo patients ------------------------------------------------
# Each: stable id, profile, survey keywords, and memories. recalled=True memories
# already feed persona/anchors; recalled=False ones are left for the session to
# elicit live (so a demo can show a fresh recall succeeding).
DEMO_PATIENTS = [
    {
        "id": "demo-soonrye",
        "name": "박순례",
        "dementia_type": "alzheimer",
        "profile": (
            "1938년 전라도 시골에서 태어나 평생 삯바느질로 딸 셋을 키우셨어요. "
            "라디오 연속극을 즐겨 들으셨고, 봄이면 논밭에서 나물을 캐 무쳐 드셨습니다."
        ),
        "recallable": ["나물", "딸", "라디오", "전라도", "논밭", "삯바느질"],
        "unrecallable": ["오늘 아침 식사", "어제 만난 사람"],
        "memories": [
            ("봄이면 논밭에서 산나물을 캐서 조물조물 무쳐 먹었어요.", ["나물", "논밭"], True),
            ("삯바느질로 밤새 일해서 딸 셋을 다 키웠지요.", ["딸", "삯바느질"], True),
            ("저녁마다 라디오에서 연속극 나오는 걸 빼놓지 않고 들었어요.", ["라디오"], True),
            ("전라도 고향집 마당 정자나무 아래에서 뛰놀았어요.", ["전라도"], False),
        ],
        "pages": [
            ("산나물 캐던 봄날", "순례 어르신은 봄이면 논밭에 나가 산나물을 한 바구니 캐 오셨어요. 조물조물 무쳐 둘러앉아 먹던 그 봄날의 향기."),
            ("딸 셋을 키운 바늘땀", "호롱불 아래 삯바느질로 새운 밤들. 그 바늘땀 하나하나가 딸 셋을 어엿하게 키워낸 어머니의 사랑이었습니다."),
        ],
    },
    {
        "id": "demo-cheolsu",
        "name": "김철수",
        "dementia_type": "vascular",
        "profile": (
            "1940년 부산에서 나고 자라 평생 바다에 나가 고기를 잡으신 뱃사람이세요. "
            "자갈치 시장에 고등어를 내다 팔고, 아들 둘을 두셨습니다."
        ),
        "recallable": ["바다", "고등어", "부산", "배", "그물", "아들"],
        "unrecallable": ["오늘 날짜", "점심 메뉴"],
        "memories": [
            ("새벽 어스름에 배를 띄워 그물 가득 고등어를 잡아 올렸어요.", ["바다", "고등어", "배"], True),
            ("자갈치 시장에 갓 잡은 고기를 내다 팔러 다녔지요.", ["부산", "고등어"], True),
            ("아들 둘에게 그물 손질하는 법을 가르쳤어요.", ["아들", "그물"], True),
            ("태풍 오던 날 바다가 무섭게 울던 게 생각나요.", ["바다"], False),
        ],
        "pages": [
            ("새벽 바다의 고등어", "철수 어르신의 배가 새벽 바다를 가르면 그물 가득 은빛 고등어가 퍼덕였습니다. 평생을 바다에 바친 뱃사람의 자부심."),
        ],
    },
    {
        "id": "demo-youngja",
        "name": "이영자",
        "dementia_type": "lewy",
        "profile": (
            "1935년 서울에서 태어나 국민학교 선생님으로 평생 아이들을 가르치셨어요. "
            "풍금을 치며 노래를 가르치셨고, 분필 가루 묻은 손이 익숙하셨습니다."
        ),
        "recallable": ["학교", "아이들", "풍금", "분필", "칠판", "노래"],
        "unrecallable": ["오늘 요일", "조금 전에 한 일"],
        "memories": [
            ("국민학교 교실에서 아이들에게 한글을 또박또박 가르쳤어요.", ["학교", "아이들"], True),
            ("풍금을 치며 아이들과 함께 노래를 불렀지요.", ["풍금", "노래"], True),
            ("분필을 들고 칠판에 글씨를 쓰던 그 느낌이 좋았어요.", ["분필", "칠판"], True),
        ],
        "pages": [
            ("풍금 소리 울리던 교실", "영자 선생님이 풍금을 누르면 교실 가득 아이들의 노랫소리가 번졌습니다. 분필 가루 속에서 피어난 평생의 보람."),
        ],
    },
]


def _purge(store, patient_id: str) -> None:
    """Remove all of a demo patient's prior data so seeding stays idempotent."""
    store.patients.pop(patient_id, None)
    store.survey_results.pop(patient_id, None)
    store.intake.pop(patient_id, None)
    mem_ids = [mid for mid, m in store.memories.items() if m.patient_id == patient_id]
    for mid in mem_ids:
        store.memories.pop(mid, None)
        store.memory_vectors.pop(mid, None)
    page_ids = [pid for pid, p in store.pages.items() if p.patient_id == patient_id]
    for pid in page_ids:
        store.pages.pop(pid, None)
    # Recall items whose backing memory belonged to this patient.
    item_ids = [iid for iid, it in store.recall_queue.items() if it.memory_id in mem_ids]
    for iid in item_ids:
        store.recall_queue.pop(iid, None)
        store.recall_due_days.pop(iid, None)
    # Any session bound to this patient.
    sess_ids = [sid for sid, s in store.session_state.items() if s.patient_id == patient_id]
    for sid in sess_ids:
        store.session_state.pop(sid, None)


async def seed() -> None:
    store = get_store()
    default_db = Path(__file__).resolve().parent / "data" / "memory_rhythm.db"
    db_path = os.environ.get("DB_PATH") or str(default_db)
    store.attach_persistence(SqlitePersistence(db_path))  # loads any existing data

    embedder = MockEmbedding()
    imager = MockImage()

    for spec in DEMO_PATIENTS:
        pid = spec["id"]
        _purge(store, pid)

        store.create_patient(
            name=spec["name"],
            dementia_type=spec["dementia_type"],
            persona_profile=spec["profile"],
            patient_id=pid,
        )
        store.save_survey_result(
            pid,
            SurveyResult(
                patient_id=pid,
                name=spec["name"],
                dementia_type=spec["dementia_type"],  # type: ignore[arg-type]
                profile={
                    "name": spec["name"],
                    "recallable_keywords": spec["recallable"],
                    "unrecallable_topics": spec["unrecallable"],
                    "summary": spec["profile"],
                },
                recallable_keywords=spec["recallable"],
                unrecallable_topics=spec["unrecallable"],
                summary=spec["profile"],
                seeded_memory_count=len(spec["memories"]),
                completed_at=now_iso(),
            ),
        )

        # Memories (+ offline mock embeddings).
        recalled_mem_ids: list[str] = []
        for text, keywords, recalled in spec["memories"]:
            vec = (await embedder.embed([text]))[0]
            mem = store.add_memory(
                patient_id=pid,
                text=text,
                keywords=keywords,
                recall_status="recalled" if recalled else "unrecalled",
                embedding=vec,
            )
            if recalled:
                recalled_mem_ids.append(mem.id)

        # Autobiography pages (offline mock image).
        for caption, narrative in spec["pages"]:
            image_url = await imager.generate(caption)
            store.add_page(
                patient_id=pid,
                session_id=f"seed-{pid}",
                image_url=image_url,
                narrative=narrative,
            )

        # Forgetting-curve queue for recalled memories (some due now/soon).
        for mid in recalled_mem_ids[:2]:
            mem = store.get_memory(mid)
            kw = mem.keywords[0] if mem and mem.keywords else "그때"
            store.add_recall_items(
                memory_id=mid,
                text=f"지난번 '{kw}' 이야기 참 좋았어요. 그 이야기 더 들려주실래요?",
                from_day=0,
                intervals=RECALL_INTERVALS,
            )

        # A short prior conversation so reconnecting feels continuous.
        sid = f"seed-{pid}"
        state = SessionState(session_id=sid, patient_id=pid)
        state.recall_anchors = list(spec["recallable"])
        first = spec["memories"][0][0]
        state.transcript = [
            {"role": "assistant", "text": f"{spec['name']} 어르신, 또 이렇게 뵈니 반가워요!"},
            {"role": "user", "text": first},
            {"role": "assistant", "text": "아이고, 그러셨구나~ 그 이야기 더 듣고 싶어요."},
        ]
        store.set_session_state(sid, state)

    store.persist()

    print(f"Seeded {len(DEMO_PATIENTS)} demo patients -> {db_path}\n")
    for spec in DEMO_PATIENTS:
        print(f"  • {spec['name']:6s} ({spec['dementia_type']:9s})  "
              f"/patient?patient={spec['id']}")
    print("\n다음: 백엔드를 (재)시작하면 시드가 로드됩니다.")


if __name__ == "__main__":
    asyncio.run(seed())
