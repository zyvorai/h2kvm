// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import type { ReactNode } from 'react';

type Props = {
  realm?: string;
  onOpenPalette?: () => void;
  trailing?: ReactNode;
};

export function ConsoleTopbar({ realm = 'h2kvm', onOpenPalette, trailing }: Props) {
  return (
    <header className="console-topbar">
      <div className="console-topbar-realm">
        <span className="console-topbar-realm-dot" aria-hidden />
        <span>{realm}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {trailing}
        {onOpenPalette && (
          <button type="button" className="console-palette-btn" onClick={onOpenPalette}>
            Command Palette
            <kbd>⌘K</kbd>
          </button>
        )}
      </div>
    </header>
  );
}
