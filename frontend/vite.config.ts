/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// In development, /api requests are proxied to the FastAPI backend so the
// browser talks to one origin, exactly as it will when the backend serves the
// built dashboard in production.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const backend = env.BACKEND_URL || "http://localhost:8000";

  return {
    plugins: [react(), tailwindcss()],
    // Relative asset paths let the backend serve the build from any prefix.
    base: "./",
    server: {
      port: 5173,
      proxy: {
        "/api": { target: backend, changeOrigin: true },
      },
    },
    test: {
      environment: "node",
      include: ["src/**/*.test.ts"],
    },
  };
});
