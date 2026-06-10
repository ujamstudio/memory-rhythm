// survey.tsx — STEP 1 초기 설문 (대화형).
//
// A patient-facing AI-persona conversational onboarding that SETS THE USER'S
// CONTEXT for the therapy flow. Lives at the dedicated /survey route, runs fully
// offline in mock mode, and seeds the patient's store so the subsequent therapy
// call uses real context. Ported from the original Vite frontend onto the
// adopted Memory Rhythm (shadcn/wouter) shell — same SurveySocket WS flow.
//
// Flow:
//   1) Setup    — name input + dementia_type select + "설문 시작".
//   2) Converse — opens its OWN survey WS (SurveySocket -> /ws/survey/{id}),
//                 sends start_survey, then renders persona question bubbles, a
//                 text answer input + send, and a skip button. A live
//                 SurveyContextPanel visualizes Tier-1 extraction.
//   3) Complete — on `survey_complete`, render SurveyProfileCard.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  DementiaType,
  SurveyResult,
  SurveyServerMessage,
} from "../protocol";
import { motion, AnimatePresence } from "framer-motion";
import { Link } from "wouter";
import { SurveySocket } from "../lib/ws";
import { useSpeechInput } from "../lib/useSpeechInput";
import {
  SurveyContextPanel,
  type SurveyCapture,
} from "../components/SurveyContextPanel";
import { SurveyProfileCard } from "../components/SurveyProfileCard";
import { ChatBubble, type ChatLine } from "../components/patient/ChatBubble";
import { TypingDots } from "../components/patient/TypingDots";

// Human-readable Korean labels for the survey domains. Mirrors the backend
// domain->label map so the live panel can show friendly topic names.
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
  // Voice-first: the mic is the default input; tapping ⌨ reveals the text field.
  const [typing, setTyping] = useState(false);

  // completion
  const [result, setResult] = useState<SurveyResult | null>(null);

  // 단서(captures) slide-in drawer, like the patient screen's 추론/앨범.
  const [panelOpen, setPanelOpen] = useState(false);

  const sockRef = useRef<SurveySocket | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const answerRef = useRef<HTMLInputElement | null>(null);

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
        setWaiting(false);
      }
    });
    sock.connect(genSessionId());
  }, [name, dementiaType, handleMessage]);

  // Send a specific text (used both by the form submit and by the voice hook,
  // which hands us the final transcript directly to avoid stale `answer` state).
  const sendAnswer = useCallback(
    (text: string) => {
      const t = text.trim();
      if (!t || waiting) return;
      sockRef.current?.sendSurveyAnswer(t);
      setTurns((ts) => [...ts, { role: "patient", text: t }]);
      setAnswer("");
      setWaiting(true);
    },
    [waiting],
  );

  const submitAnswer = useCallback(() => sendAnswer(answer), [sendAnswer, answer]);

  const skip = useCallback(() => {
    if (waiting) return;
    sockRef.current?.skipQuestion();
    setTurns((ts) => [...ts, { role: "patient", text: "(잘 모르겠어요)" }]);
    setAnswer("");
    setWaiting(true);
  }, [waiting]);

  // Voice-first input via the Web Speech API (shared with the patient screen).
  // The mic is the default; the recognized text is sent on end. When voice is
  // unavailable (no https / unsupported / blocked), drop into the text field.
  const fallbackToTyping = useCallback(() => {
    setTyping(true);
    setTimeout(() => answerRef.current?.focus(), 0);
  }, []);

  const {
    listening,
    start: startListening,
    stop: stopListening,
  } = useSpeechInput({
    onInterim: (t) => setAnswer(t),
    onFinal: (t) => sendAnswer(t),
    onUnheard: () => setAnswer(""),
    onBlocked: fallbackToTyping,
    onInsecure: fallbackToTyping,
    onUnsupported: fallbackToTyping,
  });

  const onMic = useCallback(() => {
    if (waiting) return;
    if (listening) {
      stopListening();
      return;
    }
    if (answer.trim()) {
      sendAnswer(answer);
      return;
    }
    startListening();
  }, [waiting, listening, answer, sendAnswer, startListening, stopListening]);

  const progress = useMemo(() => {
    if (!current) return { index: 0, total: 12 };
    return { index: current.index, total: current.total };
  }, [current]);

  // ---- Render -----------------------------------------------------------

  if (step === "complete" && result) {
    return (
      <div style={{ minHeight: "100dvh", background: "#2a2018", overflow: "auto", padding: "16px" }}>
        <div style={{ maxWidth: "440px", margin: "0 auto" }}>
          <SurveyProfileCard result={result} />
        </div>
      </div>
    );
  }

  if (step === "setup") {
    return (
      <div
        style={{
          minHeight: "100dvh",
          background: "#2a2018",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "16px",
        }}
      >
        <div
          className="paper-surface"
          style={{ width: "100%", maxWidth: "400px", borderRadius: "20px", padding: "22px 20px" }}
        >
          <h1 style={{ fontFamily: '"Gothic A1", sans-serif', fontSize: "20px", fontWeight: 900, color: "#4a3520", margin: 0 }}>
            초기 설문
          </h1>
          <p style={{ fontFamily: '"Gothic A1", sans-serif', fontSize: "13px", lineHeight: 1.6, color: "#8a7a64", marginTop: "8px" }}>
            편안하게 이야기 나누며 어르신의 소중한 기억을 함께 모아 봅니다. 어려운 질문은 "건너뛰기"로 넘어가셔도 괜찮아요.
          </p>

          <div style={{ marginTop: "18px" }}>
            <label htmlFor="survey_name" style={{ display: "block", fontFamily: '"Gothic A1", sans-serif', fontSize: "13px", fontWeight: 700, color: "#6E5A44", marginBottom: "6px" }}>
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
              style={{ width: "100%", boxSizing: "border-box", borderRadius: "12px", border: "1.5px solid rgba(198,117,55,0.3)", padding: "10px 14px", fontFamily: '"Gothic A1", sans-serif', fontSize: "15px", background: "rgba(255,255,255,0.9)", color: "#33291F", outline: "none" }}
            />
          </div>

          <div style={{ marginTop: "14px" }}>
            <span style={{ display: "block", fontFamily: '"Gothic A1", sans-serif', fontSize: "13px", fontWeight: 700, color: "#6E5A44", marginBottom: "6px" }}>
              치매 유형
            </span>
            <div style={{ display: "flex", flexDirection: "column", gap: "7px" }}>
              {DEMENTIA_OPTIONS.map((opt) => {
                const sel = dementiaType === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setDementiaType(opt.value)}
                    style={{ display: "flex", alignItems: "flex-start", gap: "9px", textAlign: "left", borderRadius: "14px", padding: "9px 12px", cursor: "pointer", border: sel ? "1.5px solid #C67537" : "1.5px solid rgba(120,100,80,0.18)", background: sel ? "#F4EBDD" : "rgba(255,255,255,0.7)" }}
                  >
                    <span style={{ marginTop: "2px", display: "grid", placeItems: "center", width: "18px", height: "18px", flexShrink: 0, borderRadius: "50%", fontSize: "11px", color: "#fff", border: sel ? "1px solid #C67537" : "1px solid rgba(120,100,80,0.3)", background: sel ? "#C67537" : "transparent" }}>
                      {sel ? "✓" : ""}
                    </span>
                    <span>
                      <span style={{ display: "block", fontFamily: '"Gothic A1", sans-serif', fontSize: "14px", fontWeight: 800, color: "#4a3520" }}>{opt.label}</span>
                      <span style={{ display: "block", fontFamily: '"Gothic A1", sans-serif', fontSize: "12px", color: "#9A8A74" }}>{opt.hint}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <button
            type="button"
            onClick={startSurvey}
            disabled={!name.trim()}
            style={{ marginTop: "18px", width: "100%", borderRadius: "9999px", background: name.trim() ? "#C67537" : "#C2A98E", color: "#fff", padding: "12px", fontFamily: '"Gothic A1", sans-serif', fontSize: "16px", fontWeight: 800, border: "none", cursor: name.trim() ? "pointer" : "default" }}
          >
            설문 시작
          </button>
        </div>
      </div>
    );
  }

  // step === "converse" — same compact chat format as the patient screen
  const chatLines: ChatLine[] = turns.map((t) =>
    t.role === "persona"
      ? { role: "assistant", text: [t.preface, t.text].filter(Boolean).join(" ") }
      : { role: "user", text: t.text },
  );
  const pct = progress.total > 0 ? Math.round((progress.index / progress.total) * 100) : 0;

  return (
    <div style={{ height: "100dvh", background: "#2a2018", display: "flex", alignItems: "stretch", justifyContent: "center", padding: "clamp(6px, 2vw, 12px)", overflow: "hidden" }}>
      <div
        className="paper-surface"
        style={{ width: "100%", maxWidth: "440px", height: "100%", minHeight: 0, borderRadius: "clamp(12px, 3vw, 20px)", display: "flex", flexDirection: "column", overflow: "hidden" }}
      >
        {/* header */}
        <div style={{ flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px", padding: "8px 11px 7px", fontFamily: '"Gothic A1", sans-serif', borderBottom: "1px solid rgba(198,117,55,0.14)" }}>
          <Link href="/">
            <span style={{ fontSize: "13px", color: "#6E6051", fontWeight: 700, cursor: "pointer" }}>←</span>
          </Link>
          <div style={{ textAlign: "center", lineHeight: 1.1, minWidth: 0 }}>
            <div style={{ fontSize: "13px", color: "#C67537", fontWeight: 900, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              초기 설문 · {name.trim()}
            </div>
            <div style={{ fontSize: "10px", color: "#9A8A74", fontWeight: 700 }}>
              질문 {Math.min(progress.index + 1, progress.total)} / {progress.total}
            </div>
          </div>
          <button
            type="button"
            onClick={() => setPanelOpen(true)}
            aria-label="모은 단서 보기"
            style={{ flexShrink: 0, borderRadius: "9999px", padding: "4px 9px", fontFamily: '"Gothic A1", sans-serif', fontSize: "12px", fontWeight: 800, color: "#6E4A2A", background: "rgba(255,255,255,0.7)", border: "1.5px solid rgba(198,117,55,0.28)", cursor: "pointer", whiteSpace: "nowrap" }}
          >
            단서 {captures.length}
          </button>
        </div>

        {/* progress bar */}
        <div style={{ flexShrink: 0, height: "3px", background: "rgba(198,117,55,0.12)" }}>
          <div style={{ height: "100%", width: `${pct}%`, background: "#C67537", transition: "width 0.5s ease" }} />
        </div>

        {/* chat */}
        <div role="log" aria-live="polite" aria-label="설문 대화" style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "7px", padding: "10px 6px 8px", minHeight: 0 }}>
          {turns.length === 0 && !connError && (
            <p style={{ textAlign: "center", color: "#9A8A74", fontFamily: '"Gothic A1", sans-serif', fontWeight: 700, fontSize: "13px", padding: "20px 0" }}>
              설문을 준비하고 있어요…
            </p>
          )}
          {connError && (
            <div style={{ textAlign: "center", color: "#b4524a", fontSize: "12px", fontFamily: '"Gothic A1", sans-serif', padding: "6px 10px" }}>⚠️ {connError}</div>
          )}
          {chatLines.map((m, i) => (
            <ChatBubble key={i} line={m} />
          ))}
          {waiting && <TypingDots />}
          <div ref={chatEndRef} />
        </div>

        {/* Voice-first bottom bar: 건너뛰기 · [🎤 눌러서 말하기] · ⌨ (typing reveals
            the text field with send + mic-back). Mirrors the patient screen. */}
        <div style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: "6px", padding: "7px 9px 9px", borderTop: "1px solid rgba(198,117,55,0.14)", background: "rgba(244,235,221,0.7)", backdropFilter: "blur(8px)" }}>
          <button
            type="button"
            onClick={skip}
            disabled={waiting}
            title="잘 모르겠어요 / 건너뛰기"
            aria-label="건너뛰기"
            style={{ flexShrink: 0, width: "34px", height: "34px", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: '"Gothic A1", sans-serif', fontSize: "16px", fontWeight: 800, color: "#8a6a3f", background: "#EFE2CC", border: "none", cursor: waiting ? "default" : "pointer", opacity: waiting ? 0.5 : 1 }}
          >
            ⤳
          </button>

          {typing ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                submitAnswer();
              }}
              style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: "6px" }}
            >
              <label htmlFor="survey_answer" className="sr-only">대답 입력</label>
              <input
                id="survey_answer"
                ref={answerRef}
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                disabled={waiting}
                placeholder={waiting ? "…" : "대답 입력…"}
                style={{ flex: 1, minWidth: 0, borderRadius: "9999px", border: "1.5px solid rgba(198,117,55,0.3)", padding: "9px 14px", fontFamily: '"Gothic A1", sans-serif', fontSize: "15px", background: "rgba(255,255,255,0.9)", color: "#33291F", outline: "none" }}
              />
              <button
                type="submit"
                disabled={waiting || !answer.trim()}
                aria-label="대답 보내기"
                style={{ flexShrink: 0, width: "40px", height: "40px", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", border: "none", background: waiting || !answer.trim() ? "#C2A98E" : "linear-gradient(#D98040, #C67537)", boxShadow: "0 2px 6px rgba(130,70,30,0.3)", color: "#fff", cursor: waiting || !answer.trim() ? "default" : "pointer" }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z" />
                </svg>
              </button>
              <button
                type="button"
                onClick={() => setTyping(false)}
                aria-label="음성으로 입력"
                style={{ flexShrink: 0, width: "40px", height: "40px", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", border: "none", background: "#EFE2CC", color: "#8a6a3f", cursor: "pointer" }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <rect x="9" y="2" width="6" height="11" rx="3" />
                  <path d="M5 10a7 7 0 0 0 14 0M12 17v4" />
                </svg>
              </button>
            </form>
          ) : (
            <>
              <button
                type="button"
                onClick={onMic}
                disabled={waiting}
                aria-label={listening ? "그만 듣기" : "눌러서 말하기"}
                className={listening ? "mic-pulse" : "phys-btn"}
                style={{ flex: 1, minWidth: 0, height: "44px", borderRadius: "9999px", display: "flex", alignItems: "center", justifyContent: "center", gap: "8px", border: "none", background: listening ? "linear-gradient(#C66A2E, #A85420)" : waiting ? "#C2A98E" : "linear-gradient(#D98040, #C67537)", color: "#fff", fontFamily: '"Gothic A1", sans-serif', fontWeight: 800, fontSize: "15px", cursor: waiting ? "default" : "pointer", boxShadow: "0 3px 8px rgba(130,70,30,0.28)" }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <rect x="9" y="2" width="6" height="11" rx="3" />
                  <path d="M5 10a7 7 0 0 0 14 0M12 17v4" />
                </svg>
                <span style={{ maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {waiting ? "잠시만요…" : listening ? answer.trim() || "듣는 중…" : "눌러서 말하기"}
                </span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setTyping(true);
                  setTimeout(() => answerRef.current?.focus(), 0);
                }}
                aria-label="글자로 입력"
                style={{ flexShrink: 0, width: "40px", height: "40px", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", border: "none", background: "#EFE2CC", color: "#8a6a3f", cursor: "pointer" }}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <rect x="2" y="6" width="20" height="12" rx="2" />
                  <path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M6 14h12" />
                </svg>
              </button>
            </>
          )}
        </div>
      </div>

      {/* 단서(captures) slide-in drawer */}
      <SurveyContextDrawer
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        captures={captures}
        index={progress.index}
        total={progress.total}
      />
    </div>
  );
}

function SurveyContextDrawer({
  open,
  onClose,
  captures,
  index,
  total,
}: {
  open: boolean;
  onClose: () => void;
  captures: SurveyCapture[];
  index: number;
  total: number;
}) {
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="bd"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            onClick={onClose}
            style={{ position: "fixed", inset: 0, background: "rgba(40,30,20,0.4)", backdropFilter: "blur(2px)", zIndex: 40 }}
          />
          <motion.aside
            key="dw"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 320, damping: 34 }}
            style={{ position: "fixed", top: 0, right: 0, height: "100dvh", width: "clamp(300px, 92vw, 420px)", background: "#F4EBDD", boxShadow: "-12px 0 40px rgba(40,25,10,0.3)", zIndex: 41, display: "flex", flexDirection: "column", padding: "clamp(12px, 3vw, 18px)", gap: "10px" }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
              <div style={{ fontFamily: '"Gothic A1", sans-serif', fontSize: "16px", fontWeight: 900, color: "#4a3520" }}>모은 기억 단서</div>
              <button type="button" onClick={onClose} aria-label="닫기" style={{ width: "36px", height: "36px", borderRadius: "50%", border: "none", cursor: "pointer", fontSize: "18px", fontWeight: 900, color: "#6E4A2A", background: "rgba(255,255,255,0.8)" }}>
                ✕
              </button>
            </div>
            <div style={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
              <SurveyContextPanel captures={captures} index={index} total={total} />
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
