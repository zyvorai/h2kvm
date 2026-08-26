// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { AnimatePresence, motion } from 'framer-motion';
import { X } from 'lucide-react';
import type { ReactNode } from 'react';

const spring = { type: 'spring' as const, stiffness: 320, damping: 28, mass: 0.85 };

export type GlassModalProps = {
  open: boolean;
  onClose: () => void;
  title?: string;
  subtitle?: string;
  children: ReactNode;
  wide?: boolean;
  footer?: ReactNode;
};

export function GlassModal({ open, onClose, title, subtitle, children, wide, footer }: GlassModalProps) {
  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center p-4">
          <motion.div
            className="liquid-glass-modal-backdrop absolute inset-0"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            aria-hidden
          />
          <motion.div
            role="dialog"
            aria-modal
            className={`liquid-glass-modal-panel relative w-full ${wide ? 'max-w-2xl' : 'max-w-lg'} overflow-hidden`}
            initial={{ opacity: 0, scale: 0.96, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 12 }}
            transition={spring}
          >
            {(title || subtitle) && (
              <div className="flex items-start justify-between gap-3 px-5 py-4 border-b border-white/[0.06]">
                <div>
                  {title && <h3 className="text-lg font-semibold text-[var(--text-primary)]">{title}</h3>}
                  {subtitle && <p className="text-sm text-[var(--text-secondary)] mt-0.5">{subtitle}</p>}
                </div>
                <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-[var(--text-secondary)] hover:bg-white/5" aria-label="Close">
                  <X className="w-5 h-5" strokeWidth={1.75} />
                </button>
              </div>
            )}
            <div className="p-5">{children}</div>
            {footer && <div className="px-5 py-4 border-t border-white/[0.06]">{footer}</div>}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
