// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useId, useState } from 'react';
import { CircleHelp } from 'lucide-react';
import {
  MIGRATION_FIELD_HELP,
  type MigrationFieldHelpTopic,
} from '../lib/migrationFieldHelp';

type Props = {
  topic: MigrationFieldHelpTopic;
  className?: string;
};

export function FieldHelp({ topic, className = '' }: Props) {
  const help = MIGRATION_FIELD_HELP[topic];
  const [open, setOpen] = useState(false);
  const tipId = useId();

  return (
    <span className={`relative inline-flex align-middle ${className}`.trim()}>
      <button
        type="button"
        className="p-0.5 rounded-full text-white/45 hover:text-blue-400 focus:text-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
        aria-label={`Help: ${help.title}`}
        aria-expanded={open}
        aria-describedby={open ? tipId : undefined}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((v) => !v);
        }}
      >
        <CircleHelp className="w-3.5 h-3.5" aria-hidden />
      </button>
      {open && (
        <span
          id={tipId}
          role="tooltip"
          className="absolute z-50 left-1/2 -translate-x-1/2 bottom-full mb-2 w-56 rounded-lg border border-white/[0.12] glass px-3 py-2 text-left shadow-xl pointer-events-none"
        >
          <span className="block text-[11px] font-semibold text-blue-400 mb-1">{help.title}</span>
          <span className="block text-[10px] text-white/55 leading-relaxed">{help.body}</span>
        </span>
      )}
    </span>
  );
}

export function LabelWithHelp({
  label,
  topic,
  className = '',
}: {
  label: string;
  topic?: MigrationFieldHelpTopic;
  className?: string;
}) {
  return (
    <span className={`inline-flex items-center gap-1 ${className}`.trim()}>
      {label}
      {topic ? <FieldHelp topic={topic} /> : null}
    </span>
  );
}
