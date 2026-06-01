// SurveyContextPanel — live "수집된 기억 단서" panel for STEP 1 초기 설문.
//
// This is the survey analogue of the therapy ReasoningPanel: it visualizes the
// Tier-1 keyword extraction + recallable/unrecallable classification as the
// AI-persona conversation unfolds. Each `survey_capture` event from the survey
// WS adds either green recallable chips (with the answer's keywords) or an amber
// unrecallable chip (the domain the patient could not recall). A running count
// and a question-progress bar make the live profiling visible.

import { useEffect, useRef } from "react";

// One captured turn as surfaced by the panel. Built from `survey_capture` events
// by the parent Survey page (domain label resolved there).
export interface SurveyCapture {
  domain: string;
  domainLabel: string;
  answer: string;
  keywords: string[];
  recallable: boolean;
}

interface SurveyContextPanelProps {
  captures: SurveyCapture[];
  index: number; // 0-based index of the CURRENT question
  total: number;
}

export function SurveyContextPanel({
  captures,
  index,
  total,
}: SurveyContextPanelProps) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [captures.length]);

  // Aggregate recallable keywords (deduped, frequency-aware ordering) + amber
  // unrecallable topic labels for the summary chip rows.
  const recallableKeywords: string[] = [];
  const seen = new Set<string>();
  const unrecallableTopics: string[] = [];
  let recallableCount = 0;
  let unrecallableCount = 0;

  for (const c of captures) {
    if (c.recallable) {
      recallableCount += 1;
      for (const kw of c.keywords) {
        if (!seen.has(kw)) {
          seen.add(kw);
          recallableKeywords.push(kw);
        }
      }
    } else {
      unrecallableCount += 1;
      if (!unrecallableTopics.includes(c.domainLabel)) {
        unrecallableTopics.push(c.domainLabel);
      }
    }
  }

  const progressPct = total > 0 ? Math.round((index / total) * 100) : 0;

  return (
    <div className="flex h-full flex-col rounded-2xl border border-emerald-200 bg-emerald-50/50">
      <div className="flex items-center justify-between border-b border-emerald-200 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-lg" aria-hidden>
            🧩
          </span>
          <h3 className="text-sm font-bold text-emerald-800">
            수집된 기억 단서
          </h3>
        </div>
        <span className="rounded-full bg-emerald-200 px-2 py-0.5 text-xs font-semibold text-emerald-800">
          Tier-1 추출
        </span>
      </div>

      {/* Progress */}
      <div className="border-b border-emerald-100 px-4 py-3">
        <div className="mb-1 flex items-center justify-between text-[11px] font-semibold text-emerald-700">
          <span>설문 진행</span>
          <span>
            {Math.min(index + 1, total)} / {total}
          </span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-emerald-100">
          <div
            className="h-full rounded-full bg-emerald-500 transition-all duration-500"
            style={{ width: `${progressPct}%` }}
          />
        </div>
      </div>

      {/* Running counts */}
      <div className="grid grid-cols-2 gap-2 px-4 py-3">
        <div className="rounded-xl bg-emerald-100/70 px-3 py-2 text-center">
          <div className="text-lg font-bold text-emerald-700">
            {recallableCount}
          </div>
          <div className="text-[10px] font-semibold text-emerald-600">
            인출 가능
          </div>
        </div>
        <div className="rounded-xl bg-amber-100/70 px-3 py-2 text-center">
          <div className="text-lg font-bold text-amber-700">
            {unrecallableCount}
          </div>
          <div className="text-[10px] font-semibold text-amber-600">
            인출 어려움
          </div>
        </div>
      </div>

      {/* Aggregated chips */}
      <div className="space-y-3 px-4 pb-2">
        <div>
          <div className="mb-1 text-[11px] font-semibold text-emerald-700">
            인출 가능 키워드
          </div>
          {recallableKeywords.length === 0 ? (
            <p className="text-[11px] text-emerald-400">아직 없습니다</p>
          ) : (
            <div className="flex flex-wrap gap-1">
              {recallableKeywords.map((kw, i) => (
                <span
                  key={i}
                  className="rounded-full bg-emerald-200/80 px-2 py-0.5 text-[11px] font-medium text-emerald-800"
                >
                  {kw}
                </span>
              ))}
            </div>
          )}
        </div>

        <div>
          <div className="mb-1 text-[11px] font-semibold text-amber-700">
            인출 어려운 주제
          </div>
          {unrecallableTopics.length === 0 ? (
            <p className="text-[11px] text-amber-400">아직 없습니다</p>
          ) : (
            <div className="flex flex-wrap gap-1">
              {unrecallableTopics.map((t, i) => (
                <span
                  key={i}
                  className="rounded-full bg-amber-200/80 px-2 py-0.5 text-[11px] font-medium text-amber-800"
                >
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Per-turn capture log */}
      <div className="flex-1 space-y-2 overflow-y-auto border-t border-emerald-100 px-3 py-3">
        {captures.length === 0 && (
          <p className="px-1 py-4 text-center text-xs text-emerald-400">
            대답을 하시면 떠올린 기억의 단서가 여기에 차곡차곡 모입니다.
          </p>
        )}
        {captures.map((c, i) => (
          <div
            key={i}
            className={`rounded-xl border p-2.5 text-xs shadow-sm ${
              c.recallable
                ? "border-emerald-200 bg-white"
                : "border-amber-200 bg-amber-50/60"
            }`}
          >
            <div className="mb-1 flex items-center justify-between">
              <span className="font-semibold text-stone-600">
                {c.domainLabel}
              </span>
              <span
                className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                  c.recallable
                    ? "bg-emerald-100 text-emerald-700"
                    : "bg-amber-100 text-amber-700"
                }`}
              >
                {c.recallable ? "인출 ✓" : "흐릿"}
              </span>
            </div>
            <p className="mb-1.5 line-clamp-2 text-[11px] leading-snug text-stone-500">
              {c.answer || "(대답 없음)"}
            </p>
            {c.keywords.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {c.keywords.map((kw, k) => (
                  <span
                    key={k}
                    className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                      c.recallable
                        ? "bg-emerald-100 text-emerald-700"
                        : "bg-amber-100 text-amber-700"
                    }`}
                  >
                    {kw}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}

export default SurveyContextPanel;
