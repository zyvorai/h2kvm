// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { useState } from 'react';
import { statusBgClass, statusSurfaceClasses } from '../lib/semanticColors';

type Props = {
  connected: boolean;
  version?: string;
};

export function DesktopStatusIsland({ connected, version }: Props) {
  const [expanded, setExpanded] = useState(false);
  const tone = connected ? 'ok' : 'error';
  const label = connected ? 'Daemon connected' : 'Daemon unreachable';

  return (
    <div className="relative pointer-events-auto">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className={`mac-dynamic-island inline-flex items-center gap-2 rounded-full border px-4 py-1 text-xs font-medium transition-all ${statusSurfaceClasses(tone)}`}
        aria-expanded={expanded}
      >
        <span className={`h-2 w-2 rounded-full ${statusBgClass(tone)}${!connected ? ' animate-pulse' : ''}`} />
        {label}
      </button>
      {expanded && (
        <div className="absolute left-1/2 top-full mt-2 -translate-x-1/2 w-[min(100vw-2rem,18rem)] rounded-2xl border border-white/[0.1] glass-strong p-4 shadow-2xl z-50 text-left">
          <p className="text-xs font-semibold text-white/80 mb-2">hyper2kvm status</p>
          <p className="text-xs text-white/55">
            API health: {connected ? 'OK' : 'Unreachable'}
          </p>
          {version && (
            <p className="text-xs text-white/45 mt-1">Version {version}</p>
          )}
        </div>
      )}
    </div>
  );
}
