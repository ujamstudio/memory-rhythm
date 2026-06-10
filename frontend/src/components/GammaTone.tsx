// GammaTone — 40Hz gamma-frequency tone generator via the Web Audio API.
//
// Research context: 40Hz auditory/visual stimulation ("gamma entrainment") is
// being studied as a non-invasive intervention for Alzheimer's. Here it is a
// DEMO effect only. Audio is volume-capped and only ever runs after the user
// has accepted the photosensitive-seizure consent gate (see SafetyNotice).

import { useEffect, useRef, useCallback } from "react";
import type { RefObject } from "react";

// 40 Hz gamma frequency. Hard volume cap to keep the tone gentle for elderly users.
const GAMMA_HZ = 40;
const MAX_GAIN = 0.06; // never exceed this — safety cap
const RAMP_SEC = 0.15; // soft fade in/out to avoid clicks

// Visual flicker brightness envelope (ring opacity swings between these).
const RING_MIN = 0.16;
const RING_MAX = 0.5;

export interface GammaToneController {
  /** Start (or resume) the 40Hz tone + synced visual flicker. No-op if playing. */
  start: () => void;
  /** Stop the tone + flicker and release the oscillator. */
  stop: () => void;
  /**
   * Attach the visual "gamma ring" element. Its opacity is modulated every
   * animation frame from the SAME AudioContext clock that drives the tone, so
   * the light flicker is phase-locked to the 40Hz audio (true gamma sync —
   * unlike a free-running CSS keyframe, which drifts and can't hit 40Hz).
   */
  ringRef: RefObject<HTMLElement | null>;
}

/**
 * useGammaTone — imperative controller for a single 40Hz oscillator.
 *
 * The AudioContext is created lazily on first start() (a user-gesture is
 * required by browsers to allow audio). stop() ramps the gain down and tears
 * down the oscillator so repeated start/stop cycles stay clean.
 */
export function useGammaTone(): GammaToneController {
  const ctxRef = useRef<AudioContext | null>(null);
  const oscRef = useRef<OscillatorNode | null>(null);
  const gainRef = useRef<GainNode | null>(null);
  const ringRef = useRef<HTMLElement | null>(null);
  const rafRef = useRef<number | null>(null);

  // Drive the ring opacity from the audio clock so light + tone share one 40Hz
  // phase. Respects prefers-reduced-motion (holds a steady glow, no flicker).
  const startFlicker = useCallback(() => {
    if (rafRef.current != null) return;
    const reduceMotion =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const tick = () => {
      const ctx = ctxRef.current;
      const ring = ringRef.current;
      if (ring && ctx) {
        if (reduceMotion) {
          ring.style.opacity = String((RING_MIN + RING_MAX) / 2);
        } else {
          // 0..1 sinusoid at 40Hz off the audio clock; sampled per frame.
          const phase = 0.5 + 0.5 * Math.sin(2 * Math.PI * GAMMA_HZ * ctx.currentTime);
          ring.style.opacity = String(RING_MIN + (RING_MAX - RING_MIN) * phase);
        }
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, []);

  const stopFlicker = useCallback(() => {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (ringRef.current) ringRef.current.style.opacity = "0";
  }, []);

  const ensureContext = useCallback((): AudioContext => {
    if (!ctxRef.current) {
      const AC =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext })
          .webkitAudioContext;
      ctxRef.current = new AC();
    }
    return ctxRef.current;
  }, []);

  const start = useCallback(() => {
    const ctx = ensureContext();
    // Browsers may suspend the context until a user gesture; resume on start.
    if (ctx.state === "suspended") void ctx.resume();
    if (oscRef.current) return; // already playing

    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(GAMMA_HZ, ctx.currentTime);

    // Soft fade-in to the capped gain.
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(
      MAX_GAIN,
      ctx.currentTime + RAMP_SEC,
    );

    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();

    oscRef.current = osc;
    gainRef.current = gain;
    startFlicker(); // visual ring, phase-locked to this oscillator's clock
  }, [ensureContext, startFlicker]);

  const stop = useCallback(() => {
    stopFlicker();
    const ctx = ctxRef.current;
    const osc = oscRef.current;
    const gain = gainRef.current;
    if (!ctx || !osc || !gain) return;

    const now = ctx.currentTime;
    try {
      gain.gain.cancelScheduledValues(now);
      gain.gain.setValueAtTime(Math.max(gain.gain.value, 0.0001), now);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + RAMP_SEC);
      osc.stop(now + RAMP_SEC + 0.02);
    } catch {
      // oscillator may already be stopped; ignore.
    }
    oscRef.current = null;
    gainRef.current = null;
  }, [stopFlicker]);

  // Clean up on unmount so the tone never lingers.
  useEffect(() => {
    return () => {
      stop();
      const ctx = ctxRef.current;
      if (ctx && ctx.state !== "closed") {
        void ctx.close();
      }
      ctxRef.current = null;
    };
  }, [stop]);

  return { start, stop, ringRef };
}

export default useGammaTone;
