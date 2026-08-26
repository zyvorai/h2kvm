// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { MIGRATION_ENGINE, MIGRATION_CLI, MIGRATION_PIPELINE_BANNER } from '../lib/migrationCopy';

type Props = {
  className?: string;
  compact?: boolean;
};

/** hyper2kvm pipeline identity — use above migration forms. */
export function MigrationPipelineBanner({ className = '', compact = false }: Props) {
  return (
    <div
      className={`rounded-lg border border-blue-500/20 bg-blue-500/5 ${compact ? 'px-3 py-2' : 'px-4 py-3'} ${className}`.trim()}
    >
      <p className={`${compact ? 'text-[11px]' : 'text-xs'} text-blue-300/90 font-medium`}>
        {MIGRATION_ENGINE} pipeline · {MIGRATION_CLI}
      </p>
      {!compact && (
        <p className="text-[11px] text-white/55 mt-1 leading-relaxed">{MIGRATION_PIPELINE_BANNER}</p>
      )}
    </div>
  );
}
