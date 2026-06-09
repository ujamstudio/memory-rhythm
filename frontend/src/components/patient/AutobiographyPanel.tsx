import { useEffect, useState } from "react";
import type { AutobiographyPage } from "../../protocol";

/** The 자서전 picture-book panel (right column on desktop) — newest page first. */
export function AutobiographyPanel({ pages }: { pages: AutobiographyPage[] }) {
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    if (pages.length > 0) setIdx(pages.length - 1);
  }, [pages.length]);
  const clamped = Math.min(idx, Math.max(0, pages.length - 1));
  const page = pages[clamped];

  return (
    <div className="flex h-[42%] min-h-0 flex-col rounded-2xl border border-[#E7D7C0] bg-[#FCF8F1]/90 shadow-sm">
      <div className="flex items-center justify-between border-b border-[#E7D7C0] px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-lg" aria-hidden>
            📖
          </span>
          <h3 className="text-sm font-bold text-[#6E4A2A]">나의 자서전</h3>
        </div>
        {pages.length > 0 && (
          <span className="rounded-full bg-[#E7D7C0] px-2 py-0.5 text-xs font-semibold text-[#6E4A2A]">
            {clamped + 1} / {pages.length}
          </span>
        )}
      </div>
      <div className="flex flex-1 flex-col overflow-hidden p-3">
        {!page ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 px-4 text-center">
            <span className="text-4xl opacity-40" aria-hidden>
              🕰️
            </span>
            <p className="text-xs leading-relaxed text-[#9A8A74]">
              옛 기억을 떠올리면 그 순간이 한 페이지의
              <br /> 그림과 이야기로 이곳에 남습니다.
            </p>
          </div>
        ) : (
          <>
            <div className="relative min-h-0 flex-1 overflow-hidden rounded-xl bg-[#efe5d2]">
              <img
                src={page.image_url}
                alt={`자서전 ${page.order_idx + 1}페이지`}
                className="h-full w-full object-cover"
                onError={(e) => {
                  (e.currentTarget as HTMLImageElement).style.display = "none";
                }}
              />
            </div>
            <p className="mt-2 line-clamp-2 text-[13px] leading-snug text-[#4a3520]">
              {page.narrative}
            </p>
            {pages.length > 1 && (
              <div className="mt-2 flex justify-center gap-1.5">
                {pages.map((_, i) => (
                  <button
                    key={i}
                    type="button"
                    aria-label={`${i + 1}페이지`}
                    onClick={() => setIdx(i)}
                    className={`h-2 w-2 rounded-full transition ${
                      i === clamped ? "bg-[#C67537]" : "bg-[#D8C5A8]"
                    }`}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
