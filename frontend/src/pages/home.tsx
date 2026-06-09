import { useLocation } from "wouter";
import { motion } from "framer-motion";

export default function Home() {
  const [, setLocation] = useLocation();

  return (
    <div
      style={{
        height: "100dvh",
        background: "#2a2018",
        display: "flex",
        alignItems: "stretch",
        justifyContent: "center",
        padding: "16px",
        overflow: "hidden",
        fontFamily: '"Gothic A1", sans-serif',
      }}
    >
      {/* Gamma ring */}
      <div className="gamma-ring" />

      {/* Paper surface */}
      <div
        className="paper-surface"
        style={{
          flex: 1,
          borderRadius: "28px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "40px",
          padding: "48px",
          overflow: "hidden",
        }}
      >
        {/* Logo / Title */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          style={{ textAlign: "center" }}
        >
          <div style={{ fontSize: "48px", marginBottom: "12px" }}>🧠</div>
          <h1
            style={{
              fontFamily: '"Gowun Batang", serif',
              fontSize: "42px",
              fontWeight: 700,
              color: "#33291F",
              margin: 0,
              letterSpacing: "-0.01em",
            }}
          >
            Memory Rhythm
          </h1>
          <p style={{ fontSize: "18px", color: "#9A6A3E", fontWeight: 600, marginTop: "8px" }}>
            AI 인지 보조 서비스
          </p>
        </motion.div>

        {/* Mode cards */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
          style={{
            display: "flex",
            gap: "24px",
            width: "100%",
            maxWidth: "800px",
            flexWrap: "wrap",
            justifyContent: "center",
          }}
        >
          {/* Mobile / Patient card */}
          <motion.button
            whileHover={{ y: -6, scale: 1.02 }}
            whileTap={{ y: 4 }}
            onClick={() => setLocation("/patient")}
            data-testid="button-patient-mode"
            className="phys-btn"
            style={{
              flex: "1 1 300px",
              maxWidth: "360px",
              borderRadius: "28px",
              padding: "40px 32px",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "20px",
              cursor: "pointer",
              border: "none",
              background: "linear-gradient(160deg, #D98040 0%, #C67537 100%)",
              boxShadow:
                "inset 0 3px 0 rgba(255,255,255,0.35), 0 12px 0 #8a4a1f, 0 20px 40px rgba(130,70,30,0.45)",
              color: "white",
              textAlign: "center",
            }}
          >
            <div style={{ fontSize: "64px", lineHeight: 1 }}>📱</div>
            <div>
              <div
                style={{
                  fontSize: "28px",
                  fontWeight: 900,
                  letterSpacing: "-0.02em",
                  marginBottom: "8px",
                }}
              >
                환자 화면
              </div>
              <div
                style={{
                  fontSize: "15px",
                  fontWeight: 600,
                  opacity: 0.85,
                  lineHeight: 1.5,
                }}
              >
                태블릿 · 스마트폰 전용
                <br />
                어르신이 직접 사용하는 화면
              </div>
            </div>
            <div
              style={{
                marginTop: "8px",
                fontSize: "13px",
                fontWeight: 700,
                background: "rgba(255,255,255,0.2)",
                padding: "6px 16px",
                borderRadius: "99px",
                letterSpacing: "0.03em",
              }}
            >
              MOBILE
            </div>
          </motion.button>

          {/* PC / Caregiver card */}
          <motion.button
            whileHover={{ y: -6, scale: 1.02 }}
            whileTap={{ y: 4 }}
            onClick={() => setLocation("/caregiver")}
            data-testid="button-caregiver-mode"
            className="phys-btn"
            style={{
              flex: "1 1 300px",
              maxWidth: "360px",
              borderRadius: "28px",
              padding: "40px 32px",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "20px",
              cursor: "pointer",
              border: "none",
              background: "linear-gradient(160deg, #4a3a2a 0%, #33291F 100%)",
              boxShadow:
                "inset 0 3px 0 rgba(255,255,255,0.12), 0 12px 0 #1a1208, 0 20px 40px rgba(20,15,8,0.5)",
              color: "#F4EBDD",
              textAlign: "center",
            }}
          >
            <div style={{ fontSize: "64px", lineHeight: 1 }}>🖥️</div>
            <div>
              <div
                style={{
                  fontSize: "28px",
                  fontWeight: 900,
                  letterSpacing: "-0.02em",
                  marginBottom: "8px",
                }}
              >
                보호자 대시보드
              </div>
              <div
                style={{
                  fontSize: "15px",
                  fontWeight: 600,
                  opacity: 0.75,
                  lineHeight: 1.5,
                }}
              >
                PC · 노트북 전용
                <br />
                보호자가 확인하는 현황 화면
              </div>
            </div>
            <div
              style={{
                marginTop: "8px",
                fontSize: "13px",
                fontWeight: 700,
                background: "rgba(198,117,55,0.25)",
                color: "#C67537",
                padding: "6px 16px",
                borderRadius: "99px",
                letterSpacing: "0.03em",
              }}
            >
              PC
            </div>
          </motion.button>
        </motion.div>
      </div>
    </div>
  );
}
