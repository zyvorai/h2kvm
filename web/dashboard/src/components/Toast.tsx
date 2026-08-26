// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useState, useEffect, useCallback } from 'react';
import { CheckCircle, AlertCircle, AlertTriangle, Info, X } from 'lucide-react';

interface Toast {
  id: number;
  type: 'success' | 'error' | 'warning' | 'info';
  message: string;
}

let toastId = 0;
const listeners: Set<(toast: Toast) => void> = new Set();

export function showToast(type: Toast['type'], message: string) {
  const toast: Toast = { id: ++toastId, type, message };
  listeners.forEach((fn) => fn(toast));
}

export function ToastContainer() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((toast: Toast) => {
    setToasts((prev) => [toast, ...prev].slice(0, 5));
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== toast.id));
    }, 5000);
  }, []);

  useEffect(() => {
    listeners.add(addToast);
    return () => { listeners.delete(addToast); };
  }, [addToast]);

  if (toasts.length === 0) return null;

  const icons = {
    success: CheckCircle,
    error: AlertCircle,
    warning: AlertTriangle,
    info: Info,
  };

  const colors = {
    success: 'border-green-500/30 bg-green-500/10 text-green-400',
    error: 'border-red-500/30 bg-red-500/10 text-red-400',
    warning: 'border-yellow-500/30 bg-yellow-500/10 text-yellow-400',
    info: 'border-zinc-500/30 bg-zinc-500/10 text-zinc-300',
  };

  return (
    <div className="fixed top-4 right-4 z-[100] space-y-2">
      {toasts.map((toast) => {
        const Icon = icons[toast.type];
        return (
          <div key={toast.id}
            className={`flex items-center gap-3 px-4 py-3 rounded-xl border backdrop-blur-xl shadow-2xl min-w-[320px] max-w-[440px] animate-slide-in ${colors[toast.type]}`}>
            <Icon className="h-4 w-4 flex-shrink-0" />
            <span className="text-sm flex-1">{toast.message}</span>
            <button onClick={() => setToasts((prev) => prev.filter((t) => t.id !== toast.id))}
              className="h-5 w-5 rounded hover:bg-white/10 flex items-center justify-center transition-colors flex-shrink-0">
              <X className="h-3 w-3" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
