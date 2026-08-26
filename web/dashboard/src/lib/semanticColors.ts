// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

export function statusToneClass(tone: 'ok' | 'warn' | 'error' | 'info' | 'neutral'): string {
  switch (tone) {
    case 'ok': return 'text-[var(--machina-status-ok)]';
    case 'warn': return 'text-[var(--machina-status-warn)]';
    case 'error': return 'text-[var(--machina-status-error)]';
    case 'info': return 'text-[var(--machina-status-info)]';
    default: return 'text-[var(--machina-status-neutral)]';
  }
}

export function statusBgClass(tone: 'ok' | 'warn' | 'error' | 'info' | 'neutral'): string {
  switch (tone) {
    case 'ok': return 'bg-[var(--machina-status-ok)]';
    case 'warn': return 'bg-[var(--machina-status-warn)]';
    case 'error': return 'bg-[var(--machina-status-error)]';
    case 'info': return 'bg-[var(--machina-status-info)]';
    default: return 'bg-[var(--machina-status-neutral)]';
  }
}

export function statusSurfaceClasses(tone: 'ok' | 'warn' | 'error' | 'info' | 'neutral', extra = ''): string {
  const varName = {
    ok: '--machina-status-ok',
    warn: '--machina-status-warn',
    error: '--machina-status-error',
    info: '--machina-status-info',
    neutral: '--machina-status-neutral',
  }[tone];
  return [
    extra,
    `border-[color-mix(in_srgb,var(${varName})_30%,transparent)]`,
    `bg-[color-mix(in_srgb,var(${varName})_10%,transparent)]`,
    `text-[color-mix(in_srgb,var(${varName})_75%,white)]`,
  ].filter(Boolean).join(' ');
}

export function statusBadgeClasses(tone: 'ok' | 'warn' | 'error' | 'info' | 'neutral'): string {
  const varName = {
    ok: '--machina-status-ok',
    warn: '--machina-status-warn',
    error: '--machina-status-error',
    info: '--machina-status-info',
    neutral: '--machina-status-neutral',
  }[tone];
  return `bg-[color-mix(in_srgb,var(${varName})_18%,transparent)] text-[var(${varName})]`;
}

export function navActiveChipClasses(extra = ''): string {
  return `${statusBadgeClasses('info')} ring-1 ring-[color-mix(in_srgb,var(--machina-status-info)_35%,transparent)] ${extra}`.trim();
}
