import path from 'node:path';
import { defineConfig, devices } from '@playwright/test';

const ROOT = path.resolve(__dirname, '../..');

export default defineConfig({
  testDir: './e2e/online',
  fullyParallel: false,
  timeout: 30_000,
  expect: { timeout: 8_000 },
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:3000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop-chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile-chromium', use: { ...devices['Pixel 7'] } },
  ],
  webServer: [
    {
      command: 'uv run uvicorn --app-dir apps/api darknetra_api.main:app --host 127.0.0.1 --port 8000',
      cwd: ROOT,
      url: 'http://127.0.0.1:8000/api/v1/health/live',
      reuseExistingServer: false,
      timeout: 120_000,
      env: { ...process.env, DARKNETRA_BUILD_VERSION: 'e2e' },
    },
    {
      command: 'pnpm --filter @darknetra/web exec next start --hostname 127.0.0.1 --port 3000',
      cwd: ROOT,
      url: 'http://127.0.0.1:3000/dashboard',
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        DARKNETRA_API_BASE_URL: 'http://127.0.0.1:8000',
        NEXT_PUBLIC_DARKNETRA_API_BASE_URL: 'http://127.0.0.1:8000',
      },
    },
  ],
});
