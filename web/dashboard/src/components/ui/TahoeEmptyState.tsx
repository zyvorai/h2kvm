// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import type { ReactNode } from 'react';

type Action = {
  label: string;
  onClick: () => void;
  primary?: boolean;
};

type Props = {
  icon?: ReactNode;
  title: string;
  description?: string;
  actions?: Action[];
  className?: string;
};

export function TahoeEmptyState({ icon, title, description, actions, className = '' }: Props) {
  return (
    <div className={`tahoe-empty relative overflow-hidden rounded-[var(--radius-liquid)] border border-white/[0.06] px-6 py-12 text-center ${className}`}>
      <div className="tahoe-empty-orb" aria-hidden />
      {icon && (
        <div className="tahoe-empty-icon relative z-[1] mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl text-blue-300">
          {icon}
        </div>
      )}
      <h3 className="relative z-[1] text-lg font-semibold text-white/90">{title}</h3>
      {description && <p className="relative z-[1] text-sm text-white/50 mt-2 max-w-md mx-auto">{description}</p>}
      {actions && actions.length > 0 && (
        <div className="relative z-[1] flex flex-wrap items-center justify-center gap-2 mt-6">
          {actions.map((a) => (
            <button
              key={a.label}
              type="button"
              onClick={a.onClick}
              className={a.primary ? 'tahoe-btn-primary' : 'tahoe-btn-ghost'}
            >
              {a.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
