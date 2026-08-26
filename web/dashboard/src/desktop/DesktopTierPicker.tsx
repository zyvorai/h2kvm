// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import {
  DESKTOP_TIER_HINTS,
  DESKTOP_TIER_LABELS,
  type DesktopTier,
} from '../lib/desktopTier';

type Props = {
  tier: DesktopTier;
  onChange: (tier: DesktopTier) => void;
  compact?: boolean;
};

const TIERS: DesktopTier[] = ['normal', 'power', 'advanced'];

export function DesktopTierPicker({ tier, onChange, compact = false }: Props) {
  if (compact) {
    return (
      <div className="flex flex-col gap-1" data-testid="desktop-tier-picker">
        {TIERS.map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => onChange(key)}
            className={`flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-xs transition ${
              tier === key ? 'tahoe-context-pill-active' : 'text-white/60 hover:bg-white/5'
            }`}
          >
            {DESKTOP_TIER_LABELS[key]}
            {tier === key ? <span className="text-[10px] text-white/40">✓</span> : null}
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="desktop-tier-picker">
      <p className="text-sm text-white/55">
        Choose how much of the h2kvm desktop to show — like macOS simplicity vs. pro tools.
      </p>
      <div className="grid gap-2 sm:grid-cols-3">
        {TIERS.map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => onChange(key)}
            className={`rounded-xl border p-3 text-left transition ${
              tier === key
                ? 'border-blue-400/50 ring-1 ring-blue-400/30 bg-blue-500/5'
                : 'border-white/[0.08] hover:border-white/20'
            }`}
          >
            <span className="text-sm font-medium text-white block">{DESKTOP_TIER_LABELS[key]}</span>
            <span className="text-[11px] text-white/45 mt-1 block leading-snug">{DESKTOP_TIER_HINTS[key]}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
