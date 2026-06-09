"""SQLite persistence for the in-memory :class:`~app.store.Store`.

The fast in-memory Store stays the runtime source of truth; this layer mirrors
its **durable per-patient collections** into a single SQLite file so the
"accumulating database" (memories, survey profile, autobiography, forgetting
curve) survives restarts.

Strategy — deliberately simple for demo scale:
  * **load-on-boot**  : ``load_into(store)`` reads every row back into the dicts.
  * **snapshot-on-turn**: ``snapshot(store)`` rewrites all rows in one
    transaction (a few dozen rows — sub-millisecond), called after each WS turn.

One generic key-value table holds JSON per collection, so adding/removing a
model never needs a migration. NOT persisted (intentionally ephemeral): the
in-progress survey state and the caregiver "today" timeline view.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import sqlite3
import threading
from pathlib import Path

from app.schemas import (
    AutobiographyPage,
    CaregiverIntake,
    Memory,
    Patient,
    RecallItem,
    SurveyResult,
)
from app.store import SessionState, Store

logger = logging.getLogger(__name__)

# collection attr on Store -> Pydantic model (model_dump_json / model_validate_json)
_PYDANTIC: dict[str, type] = {
    "patients": Patient,
    "memories": Memory,
    "pages": AutobiographyPage,
    "recall_queue": RecallItem,
    "intake": CaregiverIntake,
    "survey_results": SurveyResult,
}
_SESSION_FIELDS = {f.name for f in dataclasses.fields(SessionState)}


class SqlitePersistence:
    """A thin SQLite-backed mirror of the Store's durable collections."""

    def __init__(self, db_path: str) -> None:
        self._path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # check_same_thread=False: uvicorn may touch this from the event-loop
        # thread; the lock serializes access.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS store_kv ("
            "  collection TEXT NOT NULL,"
            "  key        TEXT NOT NULL,"
            "  value      TEXT NOT NULL,"
            "  PRIMARY KEY (collection, key)"
            ")"
        )
        self._conn.commit()

    # -- boot --------------------------------------------------------------
    def load_into(self, store: Store) -> int:
        """Reconstruct the Store's collections from disk. Returns rows loaded.

        A single bad/legacy row must never block boot, so each is guarded.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT collection, key, value FROM store_kv"
            ).fetchall()
        n = 0
        for collection, key, value in rows:
            try:
                if collection in _PYDANTIC:
                    model = _PYDANTIC[collection]
                    getattr(store, collection)[key] = model.model_validate_json(value)
                elif collection == "memory_vectors":
                    store.memory_vectors[key] = json.loads(value)
                elif collection == "recall_due_days":
                    store.recall_due_days[key] = int(json.loads(value))
                elif collection == "session_state":
                    data = json.loads(value)
                    data = {k: v for k, v in data.items() if k in _SESSION_FIELDS}
                    store.session_state[key] = SessionState(**data)
                elif collection == "meta" and key == "counter":
                    store._counter = int(json.loads(value))
                else:
                    continue
                n += 1
            except Exception as exc:  # pragma: no cover - resilience guard
                logger.warning("영속 복원 중 손상된 행 건너뜀 (%s/%s): %s", collection, key, exc)
        if n:
            logger.info("SQLite에서 %d개 레코드 복원: %s", n, self._path)
        return n

    # -- per-turn snapshot -------------------------------------------------
    def snapshot(self, store: Store) -> None:
        """Rewrite all durable rows from the Store in one transaction."""
        rows: list[tuple[str, str, str]] = []
        for collection in _PYDANTIC:
            for key, obj in getattr(store, collection).items():
                rows.append((collection, key, obj.model_dump_json()))
        for key, vec in store.memory_vectors.items():
            rows.append(("memory_vectors", key, json.dumps(vec)))
        for key, day in store.recall_due_days.items():
            rows.append(("recall_due_days", key, json.dumps(day)))
        for key, state in store.session_state.items():
            rows.append(("session_state", key, json.dumps(dataclasses.asdict(state))))
        rows.append(("meta", "counter", json.dumps(store._counter)))
        try:
            with self._lock:
                self._conn.execute("DELETE FROM store_kv")
                self._conn.executemany(
                    "INSERT INTO store_kv (collection, key, value) VALUES (?, ?, ?)",
                    rows,
                )
                self._conn.commit()
        except Exception as exc:  # pragma: no cover - never break the chat loop
            logger.warning("영속 스냅샷 실패(무시하고 계속): %s", exc)
