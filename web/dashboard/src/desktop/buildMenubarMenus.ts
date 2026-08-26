// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { t } from '../i18n';
import type { NavGroup } from '../navigation/h2kNav';
import type { H2kView } from '../navigation/h2kNav';

export const MENUBAR_NAV_GROUP_IDS = ['migrate', 'infrastructure', 'system'] as const;

export type MenubarAction =
  | H2kView
  | 'about'
  | 'spotlight'
  | 'mission'
  | 'shortcuts'
  | 'tier-normal'
  | 'tier-power'
  | 'tier-advanced';

export type MenubarItem = {
  label: string;
  action: MenubarAction;
  shortcut?: string;
  tier?: boolean;
};

export type MenubarMenu = {
  label: string;
  items: MenubarItem[];
};

function staticMenus(): MenubarMenu[] {
  return [
    {
      label: 'h2kvm',
      items: [
        { label: t('menu.about_app'), action: 'about' },
        { label: t('nav.settings'), action: 'settings' },
      ],
    },
    {
      label: t('menu.view'),
      items: [
        { label: t('nav.dashboard'), action: 'dashboard' },
        { label: t('menu.mission_control'), action: 'mission', shortcut: 'F3' },
        { label: t('menu.spotlight'), action: 'spotlight', shortcut: '⌘K' },
        { label: t('menu.tier_normal'), action: 'tier-normal', tier: true },
        { label: t('menu.tier_power'), action: 'tier-power', tier: true },
        { label: t('menu.tier_advanced'), action: 'tier-advanced', tier: true },
      ],
    },
    {
      label: t('menu.help'),
      items: [
        { label: t('menu.shortcuts'), action: 'shortcuts' },
        { label: t('nav.about'), action: 'about' },
      ],
    },
  ];
}

export function buildMenubarMenus(navGroups: NavGroup[]): MenubarMenu[] {
  const [app, view, help] = staticMenus();
  const navMenus = navGroups
    .filter((group) => MENUBAR_NAV_GROUP_IDS.includes(group.id as (typeof MENUBAR_NAV_GROUP_IDS)[number]))
    .map((group) => ({
      label: group.label,
      items: group.items.map((item) => ({
        label: item.label,
        action: item.id as MenubarAction,
      })),
    }));

  return [app, view, ...navMenus, help];
}
