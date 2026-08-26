// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import type { Page } from '@playwright/test';

export type DesktopTier = 'normal' | 'power' | 'advanced';

export async function mockH2kApi(page: Page) {
  await page.route('**/api/v1/auth/session', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ authenticated: true, username: 'e2e-user' }),
    });
  });
}

export async function setDesktopTier(page: Page, tier: DesktopTier) {
  await page.evaluate((value) => {
    localStorage.setItem('h2kweb-desktop-tier', value);
  }, tier);
}

export async function ensureLoggedIn(page: Page, tier: DesktopTier = 'power') {
  await mockH2kApi(page);
  await page.goto('/');
  await setDesktopTier(page, tier);
  await page.reload();
  await page.waitForSelector('.mac-desktop-root', { timeout: 15_000 });
}
