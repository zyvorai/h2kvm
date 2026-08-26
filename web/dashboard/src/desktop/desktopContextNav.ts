// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import type { NavItem } from '../navigation/h2kNav';

export const MAX_CONTEXT_PILLS = 6;

export function splitContextNavItems(
  items: NavItem[],
  activeId: string,
  maxVisible = MAX_CONTEXT_PILLS,
): { visible: NavItem[]; overflow: NavItem[] } {
  if (items.length <= maxVisible) return { visible: items, overflow: [] };

  const activeIndex = items.findIndex((item) => item.id === activeId);
  const primary = items.slice(0, maxVisible - 1);
  const active = activeIndex >= 0 ? items[activeIndex] : null;

  if (active && !primary.some((item) => item.id === active.id)) {
    const visible = [...primary, active];
    const visibleIds = new Set(visible.map((item) => item.id));
    return {
      visible,
      overflow: items.filter((item) => !visibleIds.has(item.id)),
    };
  }

  return {
    visible: items.slice(0, maxVisible),
    overflow: items.slice(maxVisible),
  };
}
