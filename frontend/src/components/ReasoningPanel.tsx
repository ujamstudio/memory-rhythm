// ReasoningPanel — live log of `reasoning` WS messages.
//
// This is the visual proof of the 이중 LLM 분리 (dual-LLM split): the 두뇌
// (reasoner, GPT-4o) decides stage/hint/recall, and the 입 (dialogue,
// GPT-4o-mini) speaks. Each entry shows the reasoning model, measured latency,
// and the structured decision so judges can see the "brain" working.

import { useEffect, useRef } from "react";
import type { ReasoningMsg } from "../protocol";
import { stageLabel } from "../protocol";

interface ReasoningPanelProps {
  log: ReasoningMsg[];
}

const HINT_LABELS: Record<number, string> = {
  0: "질문만",
  1: "카테고리 단서",
  2: "주변 기억",
  3: "시각 단서",
  4: "직접 단서",
};

export function ReasoningPanel({ log }: ReasoningPanelProps) {
  const endRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll to newest entry.
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [log.length]);

  return (
    <div className="flex h-full flex-col rounded-2xl border border-indigo-200 bg-indigo-50/60">
      <div className="flex items-center justify-between border-b border-indigo-200 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-lg" aria-hidden>
            🧠
          </span>
          <h3 className="text-sm font-bold text-indigo-800">
            추론 체인 (두뇌)
          </h3>
        </div>
        <span className="rounded-full bg-indigo-200 px-2 py-0.5 text-xs font-semibold text-indigo-800">
          이중 LLM 분리
        </span>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-3 py-3">
        {log.length === 0 && (
          <p className="px-1 py-4 text-center text-xs text-indigo-400">
            통화를 시작하면 두뇌(GPT-4o)의 추론 과정이 여기에 표시됩니다.
          </p>
        )}

        {log.map((entry, i) => {
          const d = entry.decision;
          return (
            <div
              key={i}
              className="rounded-xl border border-indigo-200 bg-white p-3 text-xs shadow-sm"
            >
              <div className="mb-2 flex items-center justify-between">
                <span className="font-mono text-[11px] font-semibold text-indigo-700">
                  {entry.model}
                </span>
                <span className="rounded bg-emerald-100 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-emerald-700">
                  {entry.latency_ms} ms
                </span>
              </div>

              <div className="grid grid-cols-2 gap-1.5">
                <Badge
                  label="단계"
                  value={`${d.stage} ${stageLabel(d.stage)}`}
                />
                <Badge
                  label="다음 단계"
                  value={`${d.next_stage} ${stageLabel(d.next_stage)}`}
                  highlight={d.next_stage !== d.stage}
                />
                <Badge
                  label="힌트 레벨"
                  value={`${d.hint_level} · ${HINT_LABELS[d.hint_level] ?? "-"}`}
                />
                <Badge
                  label="인출 감지"
                  value={d.recall_detected ? "성공 ✓" : "대기중"}
                  highlight={d.recall_detected}
                />
              </div>

              {d.keywords?.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {d.keywords.map((kw, k) => (
                    <span
                      key={k}
                      className="rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-medium text-indigo-700"
                    >
                      #{kw}
                    </span>
                  ))}
                </div>
              )}

              <p className="mt-2 border-t border-indigo-100 pt-2 text-[11px] leading-snug text-stone-600">
                <span className="font-semibold text-indigo-700">판단 근거: </span>
                {d.reason}
              </p>
            </div>
          );
        })}
        <div ref={endRef} />
      </div>
    </div>
  );
}

function Badge({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`rounded-lg px-2 py-1 ${
        highlight
          ? "bg-emerald-50 ring-1 ring-emerald-300"
          : "bg-stone-50 ring-1 ring-stone-200"
      }`}
    >
      <div className="text-[9px] uppercase tracking-wide text-stone-400">
        {label}
      </div>
      <div className="text-[11px] font-semibold text-stone-700">{value}</div>
    </div>
  );
}

export default ReasoningPanel;
