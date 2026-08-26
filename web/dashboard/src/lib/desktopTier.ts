// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import type { H2kView, NavGroup } from '../navigation/h2kNav';

export type DesktopTier = 'normal' | 'power' | 'advanced';

export const DESKTOP_TIER_KEY = 'h2kweb-desktop-tier';
export const DESKTOP_TIER_EVENT = 'h2kweb-desktop-tier-changed';

export const DESKTOP_TIER_LABELS: Record<DesktopTier, string> = {
  normal: 'Normal',
  power: 'Power user',
  advanced: 'Advanced',
};

export const DESKTOP_TIER_HINTS: Record<DesktopTier, string> = {
  normal: 'Clean desktop — dashboard, migrate hub, VMs, and jobs. Dock-first layout.',
  power: 'Full migration toolkit — providers, infrastructure, and audit log.',
  advanced: 'Complete hyper2kvm surface — API docs and all admin panes.',
};

const TIER_RANK: Record<DesktopTier, number> = {
  normal: 0,
  power: 1,
  advanced: 2,
};

const NORMAL_VIEWS = new Set<H2kView>([
  'dashboard',
  'migrate',
  'migrate-wizard',
  'providers',
  'vms',
  'jobmonitor',
  'settings',
  'about',
]);

const ADVANCED_VIEWS = new Set<H2kView>(['api-docs']);

export const DOCK_VIEWS_BY_TIER: Record<DesktopTier, H2kView[]> = {
  normal: ['dashboard', 'migrate', 'providers', 'vms', 'jobmonitor', 'settings'],
  power: ['dashboard', 'migrate', 'providers', 'vms', 'jobmonitor', 'settings'],
  advanced: ['dashboard', 'migrate', 'providers', 'vms', 'jobmonitor', 'settings'],
};

export function loadDesktopTier(): DesktopTier {
  try {
    const raw = localStorage.getItem(DESKTOP_TIER_KEY);
    if (raw === 'normal' || raw === 'power' || raw === 'advanced') return raw;
  } catch {
    /* ignore */
  }
  return 'power';
}

export function saveDesktopTier(tier: DesktopTier) {
  localStorage.setItem(DESKTOP_TIER_KEY, tier);
  window.dispatchEvent(new CustomEvent(DESKTOP_TIER_EVENT, { detail: tier }));
}

export function viewMinTier(view: H2kView): DesktopTier {
  if (ADVANCED_VIEWS.has(view)) return 'advanced';
  if (NORMAL_VIEWS.has(view)) return 'normal';
  return 'power';
}

export function tierAtLeast(current: DesktopTier, min: DesktopTier): boolean {
  return TIER_RANK[current] >= TIER_RANK[min];
}

export function isViewAllowedForTier(view: H2kView, tier: DesktopTier): boolean {
  return tierAtLeast(tier, viewMinTier(view));
}

/** Bump stored tier when navigating to a view that needs a higher desktop tier. */
export function ensureTierForView(view: H2kView, tier: DesktopTier): DesktopTier {
  const min = viewMinTier(view);
  if (tierAtLeast(tier, min)) return tier;
  saveDesktopTier(min);
  return min;
}

export function defaultViewForTier(_tier: DesktopTier): H2kView {
  return 'dashboard';
}

export function defaultSidebarVisibleForTier(_tier: DesktopTier): boolean {
  return true;
}

export function showContextBarForTier(_tier: DesktopTier): boolean {
  return true;
}

export function showContextBarForGroup(_groupId: string, _tier: DesktopTier): boolean {
  return true;
}

export function navGroupsForTier(getGroups: () => NavGroup[], tier: DesktopTier): NavGroup[] {
  return getGroups()
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => isViewAllowedForTier(item.id, tier)),
    }))
    .filter((group) => group.items.length > 0);
}
