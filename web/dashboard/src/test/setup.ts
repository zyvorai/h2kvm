// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { afterEach, beforeEach, vi } from 'vitest';

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
  vi.stubGlobal('sessionStorage', mockStorage());
});

afterEach(() => {
  vi.unstubAllGlobals();
});
