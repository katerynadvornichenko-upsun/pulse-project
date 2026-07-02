import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // Same path in every environment: on Upsun, the /api route goes to the
      // api app; in dev, Vite proxies it to the local FastAPI server.
      "/api": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
  },
});
