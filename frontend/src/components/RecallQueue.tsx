// RecallQueue — forgetting-curve re-question queue (1/3/7/21-day intervals).
// Fetches the patient's recall queue and renders each item with its due date
// and interval stage. "시간 가속" buttons (+1/+3/+7/+21d) simulate the passage
// of time so the demo can show due re-questions immediately.
//
// Time-acceleration wiring:
//   - If a parent supplies `onAdvanceTime`, it is invoked (the Caregiver page
//     forwards it to the shared WS `advance_time` helper). The server then
//     emits recall_prompt(s) over the patient session and the queue is refetched.
//   - If no WS session is available, the buttons are still shown but clearly
//     labeled as demo time-acceleration and only trigger a local refetch.

import { useEffect, useState } from "react";
import type { IntervalStage, RecallItem } from "../protocol";
import { api } from "../lib/api";

interface RecallQueueProps {
  patientId: string;
  // Optional: forward to a shared WS session's advance_time helper.
  // When absent, buttons act as a local demo refetch only.
  onAdvanceTime?: (days: number) => void;
  // Whether a live patient WS session is currently connected.
  wsConnected?: boolean;
  // Bump to force a refetch from the parent (e.g. after recall over WS).
  refreshKey?: number;
}

const ADVANCE_OPTIONS: { days: number; label: string }[] = [
  { days: 1, label: "+1일" },
  { days: 3, label: "+3일" },
  { days: 7, label: "+7일" },
  { days: 21, label: "+21일" },
];

const INTERVAL_COLOR: Record<IntervalStage, string> = {
  1: "bg-rose-100 text-rose-700",
  3: "bg-amber-100 text-amber-700",
  7: "bg-sky-100 text-sky-700",
  21: "bg-violet-100 text-violet-700",
};

function formatDue(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ko-KR", {
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function isDue(iso: string): boolean {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return false;
  return d.getTime() <= Date.now();
}

export default function RecallQueue({
  patientId,
  onAdvanceTime,
  wsConnected = false,
  refreshKey = 0,
}: RecallQueueProps) {
  const [items, setItems] = useState<RecallItem[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState("");
  // Local nudge so the +Nd buttons refetch even without a WS session.
  const [localRefresh, setLocalRefresh] = useState(0);

  useEffect(() => {
    let alive = true;
    setStatus("loading");
    api
      .getRecallQueue(patientId)
      .then((rows) => {
        if (!alive) return;
        setItems(rows);
        setStatus("ready");
      })
      .catch((err) => {
        if (!alive) return;
        setErrorMsg(err instanceof Error ? err.message : "재질문 큐를 불러오지 못했습니다.");
        setStatus("error");
      });
    return () => {
      alive = false;
    };
  }, [patientId, refreshKey, localRefresh]);

  function handleAdvance(days: number) {
    // Forward to the WS session if wired; the server will emit recall_prompts
    // and the parent should bump refreshKey. Always also nudge a local refetch
    // so the queue view updates even in pure-REST demo mode.
    onAdvanceTime?.(days);
    setLocalRefresh((n) => n + 1);
  }

  const dueCount = items.filter((it) => isDue(it.due_at)).length;

  return (
    <section className="rounded-3xl border border-amber-100 bg-white/80 p-6 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-stone-800">재질문 큐</h2>
          <p className="text-sm text-stone-500">
            망각 곡선(1·3·7·21일) 기반 회상 재질문 일정
          </p>
        </div>
        {status === "ready" && (
          <span className="rounded-full bg-amber-50 px-3 py-1 text-sm font-semibold text-amber-700">
            오늘 도래 {dueCount} / 전체 {items.length}
          </span>
        )}
      </div>

      {/* time-acceleration controls */}
      <div className="mb-4 rounded-2xl bg-stone-50 p-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-semibold text-stone-600">시간 가속</span>
          <span className="text-xs text-stone-400">
            {wsConnected
              ? "환자 세션에 연결됨 — 도래 재질문이 즉시 전송됩니다."
              : "데모 모드 — 시간 가속 시뮬레이션 (큐만 갱신)"}
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
          {ADVANCE_OPTIONS.map((opt) => (
            <button
              key={opt.days}
              type="button"
              onClick={() => handleAdvance(opt.days)}
              className="rounded-full bg-amber-500 px-5 py-2 text-base font-bold text-white shadow transition hover:bg-amber-600 active:scale-95"
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {status === "loading" && (
        <div className="flex h-32 items-center justify-center text-stone-400">
          재질문 큐를 불러오는 중...
        </div>
      )}

      {status === "error" && (
        <div className="flex h-32 items-center justify-center text-rose-500">
          {errorMsg}
        </div>
      )}

      {status === "ready" && items.length === 0 && (
        <div className="flex h-32 flex-col items-center justify-center gap-2 text-stone-400">
          <p>예약된 재질문이 없습니다.</p>
          <p className="text-sm">회상에 성공하면 1·3·7·21일 후 재질문이 등록됩니다.</p>
        </div>
      )}

      {status === "ready" && items.length > 0 && (
        <ul className="space-y-3">
          {items.map((it) => {
            const due = isDue(it.due_at);
            return (
              <li
                key={it.id}
                className={`flex items-center gap-3 rounded-2xl border px-4 py-3 ${
                  due ? "border-rose-200 bg-rose-50/60" : "border-amber-100 bg-amber-50/40"
                }`}
              >
                <span
                  className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-bold ${
                    INTERVAL_COLOR[it.interval_stage]
                  }`}
                >
                  {it.interval_stage}일차
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-base text-stone-800">{it.text}</p>
                  <p className="text-xs text-stone-500">
                    재질문 예정: {formatDue(it.due_at)}
                  </p>
                </div>
                {due && (
                  <span className="shrink-0 rounded-full bg-rose-500 px-3 py-1 text-xs font-bold text-white">
                    도래
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
