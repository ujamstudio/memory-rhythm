// IntakeForm — 보호자 문진 폼.
// Collects structured life-history facts about the patient and POSTs them to
// /api/caregiver/intake. The `structured` payload is a free-form JSON object;
// here we shape it from a small set of demo-friendly fields plus the
// dementia_type select. All user-facing copy is Korean.

import { useState, type FormEvent } from "react";
import type { DementiaType } from "../protocol";
import { api } from "../lib/api";

interface IntakeFormProps {
  patientId: string;
  // Notify parent (Caregiver page) so it can refetch the memory graph after
  // intake — seeded life facts often become memory candidates.
  onSubmitted?: () => void;
}

interface IntakeFields {
  dementia_type: DementiaType;
  full_name: string;
  birth_year: string;
  hometown: string; // 고향
  job: string; // 직업
  family: string; // 가족 관계
  hobbies: string; // 취미 / 좋아하던 일
  key_episodes: string; // 인상 깊은 사건 (줄바꿈 구분)
}

const EMPTY: IntakeFields = {
  dementia_type: "alzheimer",
  full_name: "",
  birth_year: "",
  hometown: "",
  job: "",
  family: "",
  hobbies: "",
  key_episodes: "",
};

const DEMENTIA_OPTIONS: { value: DementiaType; label: string }[] = [
  { value: "alzheimer", label: "알츠하이머형" },
  { value: "vascular", label: "혈관성" },
  { value: "lewy", label: "루이소체" },
];

// Prefilled demo content so the scripted scenario (시장/장보기 회상) has seeded
// life facts to work with.
const DEMO_PRESET: IntakeFields = {
  dementia_type: "alzheimer",
  full_name: "김순자",
  birth_year: "1945",
  hometown: "전라남도 순천",
  job: "포목점 운영 (시장 상인)",
  family: "남편 박정호, 딸 둘, 아들 하나, 손주 넷",
  hobbies: "장 보기, 동치미 담그기, 트로트 듣기",
  key_episodes:
    "매주 토요일 순천 웃장에서 장을 봤다\n딸 결혼식 날 한복을 직접 골랐다\n손주에게 줄 사탕을 늘 주머니에 넣고 다녔다",
};

export default function IntakeForm({ patientId, onSubmitted }: IntakeFormProps) {
  const [fields, setFields] = useState<IntakeFields>(EMPTY);
  const [status, setStatus] = useState<"idle" | "saving" | "done" | "error">(
    "idle",
  );
  const [errorMsg, setErrorMsg] = useState<string>("");

  function update<K extends keyof IntakeFields>(key: K, value: IntakeFields[K]) {
    setFields((f) => ({ ...f, [key]: value }));
    setStatus("idle");
  }

  function loadPreset() {
    setFields(DEMO_PRESET);
    setStatus("idle");
  }

  // Shape the structured payload sent to the backend. key_episodes is split
  // into a list so the memory extractor / graph can treat each as a node.
  function buildStructured(): Record<string, unknown> {
    return {
      dementia_type: fields.dementia_type,
      full_name: fields.full_name.trim(),
      birth_year: fields.birth_year.trim(),
      hometown: fields.hometown.trim(),
      job: fields.job.trim(),
      family: fields.family.trim(),
      hobbies: fields.hobbies
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      key_episodes: fields.key_episodes
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
    };
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!patientId) {
      setStatus("error");
      setErrorMsg("환자 ID가 없습니다. 먼저 환자를 선택해 주세요.");
      return;
    }
    setStatus("saving");
    setErrorMsg("");
    try {
      await api.caregiverIntake({
        patient_id: patientId,
        structured: buildStructured(),
      });
      setStatus("done");
      onSubmitted?.();
    } catch (err) {
      setStatus("error");
      setErrorMsg(err instanceof Error ? err.message : "문진 저장에 실패했습니다.");
    }
  }

  const inputCls =
    "w-full rounded-xl border border-amber-200 bg-white px-4 py-3 text-base " +
    "text-stone-800 placeholder:text-stone-400 focus:border-amber-400 " +
    "focus:outline-none focus:ring-2 focus:ring-amber-200";
  const labelCls = "mb-1 block text-sm font-semibold text-stone-600";

  return (
    <section className="rounded-3xl border border-amber-100 bg-white/80 p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-stone-800">보호자 문진</h2>
          <p className="text-sm text-stone-500">
            환자의 삶의 기록을 입력하면 회상 단서로 활용됩니다.
          </p>
        </div>
        <button
          type="button"
          onClick={loadPreset}
          className="rounded-full bg-amber-100 px-4 py-2 text-sm font-semibold text-amber-700 transition hover:bg-amber-200"
        >
          데모 예시 채우기
        </button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className={labelCls} htmlFor="dementia_type">
              치매 유형
            </label>
            <select
              id="dementia_type"
              className={inputCls}
              value={fields.dementia_type}
              onChange={(e) =>
                update("dementia_type", e.target.value as DementiaType)
              }
            >
              {DEMENTIA_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelCls} htmlFor="full_name">
              성함
            </label>
            <input
              id="full_name"
              className={inputCls}
              placeholder="예: 김순자"
              value={fields.full_name}
              onChange={(e) => update("full_name", e.target.value)}
            />
          </div>
          <div>
            <label className={labelCls} htmlFor="birth_year">
              출생 연도
            </label>
            <input
              id="birth_year"
              className={inputCls}
              placeholder="예: 1945"
              inputMode="numeric"
              value={fields.birth_year}
              onChange={(e) => update("birth_year", e.target.value)}
            />
          </div>
          <div>
            <label className={labelCls} htmlFor="hometown">
              고향
            </label>
            <input
              id="hometown"
              className={inputCls}
              placeholder="예: 전라남도 순천"
              value={fields.hometown}
              onChange={(e) => update("hometown", e.target.value)}
            />
          </div>
          <div>
            <label className={labelCls} htmlFor="job">
              직업 / 하던 일
            </label>
            <input
              id="job"
              className={inputCls}
              placeholder="예: 시장에서 포목점 운영"
              value={fields.job}
              onChange={(e) => update("job", e.target.value)}
            />
          </div>
          <div>
            <label className={labelCls} htmlFor="family">
              가족 관계
            </label>
            <input
              id="family"
              className={inputCls}
              placeholder="예: 남편, 딸 둘, 손주 넷"
              value={fields.family}
              onChange={(e) => update("family", e.target.value)}
            />
          </div>
        </div>

        <div>
          <label className={labelCls} htmlFor="hobbies">
            취미 / 좋아하던 일 (쉼표로 구분)
          </label>
          <input
            id="hobbies"
            className={inputCls}
            placeholder="예: 장 보기, 동치미 담그기, 트로트"
            value={fields.hobbies}
            onChange={(e) => update("hobbies", e.target.value)}
          />
        </div>

        <div>
          <label className={labelCls} htmlFor="key_episodes">
            인상 깊은 사건 (한 줄에 하나씩)
          </label>
          <textarea
            id="key_episodes"
            className={`${inputCls} min-h-[110px] resize-y`}
            placeholder={"예:\n매주 토요일 순천 웃장에서 장을 봤다\n딸 결혼식 날 한복을 직접 골랐다"}
            value={fields.key_episodes}
            onChange={(e) => update("key_episodes", e.target.value)}
          />
        </div>

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={status === "saving"}
            className="rounded-full bg-amber-500 px-6 py-3 text-base font-bold text-white shadow transition hover:bg-amber-600 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {status === "saving" ? "저장 중..." : "문진 저장"}
          </button>
          {status === "done" && (
            <span className="text-sm font-semibold text-emerald-600">
                문진이 저장되었습니다.
            </span>
          )}
          {status === "error" && (
            <span className="text-sm font-semibold text-rose-600">{errorMsg}</span>
          )}
        </div>
      </form>
    </section>
  );
}
