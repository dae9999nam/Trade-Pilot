import { fileURLToPath } from "node:url";

import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const repoRoot = fileURLToPath(new URL("..", import.meta.url));

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, repoRoot, "");

  return {
    envDir: repoRoot,
    plugins: [react()],
    server: {
      host: env.USER_WEB_HOST ?? "127.0.0.1",
      port: Number(env.USER_WEB_PORT ?? 5174),
      strictPort: true
    },
    preview: {
      host: env.USER_WEB_HOST ?? "127.0.0.1",
      port: Number(env.USER_WEB_PORT ?? 5174),
      strictPort: true
    }
  };
});
