import { useEffect, useState } from "react";

const DAYS = ["일", "월", "화", "수", "목", "금", "토"];

export interface ClockOptions {
  /** Include the year in the date string (e.g. "2026년 6월 8일 …"). */
  withYear?: boolean;
  /** Tick interval in ms (default 10s — enough for a minute-resolution clock). */
  intervalMs?: number;
}

/**
 * Live Korean date/time strings, shared by the patient + landing screens.
 *
 * Returns ``{ time: "오후 3시 07분", date: "6월 8일 일요일" }`` (with the year
 * prefixed when ``withYear`` is set).
 */
export function useClock(
  options: ClockOptions = {},
): { time: string; date: string } {
  const { withYear = false, intervalMs = 10000 } = options;
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);

  const hh = now.getHours();
  const ampm = hh < 12 ? "오전" : "오후";
  const h12 = ((hh + 11) % 12) + 1;
  const mm = String(now.getMinutes()).padStart(2, "0");
  const year = withYear ? `${now.getFullYear()}년 ` : "";
  return {
    time: `${ampm} ${h12}시 ${mm}분`,
    date: `${year}${now.getMonth() + 1}월 ${now.getDate()}일 ${DAYS[now.getDay()]}요일`,
  };
}
