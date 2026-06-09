import { useLocation } from "wouter";
import { motion } from "framer-motion";
import { useClock } from "../lib/useClock";

export default function Landing() {
  const clock = useClock({ withYear: true, intervalMs: 1000 });
  const [, setLocation] = useLocation();

  // STEP 1 — begin with the conversational survey (초기 설문), which seeds the
  // patient's context and then hands off into the therapy session.
  const handleStart = () => setLocation("/survey");

  return (
    <div
      style={{
        height: "100dvh",
        background: "#2a2018",
        display: "flex",
        alignItems: "stretch",
        justifyContent: "center",
        padding: "clamp(6px, 2vw, 12px)",
        overflow: "hidden",
      }}
    >
      {/* Gamma ring */}
      <div className="gamma-ring" />

      {/* Paper surface */}
      <div
        className="paper-surface"
        style={{
          flex: 1,
          borderRadius: "clamp(16px, 4vw, 28px)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "clamp(28px, 7vw, 56px) clamp(20px, 5vw, 40px) clamp(32px, 8vw, 52px)",
          overflow: "hidden",
          position: "relative",
        }}
      >
        {/* Date & Time */}
        <motion.div
          initial={{ opacity: 0, y: -16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
          style={{ textAlign: "center", fontFamily: '"Gothic A1", sans-serif' }}
        >
          <div style={{
            fontSize: "clamp(16px, 4vw, 30px)",
            fontWeight: 700,
            color: "#6E6051",
            marginBottom: "clamp(4px, 1vw, 10px)",
          }}>
            {clock.date}
          </div>
          <div style={{
            fontSize: "clamp(48px, 13vw, 96px)",
            fontWeight: 900,
            color: "#C67537",
            lineHeight: 1,
            letterSpacing: "-0.03em",
          }}>
            {clock.time}
          </div>
        </motion.div>

        {/* Greeting */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, delay: 0.3, ease: [0.22, 1, 0.36, 1] }}
          style={{ textAlign: "center" }}
        >
          <p style={{
            fontFamily: '"Gowun Batang", serif',
            fontSize: "clamp(24px, 5.5vw, 46px)",
            fontWeight: 700,
            color: "#33291F",
            lineHeight: 1.45,
            maxWidth: "720px",
            margin: 0,
          }}>
            오늘도 함께 기억을<br />떠올려 볼까요?
          </p>
        </motion.div>

        {/* Start button & home link */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, delay: 0.55, ease: [0.22, 1, 0.36, 1] }}
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: "clamp(16px, 4vw, 24px)",
            width: "100%",
            maxWidth: "520px",
          }}
        >
          <motion.button
            whileHover={{ y: -4 }}
            whileTap={{ y: 5 }}
            onClick={handleStart}
            data-testid="button-start"
            className="phys-btn"
            style={{
              width: "100%",
              padding: "clamp(20px, 5vw, 32px) 0",
              borderRadius: "2rem",
              fontFamily: '"Gothic A1", sans-serif',
              fontSize: "clamp(34px, 8vw, 48px)",
              fontWeight: 900,
              letterSpacing: "-0.02em",
              color: "white",
              border: "none",
              cursor: "pointer",
              background: "linear-gradient(#D98040, #C67537)",
              boxShadow: "inset 0 3px 0 rgba(255,255,255,0.35), 0 10px 0 #8a4a1f, 0 18px 28px rgba(130,70,30,0.40)",
              opacity: 1,
            }}
          >
            시작하기
          </motion.button>

          <a
            href="/"
            data-testid="link-home"
            style={{
              fontFamily: '"Gothic A1", sans-serif',
              fontSize: "clamp(16px, 4vw, 22px)",
              fontWeight: 700,
              color: "#9A6A3E",
              textDecoration: "none",
              borderBottom: "2px solid rgba(154,106,62,0.35)",
              paddingBottom: "2px",
              cursor: "pointer",
            }}
          >
            ← 홈으로
          </a>
        </motion.div>
      </div>
    </div>
  );
}
