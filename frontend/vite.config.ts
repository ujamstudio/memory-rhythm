import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

// Vite dev server for the Memory Rhythm frontend (adopted from the Replit
// monorepo, de-Replit-ified to run standalone on npm + Windows).
//
// The backend runs on :8000; we proxy both the REST API (/api) and the
// WebSocket endpoints (/ws/session, /ws/survey) so the app uses relative URLs
// and never needs to know the backend host. ws:true upgrades /ws.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "src"),
      // The orval-generated client was a pnpm workspace package; we vendored it
      // into src/lib/contract, so map the old import specifier to the local copy.
      "@workspace/api-client-react": path.resolve(
        import.meta.dirname,
        "src/lib/contract/index.ts",
      ),
    },
    dedupe: ["react", "react-dom"],
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "http://localhost:8000",
        ws: true,
        changeOrigin: true,
      },
    },
  },
});
