// Handset — the D1 phone-handset UI.
//
// A warm retro telephone for elderly users: a visual 8-step dial, a big 통화
// (call) button to start the session, a mic button (getUserMedia -> /api/stt,
// with graceful fallback to typed input), and a 40Hz tone toggle gated behind
// the photosensitive consent (SafetyNotice).

import { useEffect, useRef, useState } from "react";

interface HandsetProps {
  connected: boolean;
  inCall: boolean;
  /** Start the session (sends start_session over WS). */
  onCall: () => void;
  /** 40Hz tone state + toggle (toggle is consent-gated by the parent). */
  toneOn: boolean;
  onToggleTone: () => void;
  /**
   * Receive transcribed text from the mic. The parent decides whether to send
   * it. If STT is unavailable, the mic gracefully degrades (returns null).
   */
  onTranscript: (text: string) => void;
}

// Visual 8-step dial — purely decorative ring of "memory dial" digits.
const DIAL_STEPS = ["1", "2", "3", "4", "5", "6", "7", "8"];

export function Handset({
  connected,
  inCall,
  onCall,
  toneOn,
  onToggleTone,
  onTranscript,
}: HandsetProps) {
  const [recording, setRecording] = useState(false);
  const [sttError, setSttError] = useState<string | null>(null);
  const [activeStep, setActiveStep] = useState(0);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  // Animate the dial ring while in a call (visual "rhythm" cue).
  useEffect(() => {
    if (!inCall) {
      setActiveStep(0);
      return;
    }
    const t = setInterval(
      () => setActiveStep((s) => (s + 1) % DIAL_STEPS.length),
      650,
    );
    return () => clearInterval(t);
  }, [inCall]);

  async function startRecording() {
    setSttError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      chunksRef.current = [];
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        await sendToStt(blob);
      };
      rec.start();
      mediaRef.current = rec;
      setRecording(true);
    } catch {
      // Mic permission denied or unsupported -> graceful fallback to typing.
      setSttError("마이크를 사용할 수 없습니다. 아래에 직접 입력해 주세요.");
      setRecording(false);
    }
  }

  function stopRecording() {
    mediaRef.current?.stop();
    mediaRef.current = null;
    setRecording(false);
  }

  // POST the recorded audio to /api/stt. We use a raw fetch here (multipart)
  // so the Handset stays self-contained; the proxy forwards /api -> backend.
  async function sendToStt(blob: Blob) {
    try {
      const form = new FormData();
      form.append("audio", blob, "speech.webm");
      const res = await fetch("/api/stt", { method: "POST", body: form });
      if (!res.ok) throw new Error("stt failed");
      const data = (await res.json()) as { text: string };
      if (data.text) onTranscript(data.text);
      else setSttError("음성을 인식하지 못했습니다. 직접 입력해 주세요.");
    } catch {
      setSttError("음성 인식을 사용할 수 없습니다. 직접 입력해 주세요.");
    }
  }

  return (
    <div className="rounded-3xl border-4 border-rose-200 bg-gradient-to-b from-rose-50 to-orange-50 p-5 shadow-md">
      <div className="mb-4 flex items-center gap-2">
        <span className="text-2xl" aria-hidden>
          ☎️
        </span>
        <h2 className="text-lg font-bold text-stone-800">기억의 수화기</h2>
        <span
          className={`ml-auto inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${
            connected
              ? "bg-emerald-100 text-emerald-700"
              : "bg-stone-200 text-stone-500"
          }`}
        >
          <span
            className={`h-2 w-2 rounded-full ${
              connected ? "bg-emerald-500" : "bg-stone-400"
            }`}
          />
          {connected ? "연결됨" : "연결 안 됨"}
        </span>
      </div>

      {/* Visual 8-step dial ring. */}
      <div className="relative mx-auto mb-5 h-40 w-40">
        <div className="absolute inset-0 rounded-full border-8 border-rose-100" />
        {DIAL_STEPS.map((label, i) => {
          const angle = (i / DIAL_STEPS.length) * 2 * Math.PI - Math.PI / 2;
          const r = 62;
          const x = 80 + r * Math.cos(angle);
          const y = 80 + r * Math.sin(angle);
          const active = inCall && i === activeStep;
          return (
            <div
              key={i}
              style={{ left: x, top: y }}
              className={`absolute flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full text-sm font-bold transition ${
                active
                  ? "scale-125 bg-rose-500 text-white shadow"
                  : "bg-white text-rose-400 shadow-sm"
              }`}
            >
              {label}
            </div>
          );
        })}
        <div className="absolute left-1/2 top-1/2 flex h-16 w-16 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-rose-400 text-2xl text-white shadow-inner">
          {inCall ? "🎙️" : "📞"}
        </div>
      </div>

      {/* Call button. */}
      <button
        type="button"
        onClick={onCall}
        disabled={inCall}
        className={`w-full rounded-2xl py-4 text-lg font-bold text-white shadow transition ${
          inCall
            ? "cursor-default bg-emerald-500"
            : "bg-rose-500 hover:bg-rose-600"
        }`}
      >
        {inCall ? "통화 중…" : "📞 통화 시작"}
      </button>

      {/* Mic + tone controls. */}
      <div className="mt-3 grid grid-cols-2 gap-3">
        <button
          type="button"
          onClick={recording ? stopRecording : startRecording}
          disabled={!inCall}
          className={`flex items-center justify-center gap-2 rounded-2xl py-3 text-base font-semibold transition disabled:opacity-40 ${
            recording
              ? "bg-red-500 text-white"
              : "bg-white text-rose-600 ring-1 ring-rose-300 hover:bg-rose-50"
          }`}
        >
          {recording ? "■ 녹음 중지" : "🎤 음성 말하기"}
        </button>

        <button
          type="button"
          onClick={onToggleTone}
          className={`flex items-center justify-center gap-2 rounded-2xl py-3 text-base font-semibold transition ${
            toneOn
              ? "bg-amber-500 text-white"
              : "bg-white text-amber-600 ring-1 ring-amber-300 hover:bg-amber-50"
          }`}
        >
          {toneOn ? "🔊 40Hz 켜짐" : "🔈 40Hz 음향"}
        </button>
      </div>

      {sttError && (
        <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-center text-sm text-amber-700">
          {sttError}
        </p>
      )}
    </div>
  );
}

export default Handset;
