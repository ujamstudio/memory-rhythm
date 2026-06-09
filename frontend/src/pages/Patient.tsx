// patient.tsx — the live therapy session screen.
//
// Adopts the Memory Rhythm (Replit) visual language — warm paper card, 🧠 chat
// bubbles, progressive HintPolaroid, big tactile mic/hint buttons, 40Hz gamma
// ring — but is driven entirely by the FastAPI dual-LLM WebSocket loop
// (../lib/ws WSClient) instead of the original scripted TASKS mock.
//
// Data flow (all from the backend, zero secrets in mock mode):
//   assistant_message -> 🧠 bubble + real hint_level (drives the Polaroid)
//   reasoning         -> ReasoningPanel (두뇌 decision + latency)
//   stage_change      -> stage badge + a centered divider line
//   autobiography_page -> AutobiographyPanel (right column, desktop)
//   recall_prompt     -> a 🔔 bubble (forgetting-curve re-question)
//
// The 40Hz gamma ring (visual) + 40Hz tone (audio) share one photosensitive
// consent gate (SafetyNotice); an always-visible OFF bar can kill them instantly.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Link, useSearch } from "wouter";
import type {
  AutobiographyPage,
  ReasoningMsg,
  ServerMessage,
} from "../protocol";
import { stageLabel } from "../protocol";
import { WSClient } from "../lib/ws";
import { useClock } from "../lib/useClock";
import { ReasoningPanel } from "../components/ReasoningPanel";
import { useGammaTone } from "../components/GammaTone";
import { SafetyNotice, StimulationOffBar } from "../components/SafetyNotice";
import { ChatBubble, type ChatLine } from "../components/patient/ChatBubble";
import { HintPolaroid } from "../components/patient/HintPolaroid";
import { TypingDots } from "../components/patient/TypingDots";
import { AutobiographyPanel } from "../components/patient/AutobiographyPanel";

// Fixed demo session id so the scripted scenario (plan §10) is reproducible.
const DEMO_SESSION_ID = "demo-session";
const DEMO_PATIENT_ID = "demo-patient";

// Quick-pick replies that drive the scripted "시장"(market) recall demo so a
// presenter can click through the scenario without typing.
const QUICK_REPLIES = [
  "잘 기억이 안 나네…",
  "글쎄, 옛날 일이라…",
  "아 맞다, 시장에 갔었지!",
  "고등어를 사러 갔던 것 같아",
];

export default function Patient() {
  // Optional ?patient= from the URL (set by the survey hand-off). When present
  // we drive start_session with the SURVEYED patient's id so their seeded
  // memories/autobiography are used. Absent -> demo default.
  const search = useSearch();
  const patientId =
    (new URLSearchParams(search).get("patient") || "").trim() ||
    DEMO_PATIENT_ID;

  const [connected, setConnected] = useState(false);
  // Effective LLM backend ("google" | "mock" | ...) from /api/health, so the
  // presenter can see at a glance whether the live model or the mock fallback
  // is actually serving — a silent 429 otherwise looks identical on screen.
  const [llmBackend, setLlmBackend] = useState<string>("");
  const [messages, setMessages] = useState<ChatLine[]>([]);
  const [pages, setPages] = useState<AutobiographyPage[]>([]);
  const [reasoningLog, setReasoningLog] = useState<ReasoningMsg[]>([]);
  const [stage, setStage] = useState(1);
  const [hintLevel, setHintLevel] = useState(0);
  const [awaiting, setAwaiting] = useState(false);
  const [listening, setListening] = useState(false);
  const [input, setInput] = useState("");

  // 40Hz stimulation (gamma ring + tone) — share one consent gate.
  const [stimOn, setStimOn] = useState(false);
  const [consented, setConsented] = useState(false);
  const [consentOpen, setConsentOpen] = useState(false);

  const wsRef = useRef<WSClient | null>(null);
  const startedRef = useRef(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  // Browser SpeechRecognition instance (Web Speech API) for voice answers.
  const recognitionRef = useRef<any>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const gamma = useGammaTone();
  const clock = useClock();

  // ---- WebSocket wiring -------------------------------------------------

  const handleServerMessage = useCallback((msg: ServerMessage) => {
    switch (msg.type) {
      case "reasoning":
        setReasoningLog((log) => [...log, msg]);
        break;
      case "stage_change":
        setStage(msg.stage);
        setMessages((m) => [
          ...m,
          { role: "system", text: `— ${msg.stage}단계 · ${msg.label} —` },
        ]);
        break;
      case "assistant_message":
        setStage(msg.stage);
        setHintLevel(msg.hint_level);
        setAwaiting(false);
        setMessages((m) => [
          ...m,
          { role: "assistant", text: msg.text, hintLevel: msg.hint_level },
        ]);
        break;
      case "autobiography_page":
        setPages((p) => {
          if (p.some((x) => x.id === msg.page.id)) return p;
          return [...p, msg.page].sort((a, b) => a.order_idx - b.order_idx);
        });
        break;
      case "recall_prompt":
        setMessages((m) => [...m, { role: "assistant", text: `🔔 ${msg.text}` }]);
        break;
      case "audio":
        if (msg.b64) {
          try {
            const audio = new Audio(`data:audio/mp3;base64,${msg.b64}`);
            void audio.play();
          } catch {
            /* ignore autoplay errors */
          }
        }
        break;
      case "error":
        setAwaiting(false);
        setMessages((m) => [...m, { role: "system", text: `⚠️ ${msg.message}` }]);
        break;
    }
  }, []);

  useEffect(() => {
    const client = new WSClient();
    wsRef.current = client;
    const offMsg = client.onMessage(handleServerMessage);
    const offState = client.onState((s) => {
      setConnected(s === "open");
      // Auto-start the call once the socket opens (the user already pressed
      // "시작하기" on the landing screen).
      if (s === "open") {
        // (Re)bind the session on connect AND on every auto-reconnect, so the
        // session keeps working after a backend restart / network drop.
        client.startSession(patientId);
        if (!startedRef.current) {
          startedRef.current = true;
          // The backend does NOT greet on start_session (it only replies to a
          // user turn), so we must NOT set `awaiting` here — doing so left every
          // button disabled forever. Show a warm opening prompt locally so the
          // patient has something to answer; their reply kicks off the loop.
          setMessages((m) => [
            ...m,
            { role: "system", text: "— 통화가 시작되었습니다 —" },
            {
              role: "assistant",
              text: "안녕하세요~ 또 이렇게 만나니 참 반가워요! 오늘은 어떻게 지내셨어요? 천천히, 편하게 이야기 나눠요.",
            },
          ]);
        } else {
          // Reconnected after a drop — un-stick any pending wait so the patient
          // can retry their last answer.
          setAwaiting(false);
          setMessages((m) => [
            ...m,
            { role: "system", text: "— 다시 연결되었습니다. 방금 하신 말씀을 한 번만 더 들려주세요. —" },
          ]);
        }
      }
    });
    client.connect(DEMO_SESSION_ID);
    return () => {
      offMsg();
      offState();
      client.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handleServerMessage]);

  // Auto-scroll chat.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, awaiting]);

  // Probe the effective LLM backend once so the top bar can show a live/mock
  // badge (demo observability — pairs with the reasoning panel's per-turn model).
  useEffect(() => {
    let cancelled = false;
    fetch("/api/health")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!cancelled && d) setLlmBackend(d?.providers?.llm || d?.provider || "");
      })
      .catch(() => {
        /* health probe is best-effort; badge stays hidden */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Watchdog: never wait forever. If no reply arrives within ~25s (slow/lost
  // backend turn, dropped socket), un-stick the UI so the patient can retry.
  useEffect(() => {
    if (!awaiting) return;
    const t = setTimeout(() => {
      setAwaiting(false);
      setMessages((m) => [
        ...m,
        { role: "system", text: "⏱️ 응답이 늦어지고 있어요. 다시 한 번 말씀해 주세요." },
      ]);
    }, 25000);
    return () => clearTimeout(t);
  }, [awaiting]);

  // Stop any in-flight speech recognition on unmount.
  useEffect(
    () => () => {
      try {
        recognitionRef.current?.stop();
      } catch {
        /* ignore */
      }
    },
    [],
  );

  // ---- Actions ----------------------------------------------------------

  const sendText = useCallback((text: string) => {
    const t = text.trim();
    if (!t) return;
    const client = wsRef.current;
    if (!client) return;
    if (client.state !== "open") {
      // Socket dropped (e.g. backend restart). Don't optimistically wait — the
      // client is auto-reconnecting; ask the patient to retry shortly.
      setMessages((m) => [
        ...m,
        { role: "system", text: "연결이 잠시 끊겼어요. 다시 연결되면 말씀해 주세요…" },
      ]);
      return;
    }
    client.sendUserMessage(t);
    setMessages((m) => [...m, { role: "user", text: t }]);
    setAwaiting(true);
    setInput("");
  }, []);

  const askForHint = useCallback(() => {
    // Hint level is decided by the 두뇌; nudge it by asking for help. The
    // backend may raise hint_level, which updates the Polaroid via the next
    // assistant_message.
    sendText("잘 모르겠어요. 힌트를 좀 더 주세요.");
  }, [sendText]);

  // Voice answer via the Web Speech API (Korean). Clicking the mic starts
  // listening; the recognized text is sent automatically. Falls back to the
  // text input when the browser has no SpeechRecognition (e.g. Firefox).
  const startListening = useCallback(() => {
    const SR =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;
    if (!SR) {
      inputRef.current?.focus();
      return;
    }
    try {
      const rec = new SR();
      rec.lang = "ko-KR";
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      rec.onresult = (e: any) => {
        const transcript = e?.results?.[0]?.[0]?.transcript ?? "";
        if (transcript.trim()) sendText(transcript);
      };
      rec.onerror = () => setListening(false);
      rec.onend = () => setListening(false);
      recognitionRef.current = rec;
      setListening(true);
      rec.start();
    } catch {
      setListening(false);
      inputRef.current?.focus();
    }
  }, [sendText]);

  const stopListening = useCallback(() => {
    try {
      recognitionRef.current?.stop();
    } catch {
      /* ignore */
    }
    setListening(false);
  }, []);

  // The big mic button: stop if listening, send typed text if present,
  // otherwise start voice capture.
  const onMic = useCallback(() => {
    if (awaiting) return;
    if (listening) {
      stopListening();
      return;
    }
    if (input.trim()) {
      sendText(input);
      return;
    }
    startListening();
  }, [awaiting, listening, input, sendText, startListening, stopListening]);

  const advanceTime = useCallback((days: number) => {
    wsRef.current?.advanceTime(days);
    setMessages((m) => [...m, { role: "system", text: `⏩ 시간 가속: +${days}일` }]);
  }, []);

  // ---- 40Hz stimulation (consent-gated) ---------------------------------

  const enableStim = useCallback(() => {
    gamma.start();
    setStimOn(true);
    wsRef.current?.toggleTone(true);
  }, [gamma]);

  const disableStim = useCallback(() => {
    gamma.stop();
    setStimOn(false);
    wsRef.current?.toggleTone(false);
  }, [gamma]);

  const toggleStim = useCallback(() => {
    if (stimOn) {
      disableStim();
      return;
    }
    if (!consented) {
      setConsentOpen(true);
      return;
    }
    enableStim();
  }, [stimOn, consented, disableStim, enableStim]);

  const acceptConsent = useCallback(() => {
    setConsented(true);
    setConsentOpen(false);
    enableStim();
  }, [enableStim]);

  const declineConsent = useCallback(() => setConsentOpen(false), []);

  // ---- Derived ----------------------------------------------------------

  const focusKeyword = useMemo(() => {
    for (let i = reasoningLog.length - 1; i >= 0; i--) {
      const kws = reasoningLog[i].decision.keywords;
      if (kws && kws.length > 0) return kws[0];
    }
    return undefined;
  }, [reasoningLog]);

  const micLabel = awaiting
    ? "기다리는 중"
    : listening
      ? "듣는 중"
      : input.trim()
        ? "보내기"
        : "대답하기";
  const micActive = awaiting || listening;
  const maxHint = hintLevel >= 4;

  // ---- Render -----------------------------------------------------------

  return (
    <div
      style={{
        // min-height (not fixed height) + scroll so that when an 어르신 zooms the
        // browser or uses a short viewport, the mic/입력 controls are never
        // clipped off-screen — the whole page scrolls instead.
        minHeight: "100dvh",
        background: "#2a2018",
        display: "flex",
        alignItems: "stretch",
        justifyContent: "center",
        gap: "clamp(6px, 1.5vw, 12px)",
        padding: "clamp(6px, 2vw, 12px)",
        overflowY: "auto",
      }}
    >
      {stimOn && <div className="gamma-ring" />}

      {/* Hero: warm paper conversation card */}
      <div
        className="paper-surface"
        style={{
          flex: 1,
          minWidth: 0,
          borderRadius: "clamp(16px, 4vw, 28px)",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* Top bar */}
        <div
          style={{
            flexShrink: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding:
              "clamp(10px, 3vw, 18px) clamp(14px, 4vw, 28px) clamp(8px, 2vw, 12px)",
            fontFamily: '"Gothic A1", sans-serif',
            borderBottom: "1.5px solid rgba(198,117,55,0.14)",
          }}
        >
          <Link href="/patient">
            <span
              style={{
                fontSize: "clamp(14px, 3.5vw, 18px)",
                color: "#6E6051",
                fontWeight: 700,
                cursor: "pointer",
              }}
            >
              ← 처음으로
            </span>
          </Link>

          <div style={{ textAlign: "center" }}>
            <div
              style={{
                fontSize: "clamp(12px, 3vw, 16px)",
                color: "#6E6051",
                fontWeight: 700,
              }}
            >
              {clock.date}
            </div>
            <div
              style={{
                fontSize: "clamp(16px, 4vw, 22px)",
                color: "#C67537",
                fontWeight: 900,
              }}
            >
              {clock.time}
            </div>
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              fontWeight: 800,
            }}
          >
            {llmBackend && (
              <span
                title={`AI 모델 백엔드: ${llmBackend}`}
                style={{
                  fontSize: "clamp(10px, 2.5vw, 12px)",
                  fontWeight: 800,
                  padding: "2px 8px",
                  borderRadius: "9999px",
                  whiteSpace: "nowrap",
                  color: llmBackend === "mock" ? "#8a6a3f" : "#2f6b3a",
                  background:
                    llmBackend === "mock"
                      ? "rgba(201,160,94,0.18)"
                      : "rgba(106,170,106,0.18)",
                  border:
                    llmBackend === "mock"
                      ? "1px solid rgba(201,160,94,0.5)"
                      : "1px solid rgba(106,170,106,0.5)",
                }}
              >
                {llmBackend === "mock" ? "AI: mock" : `AI: ${llmBackend}`}
              </span>
            )}
            <span
              style={{
                width: "10px",
                height: "10px",
                borderRadius: "50%",
                background: connected ? "#6aaa6a" : "#c9a05e",
                boxShadow: connected ? "0 0 8px rgba(106,170,106,0.7)" : "none",
              }}
            />
            <span
              style={{
                fontSize: "clamp(12px, 3vw, 15px)",
                color: "#6E4A2A",
                whiteSpace: "nowrap",
              }}
            >
              {stage}단계 · {stageLabel(stage)} · 힌트 {hintLevel}/4
            </span>
          </div>
        </div>

        {/* Polaroid hint (driven by real hint_level) */}
        <HintPolaroid hintLevel={hintLevel} keyword={focusKeyword} />

        {/* Chat scroll — role=log + aria-live so a screen reader announces each
            new AI(🧠) reply / recall prompt for low-vision 어르신. */}
        <div
          role="log"
          aria-live="polite"
          aria-relevant="additions"
          aria-label="대화 내용"
          style={{
            flex: 1,
            overflowY: "auto",
            display: "flex",
            flexDirection: "column",
            gap: "clamp(12px, 3vw, 20px)",
            padding:
              "clamp(14px, 4vw, 24px) clamp(4px, 1.5vw, 8px) clamp(10px, 3vw, 16px)",
            minHeight: 0,
          }}
        >
          {messages.length === 0 && !awaiting && (
            <p
              style={{
                textAlign: "center",
                color: "#9A8A74",
                fontFamily: '"Gothic A1", sans-serif',
                fontWeight: 700,
                padding: "24px 0",
              }}
            >
              연결되면 따뜻한 인사로 대화가 시작됩니다…
            </p>
          )}
          <AnimatePresence initial={false}>
            {messages.map((m, i) => (
              <ChatBubble key={i} line={m} />
            ))}
          </AnimatePresence>
          <AnimatePresence>
            {awaiting && (
              <motion.div
                key="typing"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 6 }}
                transition={{ duration: 0.3 }}
              >
                <TypingDots />
              </motion.div>
            )}
          </AnimatePresence>
          <div ref={bottomRef} />
        </div>

        {/* Quick replies (scripted demo helper) */}
        <div
          style={{
            flexShrink: 0,
            display: "flex",
            flexWrap: "wrap",
            gap: "8px",
            justifyContent: "center",
            padding: "0 clamp(12px, 4vw, 28px) 6px",
          }}
        >
          {QUICK_REPLIES.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => sendText(q)}
              disabled={awaiting}
              className="phys-btn"
              style={{
                borderRadius: "9999px",
                padding: "8px 16px",
                fontFamily: '"Gothic A1", sans-serif',
                fontSize: "clamp(12px, 3vw, 15px)",
                fontWeight: 700,
                color: "#6E4A2A",
                background: "rgba(255,255,255,0.7)",
                border: "1.5px solid rgba(198,117,55,0.25)",
                cursor: awaiting ? "default" : "pointer",
                opacity: awaiting ? 0.5 : 1,
              }}
            >
              {q}
            </button>
          ))}
        </div>

        {/* Typed input */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            sendText(input);
          }}
          style={{
            flexShrink: 0,
            display: "flex",
            gap: "8px",
            padding: "0 clamp(12px, 4vw, 28px) 8px",
          }}
        >
          <label htmlFor="patient-input" className="sr-only">
            대답을 입력하세요
          </label>
          <input
            id="patient-input"
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="여기에 말을 입력하세요…"
            style={{
              flex: 1,
              borderRadius: "14px",
              border: "1.5px solid rgba(198,117,55,0.3)",
              padding: "12px 18px",
              fontFamily: '"Gothic A1", sans-serif',
              fontSize: "clamp(15px, 3.5vw, 19px)",
              background: "rgba(255,255,255,0.85)",
              color: "#33291F",
              outline: "none",
            }}
          />
          {/* Always-visible 보내기 button so typing is a real, discoverable path
              (Enter/mic are not obvious to 어르신). Disabled when empty/awaiting. */}
          <button
            type="submit"
            disabled={awaiting || !input.trim()}
            className="phys-btn"
            aria-label="대답 보내기"
            style={{
              flexShrink: 0,
              borderRadius: "14px",
              padding: "0 clamp(18px, 5vw, 28px)",
              minWidth: "clamp(64px, 18vw, 96px)",
              fontFamily: '"Gothic A1", sans-serif',
              fontSize: "clamp(15px, 3.5vw, 19px)",
              fontWeight: 800,
              color: "#FFFFFF",
              background: awaiting || !input.trim() ? "#C2A98E" : "#C67537",
              border: "none",
              cursor: awaiting || !input.trim() ? "default" : "pointer",
            }}
          >
            보내기
          </button>
        </form>

        {/* Footer: hint · big mic · 40Hz */}
        <div
          style={{
            flexShrink: 0,
            borderTop: "1.5px solid rgba(198,117,55,0.14)",
            padding:
              "clamp(10px, 3vw, 18px) clamp(16px, 4vw, 32px) clamp(14px, 4vw, 22px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "clamp(10px, 3vw, 20px)",
            flexWrap: "wrap",
            background: "rgba(244,235,221,0.7)",
            backdropFilter: "blur(8px)",
          }}
        >
          {/* Hint */}
          <button
            type="button"
            onClick={askForHint}
            disabled={maxHint || awaiting}
            className="phys-btn"
            aria-label={maxHint ? "힌트를 모두 봤어요" : "힌트 보기"}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "clamp(6px, 1.5vw, 10px)",
              borderRadius: "9999px",
              padding: "clamp(10px, 2.5vw, 16px) clamp(16px, 4vw, 28px)",
              fontFamily: '"Gothic A1", sans-serif',
              fontSize: "clamp(16px, 4vw, 24px)",
              fontWeight: 800,
              cursor: maxHint || awaiting ? "default" : "pointer",
              background: maxHint ? "#E3D2B8" : "linear-gradient(#EAD0A4, #D7B279)",
              opacity: maxHint ? 0.7 : 1,
              boxShadow: maxHint
                ? "inset 0 2px 0 rgba(255,255,255,0.4), 0 4px 0 #a8824a"
                : "inset 0 2px 0 rgba(255,255,255,0.6), 0 6px 0 #a8824a, 0 8px 16px rgba(110,80,40,0.25)",
              color: "#4a3520",
              border: "none",
              flexShrink: 0,
            }}
          >
            <svg
              width="28"
              height="28"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M9 18h6M10 21h4" />
              <path d="M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.4 1 2.5h6c0-1.1.3-1.8 1-2.5A6 6 0 0 0 12 3z" />
            </svg>
            {maxHint ? "다 봤어요" : "힌트"}
          </button>

          {/* Big mic / send */}
          <button
            type="button"
            onClick={onMic}
            disabled={awaiting}
            aria-label={`음성으로 대답: ${micLabel}`}
            aria-pressed={micActive}
            className={micActive ? "mic-pulse" : "phys-btn"}
            style={{
              width: "clamp(120px, 30vw, 156px)",
              height: "clamp(120px, 30vw, 156px)",
              borderRadius: "50%",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: "4px",
              cursor: awaiting ? "default" : "pointer",
              border: "none",
              background: micActive
                ? "linear-gradient(#e05a2b, #c44015)"
                : "linear-gradient(#D98040, #C67537)",
              boxShadow: micActive
                ? "inset 0 3px 0 rgba(255,255,255,0.3), 0 8px 0 #8a3a10"
                : "inset 0 3px 0 rgba(255,255,255,0.35), 0 8px 0 #8a4a1f, 0 12px 20px rgba(130,70,30,0.35)",
              color: "white",
              fontFamily: '"Gothic A1", sans-serif',
              transition: "background 0.4s ease, box-shadow 0.3s ease",
              flexShrink: 0,
            }}
          >
            <svg
              width="42"
              height="42"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <rect x="9" y="3" width="6" height="11" rx="3" />
              <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
            </svg>
            <span
              style={{
                fontSize: "clamp(14px, 3.5vw, 20px)",
                fontWeight: 800,
                letterSpacing: "-0.01em",
              }}
            >
              {micLabel}
            </span>
          </button>

          {/* 40Hz stimulation toggle */}
          <button
            type="button"
            onClick={toggleStim}
            aria-label={`40헤르츠 안정화 음 ${stimOn ? "끄기" : "켜기"}`}
            aria-pressed={stimOn}
            className="phys-btn"
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "2px",
              borderRadius: "9999px",
              padding: "clamp(10px, 2.5vw, 16px) clamp(14px, 3.5vw, 22px)",
              fontFamily: '"Gothic A1", sans-serif',
              fontSize: "clamp(13px, 3vw, 17px)",
              fontWeight: 800,
              cursor: "pointer",
              background: stimOn ? "linear-gradient(#D98040, #C67537)" : "#EFE2CC",
              color: stimOn ? "#FCF8F1" : "#8a6a3f",
              boxShadow: stimOn
                ? "inset 0 2px 0 rgba(255,255,255,0.3), 0 5px 0 #8a4a1f"
                : "inset 0 2px 0 rgba(255,255,255,0.5), 0 4px 0 #c9b48f",
              border: "none",
              flexShrink: 0,
            }}
          >
            <span>40Hz</span>
            <span style={{ fontSize: "clamp(10px, 2.5vw, 12px)", fontWeight: 700 }}>
              {stimOn ? "켜짐" : "꺼짐"}
            </span>
          </button>
        </div>

        {/* Time-acceleration (forgetting-curve demo) */}
        <div
          style={{
            flexShrink: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "8px",
            padding: "0 clamp(12px, 4vw, 28px) clamp(10px, 3vw, 16px)",
            fontFamily: '"Gothic A1", sans-serif',
          }}
        >
          <span style={{ fontSize: "12px", fontWeight: 700, color: "#9A8A74" }}>
            시간 가속:
          </span>
          {[1, 3, 7, 21].map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => advanceTime(d)}
              className="phys-btn"
              style={{
                borderRadius: "10px",
                padding: "6px 12px",
                fontSize: "12px",
                fontWeight: 800,
                color: "#6E4A2A",
                background: "rgba(255,255,255,0.65)",
                border: "1px solid rgba(198,117,55,0.2)",
                cursor: "pointer",
              }}
            >
              +{d}일
            </button>
          ))}
        </div>
      </div>

      {/* Right column (desktop): 두뇌 reasoning + autobiography */}
      <aside className="hidden w-[360px] shrink-0 flex-col gap-3 lg:flex">
        <div className="min-h-0 flex-1">
          <ReasoningPanel log={reasoningLog} />
        </div>
        <AutobiographyPanel pages={pages} />
      </aside>

      {/* Safety: consent modal + always-visible OFF bar */}
      <SafetyNotice
        open={consentOpen}
        onAccept={acceptConsent}
        onDecline={declineConsent}
      />
      <StimulationOffBar active={stimOn} onOff={disableStim} />
    </div>
  );
}
