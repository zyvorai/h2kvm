// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { test, expect } from '@playwright/test';
import { ensureLoggedIn } from './helpers/auth';

test('mission control overlay opens from custom event', async ({ page }) => {
  await ensureLoggedIn(page, 'power');
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('h2k-open-mission-control')));
  await expect(page.getByTestId('mission-control-overlay')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByRole('heading', { name: 'Mission Control', level: 1 })).toBeVisible();
});

test('mission control opens with F3', async ({ page }) => {
  await ensureLoggedIn(page, 'power');
  await page.keyboard.press('F3');
  await expect(page.getByTestId('mission-control-overlay')).toBeVisible({ timeout: 10_000 });
});
