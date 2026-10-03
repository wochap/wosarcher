import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development, /api (HTTP and the event WebSocket) goes to a running `wosarcher serve`.
// The Origin header is rewritten to the target so the server's Origin check passes.
const api = process.env.WOSARCHER_DEV_API ?? "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: api,
        ws: true,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on("proxyReq", (req) => req.setHeader("origin", api));
          proxy.on("proxyReqWs", (req) => req.setHeader("origin", api));
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.test.{ts,tsx}", "scripts/**/*.test.mjs"],
    setupFiles: ["src/test/setup.ts"],
  },
});
