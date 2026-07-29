import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      // Same-origin /api passthrough to the live bot (no CORS layer in server.py)
      "/api": {
        target: "http://100.64.0.2:7878",
        changeOrigin: true,
      },
    },
  },
});
