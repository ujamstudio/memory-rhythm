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
          fontSize: "11px",
          fontWeight: 700,
          color: "#9A8A74",
          padding: "1px 10px",
        }}
      >
        {line.text}
      </div>
    );
  }
  const isAi = line.role === "assistant";
  return (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
      style={{
        display: "flex",
        alignItems: "flex-end",
        justifyContent: isAi ? "flex-start" : "flex-end",
        padding: "0 8px",
      }}
    >
      {isAi && (
        <div
          style={{
            width: "28px",
            height: "28px",
            borderRadius: "50%",
            background: "linear-gradient(135deg, #D98040, #C67537)",
            flexShrink: 0,
            marginRight: "7px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "15px",
            boxShadow: "0 2px 6px rgba(198,117,55,0.3)",
          }}
        >
          🧠
        </div>
      )}
      <div
        style={{
          maxWidth: "76%",
          borderRadius: isAi ? "4px 16px 16px 16px" : "16px 4px 16px 16px",
          padding: "8px 12px",
          fontFamily: '"Gothic A1", sans-serif',
          fontSize: "15px",
          fontWeight: 500,
          lineHeight: 1.45,
          color: isAi ? "#33291F" : "#FCF8F1",
          background: isAi
            ? "rgba(255,255,255,0.92)"
            : "linear-gradient(135deg, #D98040, #C67537)",
          boxShadow: isAi
            ? "0 1px 4px rgba(51,41,31,0.10)"
            : "0 2px 8px rgba(130,70,30,0.28)",
          border: isAi ? "1px solid rgba(198,117,55,0.16)" : "none",
        }}
      >
        {line.text}
        {isAi && line.hintLevel !== undefined && line.hintLevel > 0 && (
          <span
            style={{
              display: "block",
              marginTop: "4px",
              fontFamily: '"Gothic A1", sans-serif',
              fontSize: "10px",
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
