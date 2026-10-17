import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  use: { baseURL: 'http://127.0.0.1:3000', trace: 'on-first-retry' },
  webServer: { command: 'pnpm dev', url: 'http://127.0.0.1:3000/_app/health', reuseExistingServer: true, timeout: 60_000 },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
