// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import {
  Home,
  Server,
  ArrowRightLeft,
  ListChecks,
  Settings,
  Monitor,
  Cloud,
  Key,
  Network,
  FileText,
  Shield,
  Info,
} from 'lucide-react';
import { t } from '../i18n';

export type H2kView =
  | 'dashboard'
  | 'migrate'
  | 'migrate-wizard'
  | 'providers'
  | 'jobmonitor'
  | 'vms'
  | 'kubevirt'
  | 'kubeconfigs'
  | 'networks'
  | 'settings'
  | 'audit'
  | 'api-docs'
  | 'about';

export interface NavItem {
  id: H2kView;
  path: string;
  label: string;
  icon: React.ReactNode;
}

export interface NavGroup {
  id: string;
  label: string;
  items: NavItem[];
  collapsible?: boolean;
}

const NAV_DEFS: Array<{
  id: string;
  labelKey: string;
  collapsible?: boolean;
  items: Array<{ id: H2kView; path: string; i18nKey: string; icon: React.ElementType }>;
}> = [
  {
    id: 'home',
    labelKey: 'nav.group.home',
    items: [{ id: 'dashboard', path: '/', i18nKey: 'nav.dashboard', icon: Home }],
  },
  {
    id: 'migrate',
    labelKey: 'nav.group.migrate',
    collapsible: true,
    items: [
      { id: 'migrate', path: '/migrate', i18nKey: 'nav.migrate', icon: ArrowRightLeft },
      { id: 'providers', path: '/providers', i18nKey: 'nav.providers', icon: Server },
      { id: 'jobmonitor', path: '/jobs', i18nKey: 'nav.jobs', icon: ListChecks },
    ],
  },
  {
    id: 'infrastructure',
    labelKey: 'nav.group.infrastructure',
    collapsible: true,
    items: [
      { id: 'vms', path: '/vms', i18nKey: 'nav.vms', icon: Monitor },
      { id: 'kubevirt', path: '/kubevirt', i18nKey: 'nav.kubevirt', icon: Cloud },
      { id: 'kubeconfigs', path: '/kubeconfigs', i18nKey: 'nav.kubeconfigs', icon: Key },
      { id: 'networks', path: '/networks', i18nKey: 'nav.networks', icon: Network },
    ],
  },
  {
    id: 'system',
    labelKey: 'nav.group.system',
    collapsible: true,
    items: [
      { id: 'settings', path: '/settings', i18nKey: 'nav.settings', icon: Settings },
      { id: 'audit', path: '/audit', i18nKey: 'nav.audit_log', icon: Shield },
      { id: 'api-docs', path: '/api-docs', i18nKey: 'nav.api_docs', icon: FileText },
      { id: 'about', path: '/about', i18nKey: 'nav.about', icon: Info },
    ],
  },
];

export function getNavGroups(): NavGroup[] {
  return NAV_DEFS.map((group) => ({
    id: group.id,
    label: t(group.labelKey),
    collapsible: group.collapsible,
    items: group.items.map((item) => ({
      id: item.id,
      path: item.path,
      label: t(item.i18nKey),
      icon: <item.icon className="w-4 h-4" />,
    })),
  }));
}

export const navGroups = getNavGroups;

export function navLabelForView(view: H2kView): string {
  for (const group of NAV_DEFS) {
    const item = group.items.find((i) => i.id === view);
    if (item) return t(item.i18nKey);
  }
  if (view === 'migrate-wizard') return t('nav.migrate');
  return view;
}

export const pathByView = Object.fromEntries(
  NAV_DEFS.flatMap((g) => g.items.map((i) => [i.id, i.path]))
) as Record<H2kView, string>;

export const validNavViewIds = new Set<H2kView>(NAV_DEFS.flatMap((g) => g.items.map((i) => i.id)));

export const validNavPaths = new Set(NAV_DEFS.flatMap((g) => g.items.map((i) => i.path)));

export function viewFromPath(pathname: string): H2kView {
  if (pathname === '/migrate/wizard') return 'migrate-wizard';
  let best: { id: H2kView; len: number } | null = null;
  for (const group of NAV_DEFS) {
    for (const item of group.items) {
      if (item.path === '/') {
        if (pathname === '/') return 'dashboard';
        continue;
      }
      if (pathname === item.path || pathname.startsWith(`${item.path}/`)) {
        if (!best || item.path.length > best.len) {
          best = { id: item.id, len: item.path.length };
        }
      }
    }
  }
  return best?.id ?? 'dashboard';
}

export function pathFromView(view: H2kView): string {
  if (view === 'migrate-wizard') return '/migrate/wizard';
  return pathByView[view] ?? '/';
}

export function navGroupForView(view: H2kView): string | undefined {
  for (const group of NAV_DEFS) {
    if (group.items.some((item) => item.id === view)) return group.id;
  }
  if (view === 'migrate-wizard') return 'migrate';
  return undefined;
}
