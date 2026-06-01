import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite dev server. The backend runs on :8000; we proxy both the REST API
// (/api) and the WebSocket endpoint (/ws) so the frontend can use relative
// URLs and never needs to know the backend host. ws:true upgrades /ws.
export default defineConfig({
  plugins: [react()],
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
