import { motion } from "framer-motion";

export type ChatRole = "user" | "assistant" | "system";

export interface ChatLine {
  role: ChatRole;
  text: string;
  hintLevel?: number;
}

/** A chat line: 🧠 assistant bubble, patient bubble, or a centered system divider. */
export function ChatBubble({ line }: { line: ChatLine }) {
  if (line.role === "system") {
    return (
      <div
        style={{
          textAlign: "center",
          fontFamily: '"Gothic A1", sans-serif',
          fontSize: "clamp(11px, 3vw, 14px)",
          fontWeight: 700,
          color: "#9A8A74",
          padding: "2px clamp(6px, 2vw, 12px)",
        }}
      >
        {line.text}
      </div>
    );
  }
  const isAi = line.role === "assistant";
  return (
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1] }}
      style={{
        display: "flex",
        justifyContent: isAi ? "flex-start" : "flex-end",
        padding: "0 clamp(6px, 2vw, 12px)",
      }}
    >
      {isAi && (
        <div
          style={{
            width: "clamp(34px, 8vw, 44px)",
            height: "clamp(34px, 8vw, 44px)",
            borderRadius: "50%",
            background: "linear-gradient(135deg, #D98040, #C67537)",
            flexShrink: 0,
            marginRight: "clamp(8px, 2vw, 14px)",
            marginTop: "4px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "clamp(16px, 4vw, 22px)",
            boxShadow: "0 4px 12px rgba(198,117,55,0.35)",
          }}
        >
          🧠
        </div>
      )}
      <div
        style={{
          maxWidth: "78%",
          borderRadius: isAi ? "6px 24px 24px 24px" : "24px 6px 24px 24px",
          padding: "clamp(14px, 3.5vw, 22px) clamp(18px, 4.5vw, 32px)",
          fontFamily: '"Gowun Batang", serif',
          fontSize: "clamp(18px, 4.5vw, 30px)",
          fontWeight: 700,
          lineHeight: 1.5,
          color: isAi ? "#33291F" : "#FCF8F1",
          background: isAi
            ? "rgba(255,255,255,0.88)"
            : "linear-gradient(135deg, #D98040, #C67537)",
          boxShadow: isAi
            ? "0 4px 20px rgba(51,41,31,0.10), 0 1px 0 rgba(255,255,255,0.8)"
            : "0 6px 24px rgba(130,70,30,0.35), inset 0 1px 0 rgba(255,255,255,0.25)",
          border: isAi ? "1.5px solid rgba(198,117,55,0.18)" : "none",
        }}
      >
        {line.text}
        {isAi && line.hintLevel !== undefined && line.hintLevel > 0 && (
          <span
            style={{
              display: "block",
              marginTop: "6px",
              fontFamily: '"Gothic A1", sans-serif',
              fontSize: "clamp(10px, 2.5vw, 13px)",
              fontWeight: 800,
              color: "#9A6A3E",
            }}
          >
            힌트 레벨 {line.hintLevel}
          </span>
        )}
      </div>
    </motion.div>
  );
}
