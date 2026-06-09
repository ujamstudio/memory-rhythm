import { motion } from "framer-motion";

/** Typing indicator (🧠 + bouncing dots) shown while awaiting the backend reply. */
export function TypingDots() {
  return (
    <div style={{ display: "flex", padding: "0 clamp(6px, 2vw, 12px)" }}>
      <div
        style={{
          width: "clamp(34px, 8vw, 44px)",
          height: "clamp(34px, 8vw, 44px)",
          borderRadius: "50%",
          background: "linear-gradient(135deg, #D98040, #C67537)",
          flexShrink: 0,
          marginRight: "clamp(8px, 2vw, 14px)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: "clamp(16px, 4vw, 22px)",
        }}
      >
        🧠
      </div>
      <div
        style={{
          borderRadius: "6px 24px 24px 24px",
          padding: "clamp(14px, 3.5vw, 20px) clamp(18px, 4vw, 28px)",
          background: "rgba(255,255,255,0.88)",
          border: "1.5px solid rgba(198,117,55,0.18)",
          boxShadow: "0 4px 20px rgba(51,41,31,0.10)",
          display: "flex",
          gap: "8px",
          alignItems: "center",
        }}
      >
        {[0, 1, 2].map((i) => (
          <motion.div
            key={i}
            animate={{ y: [0, -7, 0] }}
            transition={{
              repeat: Infinity,
              duration: 0.8,
              delay: i * 0.16,
              ease: "easeInOut",
            }}
            style={{
              width: "11px",
              height: "11px",
              borderRadius: "50%",
              background: "#C67537",
            }}
          />
        ))}
      </div>
    </div>
  );
}
