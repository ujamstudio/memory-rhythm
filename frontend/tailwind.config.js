/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Warm, calm palette suitable for elderly users.
        cream: "#fbf6ee",
        sand: "#f3e9da",
        clay: "#e7d3bb",
        amber: {
          warm: "#d99a4e",
          deep: "#b9762b",
        },
        sage: "#7c8f76",
        ink: "#3a342c",
        muted: "#8a7f6f",
      },
      fontFamily: {
        sans: [
          "Pretendard",
          "Apple SD Gothic Neo",
          "Malgun Gothic",
          "system-ui",
          "sans-serif",
        ],
      },
      boxShadow: {
        soft: "0 8px 30px rgba(58, 52, 44, 0.12)",
        handset: "0 12px 40px rgba(58, 52, 44, 0.25)",
      },
      keyframes: {
        // ~40Hz visual flicker for the e-book backlight (gamma entrainment cue).
        // 40Hz = 25ms period; one bright/dim cycle per frame.
        gamma: {
          "0%, 49%": { opacity: "1" },
          "50%, 100%": { opacity: "0.78" },
        },
        breathe: {
          "0%, 100%": { transform: "scale(1)" },
          "50%": { transform: "scale(1.04)" },
        },
        fadeup: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        gamma: "gamma 0.025s steps(1) infinite",
        breathe: "breathe 4s ease-in-out infinite",
        fadeup: "fadeup 0.35s ease-out both",
      },
    },
  },
  plugins: [],
};
