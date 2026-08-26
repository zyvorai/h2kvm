// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

const STORAGE_KEY = 'h2kweb_nav_recents';
const MAX_RECENTS = 5;

export type NavRecent = { id: string; label: string };

export function recordNavRecent(id: string, label: string): void {
  if (!id || id === '/') return;
  try {
    const prev = getNavRecents().filter((r) => r.id !== id);
    const next = [{ id, label }, ...prev].slice(0, MAX_RECENTS);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    /* ignore quota */
  }
}

export function getNavRecents(): NavRecent[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as NavRecent[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function filterNavRecents(recents: NavRecent[], validIds: ReadonlySet<string>): NavRecent[] {
  return recents.filter((r) => validIds.has(r.id));
}
