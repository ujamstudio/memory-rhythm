// Patient.tsx — the D1 (handset) + D2 (e-book) split-screen experience.
//
// Owns the WebSocket connection (via ../lib/ws WSClient), and holds all the
// session state: chat messages, autobiography pages, the reasoning log, the
// current stage / hint level, and the 40Hz tone state. The 40Hz tone + e-book
// flicker are gated behind the photosensitive-seizure consent (SafetyNotice).
//
// Layout:
//   LEFT column  = Handset + ReasoningPanel + chat input
//   RIGHT column = Ebook (autobiography)

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type {
  AutobiographyPage,
  ReasoningMsg,
  ServerMessage,
} from "../protocol";
import { stageLabel } from "../protocol";
import { WSClient } from "../lib/ws";
import { Handset } from "../components/Handset";
import { ReasoningPanel } from "../components/ReasoningPanel";
import { Ebook } from "../components/Ebook";
import { useGammaTone } from "../components/GammaTone";
import { SafetyNotice, StimulationOffBar } from "../components/SafetyNotice";

// Fixed demo session id so the scripted scenario (plan §10) is reproducible.
const DEMO_SESSION_ID = "demo-session";
const DEMO_PATIENT_ID = "demo-patient";

type ChatRole = "user" | "assistant" | "system";
interface ChatLine {
  role: ChatRole;
  text: string;
  stage?: number;
  hintLevel?: number;
}

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
  // we drive start_session (and any REST calls) with the SURVEYED patient's id
  // so their seeded memories/autobiography are used. Absent -> demo default.
  const [searchParams] = useSearchParams();
  const patientId = (searchParams.get("patient") || "").trim() || DEMO_PATIENT_ID;

  const [connected, setConnected] = useState(false);
  const [inCall, setInCall] = useState(false);
  const [messages, setMessages] = useState<ChatLine[]>([]);
  const [pages, setPages] = useState<AutobiographyPage[]>([]);
  const [reasoningLog, setReasoningLog] = useState<ReasoningMsg[]>([]);
  const [stage, setStage] = useState(1);
  const [hintLevel, setHintLevel] = useState(0);

  // 40Hz stimulation state. Tone + flicker share one consent gate.
  const [toneOn, setToneOn] = useState(false);
  const [flickerOn, setFlickerOn] = useState(false);
  const [consented, setConsented] = useState(false);
  const [consentOpen, setConsentOpen] = useState(false);
  // What the user wanted to enable; applied once consent is granted.
  const pendingRef = useRef<"tone" | "flicker" | null>(null);

  const [input, setInput] = useState("");
  const wsRef = useRef<WSClient | null>(null);
  const gamma = useGammaTone();
  const chatEndRef = useRef<HTMLDivElement | null>(null);

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
        setMessages((m) => [
          ...m,
          {
            role: "assistant",
            text: msg.text,
            stage: msg.stage,
            hintLevel: msg.hint_level,
          },
        ]);
        break;
      case "autobiography_page":
        setPages((p) => {
          // Avoid duplicates if the page id was already added.
          if (p.some((x) => x.id === msg.page.id)) return p;
          return [...p, msg.page].sort((a, b) => a.order_idx - b.order_idx);
        });
        break;
      case "recall_prompt":
        setMessages((m) => [
          ...m,
          { role: "assistant", text: `🔔 ${msg.text}` },
        ]);
        break;
      case "audio":
        // Optional TTS. Mock omits this; play if present.
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
        setMessages((m) => [
          ...m,
          { role: "system", text: `⚠️ ${msg.message}` },
        ]);
        break;
    }
  }, []);

  useEffect(() => {
    const client = new WSClient();
    wsRef.current = client;
    const offMsg = client.onMessage(handleServerMessage);
    const offState = client.onState((s) => {
      setConnected(s === "open");
      if (s === "closed") setInCall(false);
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
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  // ---- Actions ----------------------------------------------------------

  const startCall = useCallback(() => {
    const client = wsRef.current;
    if (!client) return;
    client.startSession(patientId);
    setInCall(true);
    setConnected(true);
    setMessages((m) => [
      ...m,
      { role: "system", text: "— 통화가 시작되었습니다 —" },
    ]);
  }, [patientId]);

  const sendText = useCallback(
    (text: string) => {
      const t = text.trim();
      if (!t) return;
      const client = wsRef.current;
      if (!client) return;
      if (!inCall) startCall();
      client.sendUserMessage(t);
      setMessages((m) => [...m, { role: "user", text: t }]);
      setInput("");
    },
    [inCall, startCall],
  );

  const advanceTime = useCallback((days: number) => {
    wsRef.current?.advanceTime(days);
    setMessages((m) => [
      ...m,
      { role: "system", text: `⏩ 시간 가속: +${days}일` },
    ]);
  }, []);

  // ---- 40Hz stimulation (consent-gated) ---------------------------------

  const enableTone = useCallback(() => {
    gamma.start();
    setToneOn(true);
    wsRef.current?.toggleTone(true);
  }, [gamma]);

  const disableTone = useCallback(() => {
    gamma.stop();
    setToneOn(false);
    wsRef.current?.toggleTone(false);
  }, [gamma]);

  const requestStimulation = useCallback(
    (kind: "tone" | "flicker") => {
      if (!consented) {
        pendingRef.current = kind;
        setConsentOpen(true);
        return;
      }
      if (kind === "tone") enableTone();
      else setFlickerOn(true);
    },
    [consented, enableTone],
  );

  const toggleTone = useCallback(() => {
    if (toneOn) disableTone();
    else requestStimulation("tone");
  }, [toneOn, disableTone, requestStimulation]);

  const toggleFlicker = useCallback(() => {
    if (flickerOn) setFlickerOn(false);
    else requestStimulation("flicker");
  }, [flickerOn, requestStimulation]);

  const acceptConsent = useCallback(() => {
    setConsented(true);
    setConsentOpen(false);
    const kind = pendingRef.current;
    pendingRef.current = null;
    if (kind === "tone") enableTone();
    else if (kind === "flicker") setFlickerOn(true);
  }, [enableTone]);

  const declineConsent = useCallback(() => {
    setConsentOpen(false);
    pendingRef.current = null;
  }, []);

  // Master OFF: kill all stimulation immediately.
  const stopAllStimulation = useCallback(() => {
    disableTone();
    setFlickerOn(false);
  }, [disableTone]);

  const anyStimulation = toneOn || flickerOn;

  const headerBadge = useMemo(
    () => `${stage}단계 · ${stageLabel(stage)}  ·  힌트 ${hintLevel}/4`,
    [stage, hintLevel],
  );

  // ---- Render -----------------------------------------------------------

  return (
    <div className="min-h-screen bg-gradient-to-br from-orange-50 via-rose-50 to-amber-50 p-4 md:p-6">
      <div className="mx-auto max-w-7xl">
        {/* Header */}
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-stone-800">
              메모리 리듬 — 환자 모드
            </h1>
            <p className="text-sm text-stone-500">
              수화기로 대화하면 떠올린 기억이 자서전이 됩니다.
            </p>
          </div>
          <span className="rounded-full bg-indigo-100 px-4 py-2 text-sm font-semibold text-indigo-700">
            {headerBadge}
          </span>
        </div>

        {/* Split screen */}
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          {/* LEFT: Handset + chat + reasoning */}
          <div className="flex flex-col gap-5">
            <Handset
              connected={connected}
              inCall={inCall}
              onCall={startCall}
              toneOn={toneOn}
              onToggleTone={toggleTone}
              onTranscript={(t) => sendText(t)}
            />

            {/* Chat transcript */}
            <div className="flex flex-col rounded-2xl border border-stone-200 bg-white p-4 shadow-sm">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-bold text-stone-700">대화</h3>
                <button
                  type="button"
                  onClick={toggleFlicker}
                  className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                    flickerOn
                      ? "bg-amber-500 text-white"
                      : "bg-amber-50 text-amber-700 ring-1 ring-amber-300"
                  }`}
                >
                  {flickerOn ? "전자책 백라이트 켜짐" : "40Hz 백라이트"}
                </button>
              </div>

              <div className="h-56 space-y-2 overflow-y-auto pr-1">
                {messages.length === 0 && (
                  <p className="py-6 text-center text-sm text-stone-400">
                    "📞 통화 시작"을 누르고 대화를 시작해 보세요.
                  </p>
                )}
                {messages.map((m, i) => (
                  <ChatBubble key={i} line={m} />
                ))}
                <div ref={chatEndRef} />
              </div>

              {/* Quick replies for the scripted demo */}
              <div className="mt-3 flex flex-wrap gap-2">
                {QUICK_REPLIES.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => sendText(q)}
                    className="rounded-full bg-rose-50 px-3 py-1.5 text-xs font-medium text-rose-700 ring-1 ring-rose-200 transition hover:bg-rose-100"
                  >
                    {q}
                  </button>
                ))}
              </div>

              {/* Typed input */}
              <form
                className="mt-3 flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  sendText(input);
                }}
              >
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="여기에 말을 입력하세요…"
                  className="flex-1 rounded-xl border border-stone-300 px-4 py-3 text-base focus:border-rose-400 focus:outline-none"
                />
                <button
                  type="submit"
                  className="rounded-xl bg-rose-500 px-6 py-3 text-base font-bold text-white transition hover:bg-rose-600"
                >
                  보내기
                </button>
              </form>

              {/* Time-acceleration (forgetting-curve demo) */}
              <div className="mt-3 flex items-center gap-2">
                <span className="text-xs font-semibold text-stone-500">
                  시간 가속:
                </span>
                {[1, 3, 7, 21].map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => advanceTime(d)}
                    className="rounded-lg bg-stone-100 px-3 py-1.5 text-xs font-semibold text-stone-600 transition hover:bg-stone-200"
                  >
                    +{d}일
                  </button>
                ))}
              </div>
            </div>

            <div className="h-72">
              <ReasoningPanel log={reasoningLog} />
            </div>
          </div>

          {/* RIGHT: Ebook */}
          <div className="lg:sticky lg:top-6">
            <div className="h-[calc(100vh-3rem)] min-h-[520px] rounded-3xl border border-stone-200 bg-white p-5 shadow-sm">
              <Ebook pages={pages} flicker={flickerOn} />
            </div>
          </div>
        </div>
      </div>

      {/* Safety: consent modal + always-visible OFF bar */}
      <SafetyNotice
        open={consentOpen}
        onAccept={acceptConsent}
        onDecline={declineConsent}
      />
      <StimulationOffBar active={anyStimulation} onOff={stopAllStimulation} />
    </div>
  );
}

function ChatBubble({ line }: { line: ChatLine }) {
  if (line.role === "system") {
    return (
      <div className="my-1 text-center text-xs font-medium text-stone-400">
        {line.text}
      </div>
    );
  }
  const isUser = line.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2 text-[15px] leading-relaxed ${
          isUser
            ? "bg-rose-500 text-white"
            : "bg-stone-100 text-stone-800"
        }`}
      >
        {line.text}
        {!isUser && line.hintLevel !== undefined && line.hintLevel > 0 && (
          <span className="mt-1 block text-[10px] font-semibold text-indigo-500">
            힌트 레벨 {line.hintLevel}
          </span>
        )}
      </div>
    </div>
  );
}
