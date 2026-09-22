import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In container dev/prod the SPA is served by the web image; API calls go to
// the same origin (see Dockerfile/nginx).  The dev server proxies to a local
// backend on VITE_API_PROXY_TARGET.
export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.WEB_PORT ?? 5173),
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
      },
      "/health": {
        target: process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: Number(process.env.WEB_PORT ?? 8080),
  },
});
