// SurveyProfileCard — final persona_profile summary card for STEP 1 초기 설문.
//
// Rendered once the survey WS emits `survey_complete`. Shows the warm narrative
// summary the backend built from the conversation, the ranked recallable
// keywords (green), the unrecallable topics (amber), the count of episodic
// memories seeded into the patient's store, and a primary CTA that carries the
// surveyed patient_id into the therapy flow via /patient?patient={id}.

import { useNavigate } from "react-router-dom";
import type { SurveyResult } from "../protocol";

const DEMENTIA_LABELS: Record<string, string> = {
  alzheimer: "알츠하이머",
  vascular: "혈관성",
  lewy: "루이체",
};

interface SurveyProfileCardProps {
  result: SurveyResult;
}

export function SurveyProfileCard({ result }: SurveyProfileCardProps) {
  const navigate = useNavigate();

  const startCall = () => {
    navigate(`/patient?patient=${encodeURIComponent(result.patient_id)}`);
  };

  return (
    <div className="mx-auto max-w-2xl rounded-3xl border border-amber-200 bg-white p-7 shadow-sm">
      <div className="mb-5 flex items-center gap-3">
        <span className="grid h-12 w-12 place-items-center rounded-2xl bg-amber-warm text-2xl text-white shadow-soft">
          ✿
        </span>
        <div>
          <h2 className="text-2xl font-bold text-stone-800">
            {result.name} 어르신의 기억 프로필
          </h2>
          <p className="text-sm text-stone-500">
            {DEMENTIA_LABELS[result.dementia_type] ?? result.dementia_type} ·
            초기 설문 완료
          </p>
        </div>
      </div>

      {/* Narrative summary */}
      <div className="mb-5 rounded-2xl bg-amber-50/70 p-5">
        <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-amber-600">
          요약
        </div>
        <p className="text-lg leading-relaxed text-stone-700">
          {result.summary}
        </p>
      </div>

      {/* Recallable keywords */}
      <div className="mb-4">
        <div className="mb-2 text-sm font-semibold text-emerald-700">
          또렷이 기억하시는 단서 ({result.recallable_keywords.length})
        </div>
        {result.recallable_keywords.length === 0 ? (
          <p className="text-sm text-stone-400">수집된 단서가 없습니다.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {result.recallable_keywords.map((kw, i) => (
              <span
                key={i}
                className="rounded-full bg-emerald-100 px-3 py-1 text-sm font-medium text-emerald-800"
              >
                {kw}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Unrecallable topics */}
      <div className="mb-5">
        <div className="mb-2 text-sm font-semibold text-amber-700">
          아직 흐릿한 주제 ({result.unrecallable_topics.length})
        </div>
        {result.unrecallable_topics.length === 0 ? (
          <p className="text-sm text-stone-400">없습니다.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {result.unrecallable_topics.map((t, i) => (
              <span
                key={i}
                className="rounded-full bg-amber-100 px-3 py-1 text-sm font-medium text-amber-800"
              >
                {t}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Seeded memory count */}
      <div className="mb-6 flex items-center gap-3 rounded-2xl bg-stone-50 px-5 py-4">
        <span className="text-3xl font-bold text-emerald-600">
          {result.seeded_memory_count}
        </span>
        <span className="text-sm text-stone-600">
          개의 기억이 통화에 사용될 수 있도록 저장되었습니다.
        </span>
      </div>

      {/* CTA into the therapy flow with the surveyed patient id */}
      <button
        type="button"
        onClick={startCall}
        className="w-full rounded-full bg-amber-warm px-6 py-4 text-lg font-bold text-white shadow-soft transition hover:brightness-105"
      >
        이 어르신과 통화 시작하기 →
      </button>
    </div>
  );
}

export default SurveyProfileCard;
