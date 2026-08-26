// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { test, expect } from '@playwright/test';
import { ensureLoggedIn, setDesktopTier } from './helpers/auth';

test('Finder sidebar is visible on desktop', async ({ page }) => {
  await ensureLoggedIn(page, 'power');
  await expect(page.getByLabel('h2kvm Finder')).toBeVisible();
});

test('normal tier shows providers in sidebar and dock', async ({ page }) => {
  await ensureLoggedIn(page, 'normal');
  const sidebar = page.getByLabel('h2kvm Finder');
  await expect(sidebar).toBeVisible();
  await expect(sidebar.getByRole('button', { name: 'Providers' })).toBeVisible();
  await expect(page.locator('.mac-dock').getByRole('button', { name: 'Providers' })).toBeVisible();
});

async function openMigrateFromDock(page: import('@playwright/test').Page) {
  await page.locator('.mac-dock').getByRole('button', { name: 'Migrate' }).click();
}

test('normal tier shows migrate context bar with providers', async ({ page }) => {
  await ensureLoggedIn(page, 'normal');
  await openMigrateFromDock(page);
  const contextBar = page.locator('.tahoe-context-bar');
  await expect(contextBar).toBeVisible();
  await expect(contextBar.getByRole('button', { name: 'Providers' })).toBeVisible();
});

test('about page reachable from normal tier', async ({ page }) => {
  await ensureLoggedIn(page, 'normal');
  await page.goto('/about');
  await expect(page).toHaveURL(/\/about$/);
  await expect(page.getByRole('heading', { name: /About/i })).toBeVisible();
});

test('switching to advanced tier reveals tier picker in control center', async ({ page }) => {
  await ensureLoggedIn(page, 'normal');
  await setDesktopTier(page, 'advanced');
  await page.reload();
  await page.waitForSelector('.mac-desktop-root', { timeout: 15_000 });
  await page.getByRole('button', { name: 'Control Center' }).click();
  await expect(page.getByTestId('desktop-tier-picker')).toBeVisible();
});
