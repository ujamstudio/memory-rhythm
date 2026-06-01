// Survey.tsx — STEP 1 초기 설문 (대화형).
//
// A patient-facing AI-persona conversational onboarding that SETS THE USER'S
// CONTEXT for the therapy flow. It lives at the dedicated /survey route, runs
// fully offline in mock mode, and seeds the patient's store so the subsequent
// therapy call uses real context.
//
// Flow:
//   1) Setup    — name input + dementia_type select + "설문 시작".
//   2) Converse — opens its OWN survey WS (SurveySocket -> /ws/survey/{id}),
//                 sends start_survey, then renders persona question bubbles
//                 (with a warm `preface`), a text answer input + send, and a
//                 "잘 모르겠어요 / 건너뛰기" skip button. A live
//                 SurveyContextPanel visualizes Tier-1 extraction.
//   3) Complete — on `survey_complete`, render SurveyProfileCard.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  DementiaType,
  SurveyResult,
  SurveyServerMessage,
} from "../protocol";
import { SurveySocket } from "../lib/ws";
import {
  SurveyContextPanel,
  type SurveyCapture,
} from "../components/SurveyContextPanel";
import { SurveyProfileCard } from "../components/SurveyProfileCard";

// Human-readable Korean labels for the survey domains. Mirrors the backend
// domain->label map so the live panel can show friendly topic names. Unknown
// domains fall back to the raw key.
const DOMAIN_LABELS: Record<string, string> = {
  name_era: "이름·시대",
  childhood_place: "어린 시절 고향",
  family: "가족",
  work: "일·직업",
  daily_routine: "하루 일과",
  food: "음식",
  music_media: "음악·라디오·영화",
  season_nature: "계절·자연",
  relationships: "사람·관계",
  hardship: "힘들었던 시절",
  cherished_memory: "소중한 기억",
  hope_message: "바라는 마음",
  recent_meal: "오늘 아침 식사",
  recent_visitor: "어제 만난 사람",
};

function domainLabel(domain: string): string {
  return DOMAIN_LABELS[domain] ?? domain;
}

const DEMENTIA_OPTIONS: { value: DementiaType; label: string; hint: string }[] =
  [
    {
      value: "alzheimer",
      label: "알츠하이머",
      hint: "오래된 기억은 또렷, 최근 기억은 흐릿한 편",
    },
    {
      value: "vascular",
      label: "혈관성",
      hint: "차분하고 구체적인 질문으로 진행",
    },
    {
      value: "lewy",
      label: "루이체",
      hint: "장면을 떠올리는 질문 · 또렷한 날/흐린 날 모두 괜찮아요",
    },
  ];

type Step = "setup" | "converse" | "complete";

interface QuestionBubble {
  preface: string;
  text: string;
  domain: string;
  index: number;
  total: number;
}

type Turn =
  | { role: "persona"; preface: string; text: string }
  | { role: "patient"; text: string };

function genSessionId(): string {
  return `survey-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export default function Survey() {
  const [step, setStep] = useState<Step>("setup");

  // setup
  const [name, setName] = useState("");
  const [dementiaType, setDementiaType] = useState<DementiaType>("alzheimer");

  // conversation
  const [turns, setTurns] = useState<Turn[]>([]);
  const [current, setCurrent] = useState<QuestionBubble | null>(null);
  const [answer, setAnswer] = useState("");
  const [waiting, setWaiting] = useState(false); // awaiting next server message
  const [captures, setCaptures] = useState<SurveyCapture[]>([]);
  const [connError, setConnError] = useState("");

  // completion
  const [result, setResult] = useState<SurveyResult | null>(null);

  const sockRef = useRef<SurveySocket | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  // ---- WS message handling ----------------------------------------------

  const handleMessage = useCallback((msg: SurveyServerMessage) => {
    switch (msg.type) {
      case "survey_capture":
        setCaptures((cs) => [
          ...cs,
          {
            domain: msg.domain,
            domainLabel: domainLabel(msg.domain),
            answer: msg.answer,
            keywords: msg.keywords,
            recallable: msg.recallable,
          },
        ]);
        break;
      case "survey_question":
        setCurrent({
          preface: msg.preface,
          text: msg.text,
          domain: msg.domain,
          index: msg.index,
          total: msg.total,
        });
        setTurns((t) => [
          ...t,
          { role: "persona", preface: msg.preface, text: msg.text },
        ]);
        setWaiting(false);
        break;
      case "survey_complete":
        setResult(msg.result);
        setStep("complete");
        setWaiting(false);
        break;
      case "error":
        setConnError(msg.message);
        setWaiting(false);
        break;
    }
  }, []);

  // Tear down the socket on unmount.
  useEffect(() => {
    return () => {
      sockRef.current?.close();
      sockRef.current = null;
    };
  }, []);

  // Auto-scroll the conversation.
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns.length, waiting]);

  // ---- Actions ----------------------------------------------------------

  const startSurvey = useCallback(() => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setConnError("");
    setTurns([]);
    setCaptures([]);
    setCurrent(null);
    setResult(null);
    setStep("converse");
    setWaiting(true);

    const sock = new SurveySocket();
    sockRef.current = sock;
    sock.onMessage(handleMessage);
    sock.onState((s) => {
      if (s === "open") {
        sock.startSurvey(null, trimmed, dementiaType);
      } else if (s === "closed") {
        // Only surface as an error if we never received the result.
        setWaiting(false);
      }
    });
    sock.connect(genSessionId());
  }, [name, dementiaType, handleMessage]);

  const submitAnswer = useCallback(() => {
    const t = answer.trim();
    if (!t || waiting) return;
    sockRef.current?.sendSurveyAnswer(t);
    setTurns((ts) => [...ts, { role: "patient", text: t }]);
    setAnswer("");
    setWaiting(true);
  }, [answer, waiting]);

  const skip = useCallback(() => {
    if (waiting) return;
    sockRef.current?.skipQuestion();
    setTurns((ts) => [
      ...ts,
      { role: "patient", text: "(잘 모르겠어요)" },
    ]);
    setAnswer("");
    setWaiting(true);
  }, [waiting]);

  const progress = useMemo(() => {
    if (!current) return { index: 0, total: 12 };
    return { index: current.index, total: current.total };
  }, [current]);

  // ---- Render -----------------------------------------------------------

  if (step === "complete" && result) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-orange-50 via-rose-50 to-amber-50 px-4 py-10">
        <SurveyProfileCard result={result} />
      </div>
    );
  }

  if (step === "setup") {
    return (
      <div className="min-h-screen bg-gradient-to-br from-orange-50 via-rose-50 to-amber-50 px-4 py-10">
        <div className="mx-auto max-w-xl rounded-3xl border border-amber-200 bg-white p-8 shadow-sm">
          <h1 className="text-3xl font-extrabold text-stone-800">초기 설문</h1>
          <p className="mt-2 text-lg leading-relaxed text-stone-500">
            편안하게 이야기 나누며 어르신의 소중한 기억을 함께 모아 봅니다.
            대답하기 어려운 질문은 "잘 모르겠어요"로 넘어가셔도 괜찮아요.
          </p>

          <div className="mt-7">
            <label
              htmlFor="survey_name"
              className="mb-2 block text-base font-semibold text-stone-700"
            >
              어르신 성함
            </label>
            <input
              id="survey_name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") startSurvey();
              }}
              placeholder="예: 김영자"
              className="w-full rounded-xl border border-amber-200 bg-white px-4 py-3 text-lg text-stone-800 focus:border-amber-400 focus:outline-none focus:ring-2 focus:ring-amber-200"
            />
          </div>

          <div className="mt-6">
            <span className="mb-2 block text-base font-semibold text-stone-700">
              치매 유형
            </span>
            <div className="space-y-2">
              {DEMENTIA_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setDementiaType(opt.value)}
                  className={`flex w-full items-start gap-3 rounded-2xl border px-4 py-3 text-left transition ${
                    dementiaType === opt.value
                      ? "border-amber-400 bg-amber-50 ring-2 ring-amber-200"
                      : "border-stone-200 bg-white hover:bg-stone-50"
                  }`}
                >
                  <span
                    className={`mt-1 grid h-5 w-5 shrink-0 place-items-center rounded-full border ${
                      dementiaType === opt.value
                        ? "border-amber-500 bg-amber-500 text-white"
                        : "border-stone-300"
                    }`}
                  >
                    {dementiaType === opt.value ? "✓" : ""}
                  </span>
                  <span>
                    <span className="block text-base font-bold text-stone-800">
                      {opt.label}
                    </span>
                    <span className="block text-sm text-stone-500">
                      {opt.hint}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </div>

          <button
            type="button"
            onClick={startSurvey}
            disabled={!name.trim()}
            className="mt-8 w-full rounded-full bg-amber-warm px-6 py-4 text-lg font-bold text-white shadow-soft transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-40"
          >
            설문 시작
          </button>
        </div>
      </div>
    );
  }

  // step === "converse"
  return (
    <div className="min-h-screen bg-gradient-to-br from-orange-50 via-rose-50 to-amber-50 p-4 md:p-6">
      <div className="mx-auto max-w-6xl">
        <div className="mb-4">
          <h1 className="text-2xl font-bold text-stone-800">
            초기 설문 — {name.trim()} 어르신
          </h1>
          <p className="text-sm text-stone-500">
            천천히 대답해 주세요. 떠올린 기억은 오른쪽에 단서로 모입니다.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
          {/* LEFT (2 cols): conversation */}
          <div className="lg:col-span-2">
            <div className="flex h-[calc(100vh-10rem)] min-h-[480px] flex-col rounded-3xl border border-stone-200 bg-white p-5 shadow-sm">
              {/* progress bar */}
              <div className="mb-3">
                <div className="mb-1 flex items-center justify-between text-xs font-semibold text-stone-500">
                  <span>질문 진행</span>
                  <span>
                    {Math.min(progress.index + 1, progress.total)} /{" "}
                    {progress.total}
                  </span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-stone-100">
                  <div
                    className="h-full rounded-full bg-amber-warm transition-all duration-500"
                    style={{
                      width: `${
                        progress.total > 0
                          ? Math.round((progress.index / progress.total) * 100)
                          : 0
                      }%`,
                    }}
                  />
                </div>
              </div>

              {/* transcript */}
              <div className="flex-1 space-y-3 overflow-y-auto pr-1">
                {turns.length === 0 && !connError && (
                  <p className="py-8 text-center text-base text-stone-400">
                    설문을 준비하고 있어요…
                  </p>
                )}
                {connError && (
                  <div className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-600">
                    ⚠️ {connError}
                  </div>
                )}
                {turns.map((t, i) =>
                  t.role === "persona" ? (
                    <PersonaBubble key={i} preface={t.preface} text={t.text} />
                  ) : (
                    <div key={i} className="flex justify-end">
                      <div className="max-w-[80%] rounded-2xl bg-amber-warm px-4 py-3 text-lg leading-relaxed text-white">
                        {t.text}
                      </div>
                    </div>
                  ),
                )}
                {waiting && (
                  <div className="flex justify-start">
                    <div className="rounded-2xl bg-stone-100 px-4 py-3 text-stone-400">
                      …
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              {/* answer input */}
              <form
                className="mt-4 flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  submitAnswer();
                }}
              >
                <input
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  disabled={waiting || step !== "converse"}
                  placeholder="여기에 대답을 입력하세요…"
                  className="flex-1 rounded-xl border border-stone-300 px-4 py-3 text-lg focus:border-amber-400 focus:outline-none disabled:bg-stone-50"
                />
                <button
                  type="submit"
                  disabled={waiting || !answer.trim()}
                  className="rounded-xl bg-amber-warm px-6 py-3 text-lg font-bold text-white transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  보내기
                </button>
              </form>

              <button
                type="button"
                onClick={skip}
                disabled={waiting}
                className="mt-2 self-start rounded-full bg-stone-100 px-4 py-2 text-sm font-semibold text-stone-600 transition hover:bg-stone-200 disabled:cursor-not-allowed disabled:opacity-40"
              >
                잘 모르겠어요 / 건너뛰기
              </button>
            </div>
          </div>

          {/* RIGHT: live context panel */}
          <div className="lg:col-span-1">
            <div className="h-[calc(100vh-10rem)] min-h-[480px]">
              <SurveyContextPanel
                captures={captures}
                index={progress.index}
                total={progress.total}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function PersonaBubble({
  preface,
  text,
}: {
  preface: string;
  text: string;
}) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl bg-stone-100 px-4 py-3 text-stone-800">
        {preface && (
          <p className="mb-1.5 text-base italic leading-relaxed text-stone-500">
            {preface}
          </p>
        )}
        <p className="text-lg leading-relaxed">{text}</p>
      </div>
    </div>
  );
}
