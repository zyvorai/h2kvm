// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import type { ReactNode } from 'react';

type Action = {
  label: string;
  onClick: () => void;
  primary?: boolean;
};

type Props = {
  icon?: ReactNode;
  title: string;
  description: string;
  actions?: Action[];
  className?: string;
};

export function EmptyState({ icon, title, description, actions = [], className = '' }: Props) {
  return (
    <div
      className={`rounded-xl border border-dashed border-white/[0.12]/60 tahoe-glass-card px-6 py-10 text-center ${className}`.trim()}
    >
      {icon ? <div className="flex justify-center mb-4 opacity-80">{icon}</div> : null}
      <h3 className="text-sm font-semibold text-white mb-2">{title}</h3>
      <p className="text-xs text-white/55 max-w-md mx-auto leading-relaxed mb-5">{description}</p>
      {actions.length > 0 && (
        <div className="flex flex-wrap items-center justify-center gap-2">
          {actions.map((a) => (
            <button
              key={a.label}
              type="button"
              onClick={a.onClick}
              className={
                a.primary
                  ? 'px-4 py-2 rounded-lg text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white transition-colors'
                  : 'px-4 py-2 rounded-lg text-xs font-medium border border-white/[0.12] text-white/75 hover:bg-white/[0.04] transition-colors'
              }
            >
              {a.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
