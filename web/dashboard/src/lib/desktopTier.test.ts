// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ensureTierForView,
  isViewAllowedForTier,
  loadDesktopTier,
  showContextBarForGroup,
  showContextBarForTier,
} from './desktopTier';

function mockStorage(): Storage {
  const map = new Map<string, string>();
  return {
    get length() { return map.size; },
    clear: () => map.clear(),
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => { map.set(k, v); },
    removeItem: (k: string) => { map.delete(k); },
    key: (i: number) => [...map.keys()][i] ?? null,
  };
}

beforeEach(() => {
  vi.stubGlobal('localStorage', mockStorage());
});

describe('desktopTier', () => {
  it('defaults new sessions to power tier', () => {
    localStorage.removeItem('h2kweb-desktop-tier');
    expect(loadDesktopTier()).toBe('power');
  });

  it('allows providers and about on normal tier', () => {
    expect(isViewAllowedForTier('providers', 'normal')).toBe(true);
    expect(isViewAllowedForTier('about', 'normal')).toBe(true);
  });

  it('elevates tier for advanced views', () => {
    expect(ensureTierForView('api-docs', 'normal')).toBe('advanced');
    expect(ensureTierForView('providers', 'normal')).toBe('normal');
  });

  it('shows context bar on all tiers', () => {
    expect(showContextBarForTier('normal')).toBe(true);
    expect(showContextBarForGroup('migrate', 'normal')).toBe(true);
  });

  it('treats kubevirt as power-tier view', () => {
    expect(isViewAllowedForTier('kubevirt', 'normal')).toBe(false);
    expect(isViewAllowedForTier('kubevirt', 'power')).toBe(true);
  });
});
