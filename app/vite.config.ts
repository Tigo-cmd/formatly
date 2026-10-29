import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // During development the API runs on :8000 (formatly-server).
    proxy: { "/api": "http://localhost:8000" },
  },
  build: { target: "es2020", sourcemap: false },
});
