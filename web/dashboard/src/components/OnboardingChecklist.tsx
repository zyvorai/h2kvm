// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useCallback, useEffect, useMemo, useState } from 'react';
import { CheckCircle, Circle, ChevronDown, ChevronUp, ListChecks, X } from 'lucide-react';
import { fetchAPI } from '../api/client';
import { listProviders } from '../api/providers';
import { getJobStats } from '../api/jobs';

const DEFAULT_STORAGE_KEY = 'h2kweb_onboarding_dismissed';

type ReadinessCheck = { status: string };

type Props = {
  storageKey?: string;
  onConnectProvider?: () => void;
  onStartMigration?: () => void;
  onViewJobs?: () => void;
  onOpenReadiness?: () => void;
  className?: string;
};

type StepState = {
  kvmReady: boolean;
  providerConnected: boolean;
  migrationDone: boolean;
};

export function OnboardingChecklist({
  storageKey = DEFAULT_STORAGE_KEY,
  onConnectProvider,
  onStartMigration,
  onViewJobs,
  onOpenReadiness,
  className = '',
}: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const [dismissed, setDismissed] = useState(() => localStorage.getItem(storageKey) === '1');
  const [loading, setLoading] = useState(true);
  const [state, setState] = useState<StepState>({
    kvmReady: false,
    providerConnected: false,
    migrationDone: false,
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [readiness, providers, stats] = await Promise.all([
        fetchAPI<ReadinessCheck[]>('/readiness').catch(() => []),
        listProviders().catch(() => []),
        getJobStats().catch(() => null),
      ]);

      const kvmReady =
        readiness.length > 0 &&
        readiness.every((c) => c.status === 'ok' || c.status === 'warning');
      const providerConnected = providers.some((p) => p.connected);
      const migrationDone = (stats?.completed ?? 0) > 0;

      setState({ kvmReady, providerConnected, migrationDone });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (dismissed) return;
    load();
    const t = window.setInterval(load, 45000);
    return () => window.clearInterval(t);
  }, [dismissed, load]);

  const steps = useMemo(
    () => [
      {
        id: 'kvm',
        title: 'KVM / h2kvm ready',
        done: state.kvmReady,
        hint: 'Host readiness checks (libvirt, h2kvmctl)',
        action: onOpenReadiness ? { label: 'View readiness', onClick: onOpenReadiness } : undefined,
      },
      {
        id: 'provider',
        title: 'Provider connected',
        done: state.providerConnected || state.migrationDone,
        hint: 'vSphere, Azure, AWS, or disk-only path',
        action: onConnectProvider ? { label: 'Connect provider', onClick: onConnectProvider } : undefined,
      },
      {
        id: 'migrate',
        title: 'First migration completed',
        done: state.migrationDone,
        hint: 'Export → convert → deploy pipeline',
        action: state.migrationDone
          ? onViewJobs
            ? { label: 'View jobs', onClick: onViewJobs }
            : undefined
          : onStartMigration
            ? { label: 'Start migration', onClick: onStartMigration }
            : undefined,
      },
    ],
    [state, onConnectProvider, onOpenReadiness, onStartMigration, onViewJobs]
  );

  const completedCount = steps.filter((s) => s.done).length;
  const allDone = completedCount === steps.length;

  useEffect(() => {
    if (allDone && !loading && !dismissed) {
      localStorage.setItem(storageKey, '1');
      setDismissed(true);
    }
  }, [allDone, loading, dismissed, storageKey]);

  if (dismissed) return null;

  return (
    <div
      className={`rounded-xl border border-blue-500/20 bg-gradient-to-br from-blue-500/5 to-zinc-900/40 ${className}`.trim()}
    >
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-white/[0.08]">
        <div className="flex items-center gap-2 min-w-0">
          <ListChecks className="w-4 h-4 text-blue-400 shrink-0" />
          <div>
            <h3 className="text-sm font-semibold text-white">Getting started</h3>
            <p className="text-[10px] text-white/45">
              {loading ? 'Checking…' : `${completedCount}/${steps.length} complete`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            onClick={() => setCollapsed((v) => !v)}
            className="p-1.5 rounded-lg text-white/45 hover:text-white/75 hover:bg-white/[0.04]"
            aria-label={collapsed ? 'Expand checklist' : 'Collapse checklist'}
          >
            {collapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
          </button>
          <button
            type="button"
            onClick={() => {
              localStorage.setItem(storageKey, '1');
              setDismissed(true);
            }}
            className="p-1.5 rounded-lg text-white/45 hover:text-white/75 hover:bg-white/[0.04]"
            aria-label="Dismiss checklist"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
      {!collapsed && (
        <ul className="px-4 py-3 space-y-3">
          {steps.map((step) => (
            <li key={step.id} className="flex items-start gap-3">
              {step.done ? (
                <CheckCircle className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
              ) : (
                <Circle className="w-4 h-4 text-white/40 mt-0.5 shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <div className={`text-xs font-medium ${step.done ? 'text-white/55 line-through' : 'text-white/90'}`}>
                  {step.title}
                </div>
                <p className="text-[10px] text-white/45 mt-0.5">{step.hint}</p>
                {!step.done && step.action && (
                  <button
                    type="button"
                    onClick={step.action.onClick}
                    className="mt-1.5 text-[10px] font-medium text-blue-400 hover:text-blue-300"
                  >
                    {step.action.label} →
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
