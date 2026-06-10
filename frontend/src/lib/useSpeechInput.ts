// useSpeechInput — a small wrapper around the browser Web Speech API (Korean),
// shared by the patient session and the survey so both screens get the same
// voice-first behaviour and the same cross-browser quirks handled in one place.
//
// Quirks baked in (learned on the patient screen):
//   - interimResults MUST be on, or Safari/webkit never fires onresult and the
//     mic looks stuck on "듣는 중".
//   - Loop ALL results and split final/interim by `isFinal` (Safari indexes
//     differently than Chrome) rather than assuming results[0].
//   - Send on `onend`, not on a final onresult — Safari fires onend reliably but
//     the final onresult is flaky; fall back to the last interim transcript.
//   - The API only runs in a secure context (https:// or localhost); on plain
//     http it throws / is not-allowed, so we surface that distinctly.
//
// Callbacks are read through a ref so `start`/`stop` stay referentially stable
// (empty deps) while always seeing the latest handlers.
import { useCallback, useEffect, useRef, useState } from "react";

export interface SpeechInputCallbacks {
  /** Recognition language tag (default "ko-KR"). */
  lang?: string;
  /** Live transcript while the user is still speaking. */
  onInterim?: (text: string) => void;
  /** Final recognized text (fired once, on end). */
  onFinal: (text: string) => void;
  /** Ended with no transcript at all ("잘 못 들었어요"). */
  onUnheard?: () => void;
  /** Microphone permission denied / blocked. */
  onBlocked?: () => void;
  /** Not a secure context (plain http) — voice can't run. */
  onInsecure?: () => void;
  /** Browser has no SpeechRecognition, or start() threw. */
  onUnsupported?: () => void;
}

export function useSpeechInput(cb: SpeechInputCallbacks) {
  const [listening, setListening] = useState(false);
  const recRef = useRef<any>(null);
  const cbRef = useRef(cb);
  cbRef.current = cb;

  const start = useCallback(() => {
    const SR =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;
    if (!window.isSecureContext) {
      cbRef.current.onInsecure?.();
      return;
    }
    if (!SR) {
      cbRef.current.onUnsupported?.();
      return;
    }
    try {
      const rec = new SR();
      rec.lang = cbRef.current.lang || "ko-KR";
      rec.continuous = false;
      rec.interimResults = true;
      rec.maxAlternatives = 1;

      let finalText = "";
      let lastInterim = "";
      let errored = "";

      rec.onresult = (e: any) => {
        let interim = "";
        for (let i = e.resultIndex ?? 0; i < e.results.length; i++) {
          const r = e.results[i];
          const t = r?.[0]?.transcript ?? "";
          if (r?.isFinal) finalText += t;
          else interim += t;
        }
        lastInterim = interim;
        cbRef.current.onInterim?.((finalText + interim).trim());
      };
      rec.onerror = (e: any) => {
        errored = e?.error || "error";
      };
      rec.onend = () => {
        setListening(false);
        const text = (finalText || lastInterim).trim();
        finalText = "";
        lastInterim = "";
        if (text) {
          cbRef.current.onFinal(text);
          return;
        }
        if (errored === "not-allowed" || errored === "service-not-allowed") {
          cbRef.current.onBlocked?.();
        } else {
          cbRef.current.onUnheard?.();
        }
      };

      recRef.current = rec;
      setListening(true);
      rec.start();
    } catch {
      cbRef.current.onUnsupported?.();
    }
  }, []);

  const stop = useCallback(() => {
    try {
      recRef.current?.stop();
    } catch {
      /* ignore */
    }
    setListening(false);
  }, []);

  // Stop any in-flight recognition on unmount.
  useEffect(
    () => () => {
      try {
        recRef.current?.stop();
      } catch {
        /* ignore */
      }
    },
    [],
  );

  return { listening, start, stop };
}
