import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

// `vite build --mode preview` swaps the server for an in-browser stand-in with sample results.
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  resolve: {
    alias: {
      "@demo": fileURLToPath(new URL(mode === "preview" ? "./src/demo/backend.ts" : "./src/demo/none.ts", import.meta.url)),
    },
  },
  server: {
    // During development the API runs on :8000 (formatly-server).
    proxy: { "/api": "http://localhost:8000" },
  },
  build: { target: "es2020", sourcemap: false, outDir: mode === "preview" ? "dist-preview" : "dist" },
}));
