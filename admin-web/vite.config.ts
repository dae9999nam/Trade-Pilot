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
      host: env.ADMIN_WEB_HOST ?? "127.0.0.1",
      port: Number(env.ADMIN_WEB_PORT ?? 5173),
      strictPort: true
    },
    preview: {
      host: env.ADMIN_WEB_HOST ?? "127.0.0.1",
      port: Number(env.ADMIN_WEB_PORT ?? 5173),
      strictPort: true
    }
  };
});
