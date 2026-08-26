// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import type { ReactNode } from 'react';

type Stat = {
  label: string;
  value: string;
  tone?: 'sky' | 'violet' | 'emerald' | 'amber';
};

type Props = {
  icon?: ReactNode;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  stats?: Stat[];
  className?: string;
};

export function TahoeHero({ icon, title, subtitle, actions, stats, className = '' }: Props) {
  return (
    <div className={`tahoe-hero relative overflow-hidden rounded-[var(--radius-liquid)] border border-white/[0.08] p-5 lg:p-6 mb-6 ${className}`}>
      <div className="tahoe-hero-shine" aria-hidden />
      <div className="relative flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div className="flex items-start gap-4 min-w-0">
          {icon && <div className="tahoe-icon-badge shrink-0">{icon}</div>}
          <div className="min-w-0">
            <h1 className="text-xl lg:text-2xl font-semibold text-white tracking-tight">{title}</h1>
            {subtitle && <p className="text-sm text-white/55 mt-1">{subtitle}</p>}
          </div>
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2 shrink-0">{actions}</div>}
      </div>
      {stats && stats.length > 0 && (
        <div className="relative grid grid-cols-2 lg:grid-cols-4 gap-3 mt-5">
          {stats.map((s) => (
            <div key={s.label} className={`tahoe-stat-tile tahoe-stat-${s.tone ?? 'sky'}`}>
              <span className="tahoe-stat-label">{s.label}</span>
              <span className="tahoe-stat-value">{s.value}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
