import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  cacheDir: "E:/AgentOpsLab/cache/vite",
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8765" } },
  preview: { port: 5173, proxy: { "/api": "http://127.0.0.1:8765" } },
});
