// SafetyNotice — Korean 광과민성(photosensitive) seizure warning + consent gate.
//
// The 40Hz gamma tone and the e-book backlight flicker are gated behind this
// consent modal (plan §11). Tone/flicker stay OFF until the user explicitly
// accepts. An always-visible OFF affordance is rendered alongside whenever any
// stimulation is active.

import { useState } from "react";

interface SafetyNoticeProps {
  /** Whether the consent modal is open. */
  open: boolean;
  /** User accepted the warning -> enable stimulation features. */
  onAccept: () => void;
  /** User declined / closed without accepting. */
  onDecline: () => void;
}

/**
 * Consent modal shown before any 40Hz stimulation is allowed.
 * Renders nothing when `open` is false.
 */
export function SafetyNotice({ open, onAccept, onDecline }: SafetyNoticeProps) {
  const [checked, setChecked] = useState(false);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="safety-title"
    >
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
        <div className="mb-4 flex items-center gap-3">
          <span className="text-3xl" aria-hidden>
            ⚠️
          </span>
          <h2
            id="safety-title"
            className="text-xl font-bold text-amber-700"
          >
            광과민성 발작 주의 안내
          </h2>
        </div>

        <div className="space-y-3 text-base leading-relaxed text-stone-700">
          <p>
            이 기능은 <strong>40Hz 감마 자극(소리·화면 깜빡임)</strong>을
            사용합니다. 매우 드물게 빛이나 깜빡임에 민감한 분께
            <strong> 발작이나 어지럼증</strong>을 유발할 수 있습니다.
          </p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-stone-600">
            <li>과거 광과민성 발작·뇌전증 병력이 있으신 분은 사용을 피해 주세요.</li>
            <li>불편함(두통·어지럼·시야 이상)이 느껴지면 즉시 꺼 주세요.</li>
            <li>본 데모의 자극은 안전을 위해 음량·밝기를 낮게 제한합니다.</li>
            <li>의료 행위가 아닌 시연용 효과이며, 의학적 효능을 보장하지 않습니다.</li>
          </ul>
        </div>

        <label className="mt-5 flex cursor-pointer items-start gap-2 text-sm text-stone-700">
          <input
            type="checkbox"
            className="mt-1 h-5 w-5 accent-amber-600"
            checked={checked}
            onChange={(e) => setChecked(e.target.checked)}
          />
          <span>위 주의사항을 읽고 이해했으며, 자극 기능 사용에 동의합니다.</span>
        </label>

        <div className="mt-6 flex gap-3">
          <button
            type="button"
            onClick={onDecline}
            className="flex-1 rounded-xl border border-stone-300 px-4 py-3 text-base font-semibold text-stone-600 transition hover:bg-stone-100"
          >
            사용 안 함
          </button>
          <button
            type="button"
            disabled={!checked}
            onClick={onAccept}
            className="flex-1 rounded-xl bg-amber-600 px-4 py-3 text-base font-semibold text-white transition hover:bg-amber-700 disabled:cursor-not-allowed disabled:bg-stone-300"
          >
            동의하고 켜기
          </button>
        </div>
      </div>
    </div>
  );
}

interface StimulationOffBarProps {
  /** True when any 40Hz stimulation (tone or flicker) is currently active. */
  active: boolean;
  /** Turn everything off immediately. */
  onOff: () => void;
}

/**
 * Always-visible emergency OFF affordance. Shown whenever stimulation is on so
 * the user can stop it instantly at any time.
 */
export function StimulationOffBar({ active, onOff }: StimulationOffBarProps) {
  if (!active) return null;
  return (
    <div className="fixed bottom-4 left-1/2 z-40 -translate-x-1/2">
      <button
        type="button"
        onClick={onOff}
        className="flex items-center gap-2 rounded-full bg-red-600 px-6 py-3 text-base font-bold text-white shadow-lg ring-2 ring-red-300 transition hover:bg-red-700"
      >
        <span aria-hidden>⏹</span> 40Hz 자극 모두 끄기
      </button>
    </div>
  );
}

export default SafetyNotice;
