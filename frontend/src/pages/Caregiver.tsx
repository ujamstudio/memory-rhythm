import { useState, useEffect, useRef } from "react";
import {
  useGetTodaySummary,
  useGetCurrentPhase,
  useGetTimeline,
} from "@workspace/api-client-react";
import { Link } from "wouter";
import { motion, AnimatePresence } from "framer-motion";
import { format } from "date-fns";
import { ko } from "date-fns/locale";

/* ── SSE notifications ── */
type NotifType = "hint" | "session" | "mission";
interface Notif {
  id: string;
  type: NotifType;
  message: string;
  sub: string;
  at: string;
  ts: number;
}

const NOTIF_META: Record<NotifType, { icon: string; bg: string; fg: string; bar: string }> = {
  hint:    { icon: "💡", bg: "#FFFBE6", fg: "#9a7000", bar: "#FFD700" },
  session: { icon: "📱", bg: "#EBF3FF", fg: "#2255cc", bar: "#5599ff" },
  mission: { icon: "🎯", bg: "#EDFBEE", fg: "#2d8e36", bar: "#44cc55" },
};

function useNotifications() {
  const [notifs, setNotifs] = useState<Notif[]>([]);
  const [newNotif, setNewNotif] = useState<Notif | null>(null);

  useEffect(() => {
    const base = (import.meta.env.BASE_URL as string).replace(/\/$/, "");
    let es: EventSource;
    let retryTimer: ReturnType<typeof setTimeout>;

    function connect() {
      es = new EventSource(`${base}/api/events/stream`);

      const addNotif = (n: Notif) => {
        setNotifs((prev) => [n, ...prev].slice(0, 20));
        setNewNotif(n);
        setTimeout(() => setNewNotif(null), 6000);
      };

      es.addEventListener("hint", (e) => {
        const d = JSON.parse(e.data) as { level: number; content: string; at: string };
        addNotif({
          id: crypto.randomUUID(),
          type: "hint",
          message: `힌트 레벨 ${d.level} 요청됨`,
          sub: d.content,
          at: format(new Date(d.at), "a h:mm", { locale: ko }),
          ts: Date.now(),
        });
      });

      es.addEventListener("session_started", (e) => {
        const d = JSON.parse(e.data) as { patientName: string; at: string };
        addNotif({
          id: crypto.randomUUID(),
          type: "session",
          message: `${d.patientName} 세션 시작됨`,
          sub: "환자가 오늘의 대화를 시작했어요",
          at: format(new Date(d.at), "a h:mm", { locale: ko }),
          ts: Date.now(),
        });
      });

      es.onerror = () => {
        es.close();
        retryTimer = setTimeout(connect, 5000);
      };
    }

    connect();
    return () => {
      es?.close();
      clearTimeout(retryTimer);
    };
  }, []);

  const dismiss = (id: string) => setNotifs((prev) => prev.filter((n) => n.id !== id));
  const clearAll = () => setNotifs([]);

  return { notifs, newNotif, dismiss, clearAll };
}

/* ── Stat card ── */
function StatCard({ icon, label, value, unit, accent }: {
  icon: string; label: string; value: number | string; unit?: string; accent: string;
}) {
  return (
    <div style={{
      background: "white",
      borderRadius: "20px",
      padding: "24px 28px",
      boxShadow: "0 2px 12px rgba(51,41,31,0.07)",
      border: "1px solid rgba(198,117,55,0.12)",
      display: "flex",
      flexDirection: "column",
      gap: "10px",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
        <span style={{ fontSize: "22px" }}>{icon}</span>
        <span style={{ fontSize: "14px", fontWeight: 700, color: "#6E6051" }}>{label}</span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: "5px" }}>
        <span style={{ fontSize: "38px", fontWeight: 900, color: "#33291F", lineHeight: 1 }}>{value}</span>
        {unit && <span style={{ fontSize: "17px", fontWeight: 600, color: "#9A6A3E" }}>{unit}</span>}
      </div>
      <div style={{ height: "3px", borderRadius: "99px", background: accent, opacity: 0.7 }} />
    </div>
  );
}

const PHASE_NAMES = ["기억 회상", "감각 자극", "인지 훈련", "일상 복귀"];

const EVENT_META: Record<string, { icon: string; label: string; bg: string; fg: string }> = {
  ai_message:       { icon: "💬", label: "AI 발화",   bg: "#EBF3FF", fg: "#3b7dd8" },
  patient_response: { icon: "🗣",  label: "환자 응답", bg: "#FFF7E6", fg: "#b87a00" },
  hint_given:       { icon: "💡", label: "힌트 제공", bg: "#FFFBE6", fg: "#9a7000" },
  mission_success:  { icon: "✅", label: "미션 성공", bg: "#EDFBEE", fg: "#2d8e36" },
  mission_fail:     { icon: "❌", label: "미션 실패", bg: "#FFF0F0", fg: "#cc3333" },
};

export default function Caregiver() {
  const { data: summary, isLoading: loadingSummary } = useGetTodaySummary();
  const { data: phase, isLoading: loadingPhase } = useGetCurrentPhase();
  const { data: timeline, isLoading: loadingTimeline } = useGetTimeline();
  const { notifs, newNotif, dismiss, clearAll } = useNotifications();
  const notifPanelRef = useRef<HTMLDivElement>(null);

  const today = format(new Date(), "yyyy년 MM월 dd일 EEEE", { locale: ko });

  return (
    <div style={{ minHeight: "100dvh", background: "#F8F4EE", display: "flex", fontFamily: '"Gothic A1", sans-serif' }}>

      {/* ── Sidebar ── */}
      <aside style={{
        width: "260px",
        minHeight: "100dvh",
        background: "#33291F",
        display: "flex",
        flexDirection: "column",
        position: "sticky",
        top: 0,
        flexShrink: 0,
      }}>
        <div style={{ padding: "32px 28px 24px", borderBottom: "1px solid rgba(255,255,255,0.1)" }}>
          <div style={{ fontSize: "26px", marginBottom: "6px" }}>🧠</div>
          <div style={{ fontSize: "20px", fontWeight: 900, color: "#F4EBDD", letterSpacing: "-0.02em" }}>Memory Rhythm</div>
          <div style={{ fontSize: "12px", color: "#9A6A3E", fontWeight: 600, marginTop: "2px" }}>보호자 대시보드</div>
        </div>

        <div style={{ padding: "24px 28px", borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
          <div style={{ fontSize: "11px", fontWeight: 700, color: "#6E6051", letterSpacing: "0.08em", marginBottom: "12px" }}>현재 환자</div>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div style={{
              width: "44px", height: "44px", borderRadius: "50%",
              background: "linear-gradient(135deg, #C4A271, #9A6A3E)",
              display: "flex", alignItems: "center", justifyContent: "center", fontSize: "20px",
            }}>👵</div>
            <div>
              <div style={{ fontSize: "16px", fontWeight: 800, color: "#F4EBDD" }}>김순자</div>
              <div style={{ fontSize: "12px", color: "#9A6A3E", fontWeight: 600 }}>
                Phase {phase?.currentPhase ?? "–"} · {phase?.phaseName ?? "불러오는 중"}
              </div>
            </div>
          </div>
        </div>

        <nav style={{ padding: "16px 16px", flex: 1, display: "flex", flexDirection: "column", gap: "4px" }}>
          {[
            { icon: "📊", label: "오늘 현황", active: true },
            { icon: "📋", label: "대화 타임라인", active: false },
            { icon: "📈", label: "주간 리포트", active: false },
            { icon: "⚙️",  label: "설정", active: false },
          ].map((item) => (
            <div key={item.label} style={{
              display: "flex", alignItems: "center", gap: "12px",
              padding: "12px 16px", borderRadius: "12px",
              background: item.active ? "rgba(198,117,55,0.18)" : "transparent",
              color: item.active ? "#C67537" : "rgba(244,235,221,0.5)",
              fontSize: "15px", fontWeight: item.active ? 700 : 600,
            }}>
              <span style={{ fontSize: "18px" }}>{item.icon}</span>
              {item.label}
            </div>
          ))}
        </nav>

        {/* Live alerts badge in sidebar */}
        {notifs.length > 0 && (
          <div style={{ padding: "0 16px 8px" }}>
            <div style={{
              background: "rgba(198,117,55,0.15)",
              borderRadius: "12px",
              padding: "10px 14px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}>
              <span style={{ fontSize: "13px", color: "#C67537", fontWeight: 700 }}>
                🔔 알림 {notifs.length}건
              </span>
              <button onClick={clearAll} style={{
                background: "none", border: "none", cursor: "pointer",
                fontSize: "11px", color: "rgba(198,117,55,0.7)", fontWeight: 600,
              }}>전체 지우기</button>
            </div>
          </div>
        )}

        <div style={{ padding: "20px 16px", borderTop: "1px solid rgba(255,255,255,0.08)" }}>
          <Link href="/">
            <div style={{
              display: "flex", alignItems: "center", gap: "10px",
              padding: "12px 16px", borderRadius: "12px", cursor: "pointer",
              color: "rgba(244,235,221,0.5)", fontSize: "14px", fontWeight: 600,
            }}>
              ← 홈으로
            </div>
          </Link>
        </div>
      </aside>

      {/* ── Main ── */}
      <main style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>

        {/* Header */}
        <header style={{
          background: "white",
          borderBottom: "1px solid rgba(198,117,55,0.14)",
          padding: "20px 36px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          position: "sticky",
          top: 0,
          zIndex: 20,
          boxShadow: "0 1px 8px rgba(51,41,31,0.06)",
        }}>
          <div>
            <h1 style={{ fontSize: "22px", fontWeight: 900, color: "#33291F", margin: 0 }}>오늘의 현황</h1>
            <p style={{ fontSize: "14px", color: "#9A6A3E", fontWeight: 600, margin: "3px 0 0" }}>{today}</p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div style={{
              display: "flex", alignItems: "center", gap: "8px",
              background: "#EDFBEE", color: "#2d8e36",
              padding: "8px 16px", borderRadius: "99px", fontSize: "13px", fontWeight: 700,
            }}>
              <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#2d8e36", display: "inline-block" }} />
              세션 진행 중
            </div>
            <Link href="/patient">
              <div style={{
                padding: "8px 16px", borderRadius: "99px",
                background: "linear-gradient(#D98040, #C67537)", color: "white",
                fontSize: "13px", fontWeight: 700, cursor: "pointer",
                boxShadow: "0 4px 0 #8a4a1f",
              }}>
                📱 환자 화면
              </div>
            </Link>
          </div>
        </header>

        {/* Content */}
        <div style={{ flex: 1, padding: "28px 36px", display: "flex", flexDirection: "column", gap: "28px", overflowY: "auto" }}>

          {/* ── LIVE NOTIFICATION PANEL ── */}
          <section>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
              <h2 style={{ fontSize: "16px", fontWeight: 700, color: "#6E6051", letterSpacing: "0.04em", margin: 0, textTransform: "uppercase", display: "flex", alignItems: "center", gap: "8px" }}>
                🔔 실시간 알림
                <span style={{
                  fontSize: "11px", background: notifs.length > 0 ? "#C67537" : "#D4BFA0",
                  color: "white", padding: "1px 7px", borderRadius: "99px", fontWeight: 800,
                }}>
                  {notifs.length}
                </span>
              </h2>
              {notifs.length > 0 && (
                <button onClick={clearAll} style={{
                  background: "none", border: "none", cursor: "pointer",
                  fontSize: "13px", color: "#9A6A3E", fontWeight: 600,
                }}>전체 지우기</button>
              )}
            </div>

            <div
              ref={notifPanelRef}
              style={{
                background: "white",
                borderRadius: "20px",
                border: "1px solid rgba(198,117,55,0.14)",
                boxShadow: "0 2px 12px rgba(51,41,31,0.06)",
                minHeight: "80px",
                maxHeight: "240px",
                overflowY: "auto",
                display: "flex",
                flexDirection: "column",
              }}
            >
              <AnimatePresence initial={false}>
                {notifs.length === 0 ? (
                  <motion.div
                    key="empty"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    style={{
                      flex: 1,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: "#C4A271",
                      fontSize: "15px",
                      fontWeight: 600,
                      padding: "28px",
                      gap: "10px",
                    }}
                  >
                    <span style={{ fontSize: "22px" }}>🔕</span>
                    환자 화면에서 활동이 생기면 여기에 표시됩니다
                  </motion.div>
                ) : (
                  notifs.map((n, i) => {
                    const meta = NOTIF_META[n.type];
                    return (
                      <motion.div
                        key={n.id}
                        initial={{ opacity: 0, x: -16, height: 0 }}
                        animate={{ opacity: 1, x: 0, height: "auto" }}
                        exit={{ opacity: 0, x: 16, height: 0 }}
                        transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "14px",
                          padding: "14px 18px",
                          borderBottom: i < notifs.length - 1 ? "1px solid rgba(198,117,55,0.10)" : "none",
                          borderLeft: `4px solid ${meta.bar}`,
                          background: i === 0 ? meta.bg : "white",
                          transition: "background 1s ease",
                          overflow: "hidden",
                        }}
                      >
                        <span style={{
                          fontSize: "24px",
                          flexShrink: 0,
                          width: "36px",
                          height: "36px",
                          borderRadius: "50%",
                          background: meta.bg,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                        }}>{meta.icon}</span>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: "15px", fontWeight: 700, color: "#33291F" }}>{n.message}</div>
                          <div style={{ fontSize: "13px", color: "#9A6A3E", fontWeight: 600, marginTop: "2px" }}>{n.sub}</div>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: "10px", flexShrink: 0 }}>
                          <span style={{ fontSize: "12px", color: "#C4A271", fontWeight: 600 }}>{n.at}</span>
                          <button onClick={() => dismiss(n.id)} style={{
                            background: "rgba(110,96,81,0.1)", border: "none", cursor: "pointer",
                            width: "24px", height: "24px", borderRadius: "50%",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            color: "#9A6A3E", fontSize: "14px", fontWeight: 700,
                          }}>×</button>
                        </div>
                      </motion.div>
                    );
                  })
                )}
              </AnimatePresence>
            </div>
          </section>

          {/* Phase Tracker */}
          <section>
            <h2 style={{ fontSize: "16px", fontWeight: 700, color: "#6E6051", letterSpacing: "0.04em", margin: "0 0 14px", textTransform: "uppercase" }}>인지 치료 단계</h2>
            {loadingPhase ? (
              <div style={{ height: "160px", background: "white", borderRadius: "20px" }} />
            ) : phase ? (
              <div style={{ background: "white", borderRadius: "20px", padding: "28px 32px", boxShadow: "0 2px 12px rgba(51,41,31,0.07)", border: "1px solid rgba(198,117,55,0.12)" }}>
                <div style={{ display: "flex", alignItems: "center", position: "relative", marginBottom: "24px" }}>
                  <div style={{ position: "absolute", top: "24px", left: "24px", right: "24px", height: "3px", background: "#F0E6D4", borderRadius: "99px", zIndex: 0 }} />
                  <div style={{ position: "absolute", top: "24px", left: "24px", width: `${((phase.currentPhase - 1) / 3) * 100}%`, height: "3px", background: "#C67537", borderRadius: "99px", zIndex: 1, transition: "width 1s ease" }} />
                  {[1, 2, 3, 4].map((step) => {
                    const isActive = phase.currentPhase === step;
                    const isPast = phase.currentPhase > step;
                    return (
                      <div key={step} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: "10px", position: "relative", zIndex: 2 }}>
                        <div style={{
                          width: "48px", height: "48px", borderRadius: "50%",
                          display: "flex", alignItems: "center", justifyContent: "center",
                          fontSize: "18px", fontWeight: 900,
                          background: isActive ? "#C67537" : isPast ? "#C4A271" : "#F0E6D4",
                          color: (isActive || isPast) ? "white" : "#9A6A3E",
                          boxShadow: isActive ? "0 4px 16px rgba(198,117,55,0.45), 0 0 0 4px rgba(198,117,55,0.15)" : "none",
                          transform: isActive ? "scale(1.15)" : "scale(1)",
                          transition: "all 0.3s ease",
                        }}>
                          {isPast ? "✓" : step}
                        </div>
                        <div style={{ textAlign: "center" }}>
                          <div style={{ fontSize: "12px", fontWeight: 700, color: isActive ? "#C67537" : "#9A6A3E" }}>Phase {step}</div>
                          <div style={{ fontSize: "13px", fontWeight: 700, color: isActive ? "#33291F" : "#9A6A3E", marginTop: "2px" }}>{PHASE_NAMES[step - 1]}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div style={{ background: "#F8F4EE", borderRadius: "14px", padding: "16px 20px", border: "1px solid rgba(198,117,55,0.12)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
                    <span style={{ fontSize: "15px", fontWeight: 800, color: "#33291F" }}>{phase.phaseName} 진행 중</span>
                    <span style={{ fontSize: "15px", fontWeight: 800, color: "#C67537" }}>{phase.progressPercent}%</span>
                  </div>
                  <div style={{ height: "10px", background: "#F0E6D4", borderRadius: "99px", overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${phase.progressPercent}%`, background: "linear-gradient(90deg, #D98040, #C67537)", borderRadius: "99px", transition: "width 1s ease" }} />
                  </div>
                  <p style={{ fontSize: "13px", color: "#9A6A3E", fontWeight: 600, margin: "10px 0 0" }}>{phase.phaseDescription}</p>
                </div>
              </div>
            ) : null}
          </section>

          {/* Stat cards */}
          <section>
            <h2 style={{ fontSize: "16px", fontWeight: 700, color: "#6E6051", letterSpacing: "0.04em", margin: "0 0 14px", textTransform: "uppercase" }}>오늘 세션 요약</h2>
            {loadingSummary ? (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "16px" }}>
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} style={{ height: "120px", background: "white", borderRadius: "20px" }} />
                ))}
              </div>
            ) : summary ? (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "16px" }}>
                <StatCard icon="💬" label="총 대화 수" value={summary.totalMessages} unit="회" accent="#7b9cff" />
                <StatCard icon="💡" label="힌트 사용" value={summary.hintsUsed} unit="회" accent="#ffb347" />
                <StatCard icon="🎯" label="미션 성공" value={summary.missionsCompleted} unit="개" accent="#6ec96e" />
                <StatCard icon="⏱️" label="세션 시간" value={summary.durationMinutes} unit="분" accent="#C67537" />
              </div>
            ) : null}
          </section>

          {/* Timeline */}
          <section style={{ paddingBottom: "40px" }}>
            <h2 style={{ fontSize: "16px", fontWeight: 700, color: "#6E6051", letterSpacing: "0.04em", margin: "0 0 14px", textTransform: "uppercase" }}>대화 타임라인</h2>
            {loadingTimeline ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {[1, 2, 3].map((i) => (
                  <div key={i} style={{ height: "72px", background: "white", borderRadius: "14px" }} />
                ))}
              </div>
            ) : timeline && timeline.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {timeline.map((event) => {
                  const meta = EVENT_META[event.type] ?? { icon: "📌", label: event.type, bg: "#F8F4EE", fg: "#6E6051" };
                  return (
                    <div key={event.id} style={{
                      background: "white",
                      borderRadius: "14px",
                      padding: "14px 18px",
                      display: "flex",
                      alignItems: "center",
                      gap: "14px",
                      boxShadow: "0 1px 6px rgba(51,41,31,0.05)",
                      border: "1px solid rgba(198,117,55,0.08)",
                    }}>
                      <div style={{
                        width: "40px", height: "40px", borderRadius: "10px",
                        background: meta.bg, display: "flex", alignItems: "center",
                        justifyContent: "center", fontSize: "20px", flexShrink: 0,
                      }}>{meta.icon}</div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "3px" }}>
                          <span style={{ fontSize: "12px", fontWeight: 700, color: meta.fg, background: meta.bg, padding: "1px 7px", borderRadius: "5px" }}>{meta.label}</span>
                          {event.missionName && (
                            <span style={{ fontSize: "12px", fontWeight: 700, color: "#2d8e36", background: "#EDFBEE", padding: "1px 7px", borderRadius: "5px" }}>{event.missionName}</span>
                          )}
                          {event.hintLevel != null && (
                            <span style={{ fontSize: "12px", fontWeight: 700, color: "#b87a00", background: "#FFF7E6", padding: "1px 7px", borderRadius: "5px" }}>Lv.{event.hintLevel}</span>
                          )}
                        </div>
                        <p style={{ fontSize: "14px", fontWeight: 600, color: "#33291F", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{event.content}</p>
                      </div>
                      <span style={{ fontSize: "12px", fontWeight: 700, color: "#9A6A3E", flexShrink: 0 }}>
                        {format(new Date(event.timestamp), "a h:mm", { locale: ko })}
                      </span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div style={{ background: "white", borderRadius: "20px", padding: "40px", textAlign: "center", color: "#9A6A3E", fontSize: "16px", fontWeight: 600 }}>
                아직 기록된 이벤트가 없습니다.
              </div>
            )}
          </section>
        </div>
      </main>

      {/* ── Floating toast for newest notification ── */}
      <AnimatePresence>
        {newNotif && (
          <motion.div
            key={newNotif.id}
            initial={{ opacity: 0, y: 40, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.97 }}
            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
            style={{
              position: "fixed",
              bottom: "28px",
              right: "28px",
              zIndex: 200,
              background: "white",
              borderRadius: "18px",
              padding: "18px 22px",
              boxShadow: "0 12px 40px rgba(51,41,31,0.22), 0 2px 0 rgba(198,117,55,0.15)",
              border: `1px solid ${NOTIF_META[newNotif.type].bar}40`,
              borderLeft: `5px solid ${NOTIF_META[newNotif.type].bar}`,
              display: "flex",
              alignItems: "center",
              gap: "14px",
              maxWidth: "360px",
              fontFamily: '"Gothic A1", sans-serif',
            }}
          >
            <span style={{
              fontSize: "30px",
              width: "48px",
              height: "48px",
              borderRadius: "50%",
              background: NOTIF_META[newNotif.type].bg,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}>
              {NOTIF_META[newNotif.type].icon}
            </span>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: "14px", color: "#6E6051", fontWeight: 700, marginBottom: "2px" }}>실시간 알림</div>
              <div style={{ fontSize: "16px", fontWeight: 800, color: "#33291F" }}>{newNotif.message}</div>
              <div style={{ fontSize: "13px", color: "#9A6A3E", marginTop: "3px" }}>{newNotif.sub}</div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
