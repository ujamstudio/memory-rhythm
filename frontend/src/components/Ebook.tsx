// Ebook — the D2 autobiography picture-book panel.
//
// Renders AutobiographyPage[] as a flipping picture book. Each recalled memory
// becomes a page (image_url + Korean narrative). A toggleable 40Hz backlight
// flicker (CSS class `gamma-flicker` from index.css) simulates the e-book's
// gamma-stimulation backlight; it is gated behind the photosensitive consent.

import { useEffect, useState } from "react";
import type { AutobiographyPage } from "../protocol";

interface EbookProps {
  pages: AutobiographyPage[];
  /** Whether the 40Hz backlight flicker effect is active (consent-gated). */
  flicker: boolean;
}

export function Ebook({ pages, flicker }: EbookProps) {
  const [idx, setIdx] = useState(0);

  // When a new page is added, jump to it so the demo shows the fresh recall.
  useEffect(() => {
    if (pages.length > 0) setIdx(pages.length - 1);
  }, [pages.length]);

  const clamped = Math.min(idx, Math.max(0, pages.length - 1));
  const page = pages[clamped];
  const hasPages = pages.length > 0;

  return (
    <div className="flex h-full flex-col">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-2xl" aria-hidden>
            📖
          </span>
          <h2 className="text-lg font-bold text-stone-800">나의 자서전</h2>
        </div>
        {flicker && (
          <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-700">
            40Hz 백라이트 작동중
          </span>
        )}
      </div>

      {/* The "book". The flicker class only applies when consent-gated flicker is on. */}
      <div
        className={`relative flex flex-1 flex-col overflow-hidden rounded-3xl border-4 border-amber-200 bg-amber-50 shadow-inner ${
          flicker ? "gamma-flicker" : ""
        }`}
      >
        {!hasPages && (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
            <span className="text-5xl opacity-40" aria-hidden>
              🕰️
            </span>
            <p className="text-stone-500">
              아직 기록된 기억이 없습니다.
            </p>
            <p className="max-w-xs text-sm text-stone-400">
              왼쪽 수화기로 통화를 시작하고 옛 기억을 떠올리면,
              그 순간이 한 페이지의 그림과 이야기로 이곳에 남습니다.
            </p>
          </div>
        )}

        {hasPages && page && (
          <>
            <div className="relative flex-1 overflow-hidden bg-stone-100">
              {/* image_url may be a data: URI (mock) or remote URL (openai). */}
              <img
                src={page.image_url}
                alt={`자서전 ${page.order_idx + 1}페이지`}
                className="h-full w-full object-cover"
                onError={(e) => {
                  // Graceful fallback if the image fails to load.
                  (e.currentTarget as HTMLImageElement).style.display = "none";
                }}
              />
              <span className="absolute right-3 top-3 rounded-full bg-black/40 px-2 py-1 text-xs font-medium text-white">
                {clamped + 1} / {pages.length}
              </span>
            </div>

            <div className="bg-amber-50/90 px-6 py-4">
              <p className="text-[15px] leading-relaxed text-stone-800">
                {page.narrative}
              </p>
            </div>
          </>
        )}
      </div>

      {/* Page navigation. */}
      {hasPages && (
        <div className="mt-3 flex items-center justify-center gap-4">
          <button
            type="button"
            onClick={() => setIdx((i) => Math.max(0, i - 1))}
            disabled={clamped === 0}
            className="rounded-xl border border-stone-300 px-5 py-2 text-base font-semibold text-stone-600 transition hover:bg-stone-100 disabled:opacity-40"
          >
            ◀ 이전
          </button>
          <div className="flex gap-1.5">
            {pages.map((_, i) => (
              <button
                key={i}
                type="button"
                aria-label={`${i + 1}페이지로 이동`}
                onClick={() => setIdx(i)}
                className={`h-2.5 w-2.5 rounded-full transition ${
                  i === clamped ? "bg-amber-600" : "bg-stone-300"
                }`}
              />
            ))}
          </div>
          <button
            type="button"
            onClick={() =>
              setIdx((i) => Math.min(pages.length - 1, i + 1))
            }
            disabled={clamped >= pages.length - 1}
            className="rounded-xl border border-stone-300 px-5 py-2 text-base font-semibold text-stone-600 transition hover:bg-stone-100 disabled:opacity-40"
          >
            다음 ▶
          </button>
        </div>
      )}
    </div>
  );
}

export default Ebook;
