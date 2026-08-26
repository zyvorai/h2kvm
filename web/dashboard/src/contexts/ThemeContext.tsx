// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import {
  loadInitialTheme,
  loadInitialWallpaper,
  wallpaperForTheme,
  THEME_STORAGE_KEY,
  WALLPAPER_STORAGE_KEY,
  type AppTheme,
  type DesktopWallpaper,
} from '../lib/themeStorage';

export type { AppTheme, DesktopWallpaper };

const THEME_CYCLE: AppTheme[] = ['dark', 'steel', 'aurora'];

interface ThemeContextType {
  theme: AppTheme;
  setTheme: (t: AppTheme) => void;
  cycleTheme: () => void;
  wallpaper: DesktopWallpaper;
  setWallpaper: (w: DesktopWallpaper) => void;
}

const ThemeContext = createContext<ThemeContextType>({
  theme: 'dark',
  setTheme: () => {},
  cycleTheme: () => {},
  wallpaper: 'tahoe',
  setWallpaper: () => {},
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<AppTheme>(() => loadInitialTheme());
  const [wallpaper, setWallpaperState] = useState<DesktopWallpaper>(() => loadInitialWallpaper(loadInitialTheme()));

  const setTheme = useCallback((t: AppTheme) => {
    setThemeState(t);
    setWallpaperState(wallpaperForTheme(t));
  }, []);

  const setWallpaper = useCallback((w: DesktopWallpaper) => setWallpaperState(w), []);

  useEffect(() => {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
    const root = document.documentElement;
    root.classList.remove('steel-theme', 'aurora-theme', 'light-theme');
    root.classList.add('liquid-glass-app');
    if (theme === 'steel') root.classList.add('steel-theme');
    else if (theme === 'aurora') root.classList.add('aurora-theme');
  }, [theme]);

  useEffect(() => {
    localStorage.setItem(WALLPAPER_STORAGE_KEY, wallpaper);
  }, [wallpaper]);

  const cycleTheme = useCallback(() => {
    setThemeState((t) => {
      const next = THEME_CYCLE[(THEME_CYCLE.indexOf(t) + 1) % THEME_CYCLE.length];
      setWallpaperState(wallpaperForTheme(next));
      return next;
    });
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, cycleTheme, wallpaper, setWallpaper }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
