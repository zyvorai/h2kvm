// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { useEffect, useState } from 'react';
import {
  DESKTOP_TIER_EVENT,
  loadDesktopTier,
  saveDesktopTier,
  type DesktopTier,
} from '../lib/desktopTier';

export function useDesktopTier(): [DesktopTier, (tier: DesktopTier) => void] {
  const [tier, setTier] = useState<DesktopTier>(() => loadDesktopTier());

  useEffect(() => {
    const onChange = () => setTier(loadDesktopTier());
    window.addEventListener(DESKTOP_TIER_EVENT, onChange);
    return () => window.removeEventListener(DESKTOP_TIER_EVENT, onChange);
  }, []);

  const save = (next: DesktopTier) => {
    saveDesktopTier(next);
    setTier(next);
  };

  return [tier, save];
}
