import { motion } from "framer-motion";

// hint level (0..4) -> Polaroid clue opacity (mirrors the original MR mock).
const HINT_OPACITY = [0, 0.22, 0.5, 1, 1];

// keyword -> emoji so the clue reflects the 두뇌's detected keyword (from the
// latest `reasoning` message). Falls back to a generic clue.
const KEYWORD_EMOJI: Record<string, string> = {
  시장: "🛒",
  고등어: "🐟",
  생선: "🐟",
  약: "💊",
  물: "🫗",
  산책: "👟",
  전화: "📞",
  바다: "🌊",
  학교: "🏫",
  집: "🏠",
  꽃: "🌷",
  음식: "🍲",
  노래: "🎵",
  사진: "🖼️",
  가족: "👪",
};

export function emojiFor(kw: string | undefined): string {
  if (!kw) return "💭";
  for (const [k, e] of Object.entries(KEYWORD_EMOJI)) {
    if (kw.includes(k)) return e;
  }
  return "💭";
}

/**
 * Progressive Polaroid clue, driven by the real backend hint_level. The emoji,
 * caption, and (at level 4) text cue are derived from the 두뇌's focus keyword.
 */
export function HintPolaroid({
  hintLevel,
  keyword,
}: {
  hintLevel: number;
  keyword?: string;
}) {
  if (hintLevel === 0) return null;
  const emoji = emojiFor(keyword);
  const caption = keyword ?? "기억 단서";
  const cue = keyword
    ? `'${keyword}'와 관련된 기억이에요.`
    : "천천히 떠올려 보세요.";
  const opacity = HINT_OPACITY[Math.min(hintLevel, 4)];
  return (
    <motion.div
      className="hint-polaroid"
      initial={{ opacity: 0, y: -8, scale: 0.96 }}
      animate={{ opacity, y: 0, scale: 1 }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      style={{
        display: "flex",
        justifyContent: "center",
        // The clue image + caption are already viewport-HEIGHT capped below
        // (min(..,14vh)/min(..,7.5vh)), so the Polaroid's intrinsic height is
        // bounded and it pushes the chat down without overlapping it. (A prior
        // maxHeight+overflow:visible clamp painted the card OVER the chat on
        // short screens; on very short viewports the whole Polaroid is hidden
        // via the .hint-polaroid media query instead.)
        padding: "4px 0 2px",
        flexShrink: 0,
      }}
    >
      <div
        style={{
          transform: "rotate(-1.8deg)",
          borderRadius: "6px",
          background: "white",
          padding: "clamp(5px, 1.4vw, 9px) clamp(7px, 1.8vw, 10px) clamp(4px, 1vw, 6px)",
          boxShadow: "0 8px 20px rgba(58,44,32,0.22)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          position: "relative",
          maxWidth: "min(82vw, 240px)",
        }}
      >
        <div
          style={{
            position: "absolute",
            top: "-8px",
            left: "50%",
            transform: "translateX(-50%) rotate(2deg)",
            width: "clamp(44px, 11vw, 60px)",
            height: "clamp(14px, 3.4vw, 20px)",
            borderRadius: "2px",
            background: "rgba(201,162,75,0.45)",
          }}
        />
        <div
          style={{
            // Square clue image, but also capped by viewport HEIGHT (vmin/vh)
            // so it shrinks on short screens instead of pushing the chat away.
            width: "min(clamp(60px, 14vw, 96px), 14vh)",
            height: "min(clamp(60px, 14vw, 96px), 14vh)",
            background: "linear-gradient(135deg, #efe5d2, #e8d8c0)",
            borderRadius: "4px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "min(clamp(30px, 7.5vw, 48px), 7.5vh)",
            filter: hintLevel < 3 ? `blur(${(3 - hintLevel) * 4}px)` : "none",
            transition: "filter 0.8s ease",
          }}
        >
          {emoji}
        </div>
        <div
          style={{
            marginTop: "3px",
            fontFamily: '"Nanum Pen Script", cursive',
            fontSize: "clamp(15px, 3.4vw, 20px)",
            lineHeight: 1.1,
            color: "#33291F",
            whiteSpace: "nowrap",
          }}
        >
          {caption}
        </div>
        {hintLevel >= 4 && (
          <div
            style={{
              marginTop: "2px",
              fontFamily: '"Gothic A1", sans-serif',
              fontSize: "clamp(10px, 2.4vw, 13px)",
              fontWeight: 700,
              color: "#9A6A3E",
              textAlign: "center",
              maxWidth: "160px",
            }}
          >
            {cue}
          </div>
        )}
      </div>
    </motion.div>
  );
}
