// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

export type AppTheme = 'dark' | 'steel' | 'aurora';
export type DesktopWallpaper = 'tahoe' | 'aurora';

export const THEME_STORAGE_KEY = 'h2kweb-theme';
export const LEGACY_THEME_KEY = 'h2kweb-theme-legacy';
export const WALLPAPER_STORAGE_KEY = 'h2kweb-wallpaper';

export function wallpaperForTheme(theme: AppTheme): DesktopWallpaper {
  if (theme === 'aurora') return 'aurora';
  return 'tahoe';
}

export function parseStoredTheme(raw: string | null): AppTheme {
  if (raw === 'light') return 'steel';
  if (raw === 'dark') return 'dark';
  if (raw === 'aurora' || raw === 'steel' || raw === 'dark') return raw;
  return 'steel';
}

export function loadInitialTheme(storage: Storage | null = typeof localStorage !== 'undefined' ? localStorage : null): AppTheme {
  if (!storage) return 'steel';
  const current = storage.getItem(THEME_STORAGE_KEY);
  if (current) return parseStoredTheme(current);
  const legacy = storage.getItem('h2kweb-theme-store');
  if (legacy === 'light') return 'steel';
  if (legacy === 'dark') return 'dark';
  return 'steel';
}

export function loadInitialWallpaper(
  theme: AppTheme,
  storage: Storage | null = typeof localStorage !== 'undefined' ? localStorage : null,
): DesktopWallpaper {
  if (!storage) return wallpaperForTheme(theme);
  const w = storage.getItem(WALLPAPER_STORAGE_KEY);
  if (w === 'aurora' || w === 'tahoe') return w;
  return wallpaperForTheme(theme);
}
