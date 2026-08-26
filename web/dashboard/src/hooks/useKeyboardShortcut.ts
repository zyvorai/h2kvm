// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { useEffect } from 'react';

type Options = {
  key: string;
  handler: () => void;
  enabled?: boolean;
  ctrlOrMeta?: boolean;
  shift?: boolean;
};

export function useKeyboardShortcut({
  key,
  handler,
  enabled = true,
  ctrlOrMeta = false,
  shift = false,
}: Options) {
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (ctrlOrMeta && !(e.ctrlKey || e.metaKey)) return;
      if (shift && !e.shiftKey) return;
      if (e.key !== key) return;
      e.preventDefault();
      handler();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [key, handler, enabled, ctrlOrMeta, shift]);
}
