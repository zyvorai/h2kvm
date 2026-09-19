// Copyright (c) 2026 ZyvorAI Labs Private Limited.
// SPDX-License-Identifier: LicenseRef-Zyvor-Production-1.0
// https://zyvor.dev · info@zyvor.dev

import type { ReactNode } from 'react';
import { ConsolePageHeader } from '../console/ConsolePageHeader';
import { StatusCard } from '../console/StatusCard';

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

export function TahoeHero({ title, subtitle, actions, stats }: Props) {
  return (
    <div>
      <ConsolePageHeader eyebrow="h2kvm" title={title} subtitle={subtitle} actions={actions} />
      {stats && stats.length > 0 && (
        <div className="status-grid">
          {stats.map((s) => (
            <StatusCard
              key={s.label}
              label={s.label}
              value={s.value}
              ok={s.tone === 'emerald'}
            />
          ))}
        </div>
      )}
    </div>
  );
}
