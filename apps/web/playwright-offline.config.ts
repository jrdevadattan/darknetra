import path from 'node:path';
import { defineConfig, devices } from '@playwright/test';

const ROOT = path.resolve(__dirname, '../..');

export default defineConfig({
  testDir: './e2e',
  testMatch: 'offline-health.spec.ts',
  fullyParallel: false,
  timeout: 30_000,
  expect: { timeout: 8_000 },
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:3001',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'offline-chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'pnpm --filter @darknetra/web exec next start --hostname 127.0.0.1 --port 3001',
    cwd: ROOT,
    url: 'http://127.0.0.1:3001/system/health',
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      ...process.env,
      DARKNETRA_API_BASE_URL: 'http://127.0.0.1:65534',
      NEXT_PUBLIC_DARKNETRA_API_BASE_URL: 'http://127.0.0.1:65534',
    },
  },
});
