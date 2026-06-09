import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import { motion } from "framer-motion";

type DemoPatient = {
  id: string;
  name: string;
  dementia_type: string;
  persona_profile?: string;
};

const DEMENTIA_LABEL: Record<string, string> = {
  alzheimer: "알츠하이머",
  vascular: "혈관성",
  lewy: "루이소체",
};

export default function Home() {
  const [, setLocation] = useLocation();
  // Pre-seeded demo patients (backend/seed_demo.py) so the app can be tried
  // with rich, already-accumulated data — no need to walk the survey first.
  const [patients, setPatients] = useState<DemoPatient[]>([]);
  useEffect(() => {
    fetch("/api/patients")
      .then((r) => (r.ok ? r.json() : []))
      .then((list) =>
        setPatients(
          // Only show patients with a profile (the seeded/onboarded ones), not
          // the bare auto-created demo patient.
          Array.isArray(list)
            ? list.filter((p: DemoPatient) => (p.persona_profile || "").trim())
            : [],
        ),
      )
      .catch(() => {});
  }, []);

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

        {/* Demo patients — jump straight into a session with rich seeded data */}
        {patients.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.35, ease: [0.22, 1, 0.36, 1] }}
            style={{
              width: "100%",
              maxWidth: "800px",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "12px",
            }}
          >
            <div
              style={{
                fontSize: "14px",
                fontWeight: 700,
                color: "#9A6A3E",
                letterSpacing: "0.02em",
              }}
            >
              데모 환자로 바로 체험
            </div>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "10px",
                justifyContent: "center",
              }}
            >
              {patients.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => setLocation(`/patient/session?patient=${p.id}`)}
                  className="phys-btn"
                  style={{
                    borderRadius: "9999px",
                    padding: "10px 18px",
                    fontFamily: '"Gothic A1", sans-serif',
                    fontSize: "15px",
                    fontWeight: 800,
                    color: "#6E4A2A",
                    background: "rgba(255,255,255,0.78)",
                    border: "1.5px solid rgba(198,117,55,0.3)",
                    cursor: "pointer",
                  }}
                >
                  {p.name}
                  <span style={{ fontWeight: 600, color: "#9A8A74", marginLeft: "6px" }}>
                    {DEMENTIA_LABEL[p.dementia_type] ?? p.dementia_type}
                  </span>
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}
