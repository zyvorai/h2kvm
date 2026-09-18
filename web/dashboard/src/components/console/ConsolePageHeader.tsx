// Copyright (c) 2026 ZyvorAI Labs Private Limited.
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
// https://zyvor.dev · info@zyvor.dev

import type { ReactNode } from 'react';

type Props = {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
};

export function ConsolePageHeader({ eyebrow, title, subtitle, actions }: Props) {
  return (
    <div className="console-page-header">
      <div>
        {eyebrow && <p className="console-eyebrow">{eyebrow}</p>}
        <h1 className="console-page-title">{title}</h1>
        {subtitle && <p className="console-page-subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="console-page-header-actions">{actions}</div>}
    </div>
  );
}
