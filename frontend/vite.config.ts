// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - tanstackStart, viteReact, tailwindcss, tsConfigPaths, cloudflare (build-only),
//     componentTagger (dev-only), VITE_* env injection, @ path alias, React/TanStack dedupe,
//     error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... } }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

const BACKEND_URL = process.env.VITE_API_URL ?? "http://localhost:3000";

export default defineConfig({
  vite: {
    server: {
      proxy: {
        // Proxy all /api requests to the FastAPI backend during development.
        // This avoids CORS issues and works regardless of what port Vite runs on.
        "/api": {
          target: BACKEND_URL,
          changeOrigin: true,
          secure: false,
        },
      },
    },
  },
});
