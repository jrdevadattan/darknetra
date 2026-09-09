import { defineConfig } from "@playwright/test";
import { tmpdir } from "node:os";
import path from "node:path";
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 20_000 },
  reporter: "list",
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        command: "npm run start -- --port 3100",
        url: "http://127.0.0.1:3100",
        env: {
          CODEX_CHAT_DATA_DIR: path.join(
            tmpdir(),
            `darknetra-synthetic-e2e-${process.pid}`,
          ),
        },
        reuseExistingServer: false,
        timeout: 60_000,
      },
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3100",
    headless: true,
    viewport: { width: 1440, height: 960 },
    actionTimeout: 20_000,
    screenshot: "only-on-failure",
    trace: "off",
  },
});
