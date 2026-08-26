// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useEffect, useRef, useCallback } from 'react';
import { useAuthStore } from '../stores/auth';
import { showToast } from '../components/Toast';

const WARNING_BEFORE_MS = 2 * 60 * 1000; // 2 minutes before timeout
const CHECK_INTERVAL_MS = 30 * 1000; // check every 30 seconds

export function useSessionTimeout(timeoutMs = 30 * 60 * 1000) {
  const lastActivity = useRef(Date.now());
  const warningShown = useRef(false);
  const { logout, isAuthenticated } = useAuthStore();

  const resetActivity = useCallback(() => {
    lastActivity.current = Date.now();
    warningShown.current = false;
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;

    // Track user activity
    const events = ['mousemove', 'keypress', 'click'] as const;
    events.forEach((event) => window.addEventListener(event, resetActivity));

    const interval = setInterval(() => {
      const elapsed = Date.now() - lastActivity.current;
      const remaining = timeoutMs - elapsed;

      if (remaining <= 0) {
        // Session expired
        clearInterval(interval);
        events.forEach((event) => window.removeEventListener(event, resetActivity));
        logout();
        window.location.reload();
        return;
      }

      if (remaining <= WARNING_BEFORE_MS && !warningShown.current) {
        warningShown.current = true;
        const mins = Math.ceil(remaining / 60000);
        showToast('warning', `Session expires in ${mins} minute${mins !== 1 ? 's' : ''}`);
      }
    }, CHECK_INTERVAL_MS);

    return () => {
      clearInterval(interval);
      events.forEach((event) => window.removeEventListener(event, resetActivity));
    };
  }, [isAuthenticated, logout, resetActivity, timeoutMs]);
}
