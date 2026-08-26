// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { GlassCard } from './GlassCard';
import { GlassModal } from './GlassModal';
import { statusBgClass } from '../../lib/semanticColors';

export function MacGlassPanel({
  title,
  subtitle,
  action,
  children,
  className = '',
}: {
  title?: string;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <GlassCard hover={false} className={`platform-mac-panel tahoe-glass-card p-0 ${className}`}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 px-4 pt-3.5 pb-2 border-b border-white/[0.04]">
          <div>
            {title && <h2 className="font-semibold text-[var(--text-primary)] text-sm">{title}</h2>}
            {subtitle && <p className="text-xs text-[var(--text-muted)] mt-0.5">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </GlassCard>
  );
}

export function MacToggle({
  checked,
  onChange,
  disabled,
  label,
  description,
  id,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  label: string;
  description?: string;
  id?: string;
}) {
  const toggleId = id ?? label.replace(/\s+/g, '-').toLowerCase();
  return (
    <div className="flex items-start justify-between gap-4 py-2">
      <div className="min-w-0">
        <label htmlFor={toggleId} className="text-sm font-medium text-white/90 cursor-pointer">{label}</label>
        {description && <p className="text-xs text-white/45 mt-0.5">{description}</p>}
      </div>
      <button
        id={toggleId}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`platform-mac-toggle relative shrink-0 w-11 h-6 rounded-full transition-colors ${
          checked ? statusBgClass('ok') : 'bg-white/20'
        } ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
      >
        <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-5' : 'translate-x-0'}`} />
      </button>
    </div>
  );
}

export function MacSegmentedControl<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: Array<{ value: T; label: string }>;
  value: T;
  onChange: (v: T) => void;
  label?: string;
}) {
  return (
    <div className="space-y-2">
      {label && <p className="text-xs font-medium text-white/45 uppercase tracking-wide">{label}</p>}
      <div className="inline-flex p-0.5 rounded-full bg-black/30 border border-white/[0.08]" role="tablist">
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            role="tab"
            aria-selected={value === opt.value}
            onClick={() => onChange(opt.value)}
            className={`px-3 py-1.5 text-xs font-medium rounded-full transition ${
              value === opt.value ? 'tahoe-segment-active text-white' : 'text-white/50 hover:text-white/80'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function MacListRow({
  title,
  subtitle,
  trailing,
  onClick,
  badge,
}: {
  title: string;
  subtitle?: string;
  trailing?: React.ReactNode;
  onClick?: () => void;
  badge?: React.ReactNode;
}) {
  const cls = 'flex items-center gap-3 px-4 py-3 border-b border-white/[0.04] last:border-0 hover:bg-white/[0.02] transition text-left w-full';
  const inner = (
    <>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-white/90 truncate">{title}</p>
        {subtitle && <p className="text-xs text-white/45 truncate mt-0.5">{subtitle}</p>}
      </div>
      {badge}
      {trailing}
    </>
  );
  if (onClick) {
    return <button type="button" onClick={onClick} className={cls}>{inner}</button>;
  }
  return <div className={cls}>{inner}</div>;
}

export { GlassModal };
