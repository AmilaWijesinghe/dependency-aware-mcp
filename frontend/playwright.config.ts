import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser",
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  use: {
    baseURL: "http://127.0.0.1:3000",
    channel: "chrome",
    headless: true,
    screenshot: "only-on-failure",
  },
  webServer: [
    { command: "uv run python scripts/serve_demo_test_api.py", cwd: "../backend", url: "http://127.0.0.1:8002/health", timeout: 30000 },
    { command: "npm run dev", url: "http://127.0.0.1:3000", timeout: 60000,
      env: { NEXT_PUBLIC_API_URL: "http://127.0.0.1:8002", NEXT_TELEMETRY_DISABLED: "1" } },
  ],
});
