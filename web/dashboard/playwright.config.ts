// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5193/',
    ignoreHTTPSErrors: (process.env.PLAYWRIGHT_BASE_URL ?? '').startsWith('https'),
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        command: 'npm run build && npm run preview -- --host 127.0.0.1 --port 5193',
        url: 'http://127.0.0.1:5193/',
        reuseExistingServer: false,
        timeout: 180_000,
      },
});
