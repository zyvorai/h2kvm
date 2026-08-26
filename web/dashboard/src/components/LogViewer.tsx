// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useEffect, useRef } from 'react';

interface LogViewerProps {
  lines: string[];
  maxHeight?: number;
}

export function LogViewer({ lines, maxHeight = 400 }: LogViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [lines]);

  return (
    <div
      ref={containerRef}
      className="glass border border-white/[0.08] rounded-xl p-4 overflow-auto font-mono text-xs leading-relaxed"
      style={{ maxHeight }}
    >
      {lines.length === 0 ? (
        <div className="text-white/40">No output yet...</div>
      ) : (
        lines.map((line, i) => (
          <div key={i} className={getLineClass(line)}>{line}</div>
        ))
      )}
    </div>
  );
}

function getLineClass(line: string): string {
  if (line.includes('ERROR') || line.includes('error')) return 'text-red-400';
  if (line.includes('WARNING') || line.includes('warning')) return 'text-yellow-400';
  if (line.includes('SUCCESS') || line.includes('completed')) return 'text-green-400';
  if (line.includes('[PROGRESS]')) return 'text-blue-400';
  return 'text-white/75';
}
