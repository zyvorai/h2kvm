// Copyright (c) 2026 ZyvorAI Labs Private Limited.
// SPDX-License-Identifier: LicenseRef-Zyvor-Production-1.0
// https://zyvor.dev · info@zyvor.dev

import { useEffect, useRef, type ReactNode } from 'react';

type Props = {
  lines: string[];
  title?: string;
  maxHeight?: number;
  isRunning?: boolean;
  autoScroll?: boolean;
  onToggleFollow?: () => void;
};

const ANSI = /\u001b\[([0-9;]*)m/g;

const ANSI_CLASS: Record<string, string> = {
  '31': 'ansi-red',
  '32': 'ansi-green',
  '33': 'ansi-yellow',
  '34': 'ansi-blue',
  '35': 'ansi-magenta',
  '36': 'ansi-cyan',
  '90': 'ansi-dim',
  '91': 'ansi-red',
  '92': 'ansi-green',
  '93': 'ansi-yellow',
  '94': 'ansi-blue',
  '95': 'ansi-magenta',
  '96': 'ansi-cyan',
  '2': 'ansi-dim',
};

function paintPlain(text: string): ReactNode {
  if (/error|traceback|fatal|failed/i.test(text)) return <span className="kw-error">{text}</span>;
  if (/warn/i.test(text)) return <span className="kw-warn">{text}</span>;
  if (/success|completed|✓|ok\b/i.test(text)) return <span className="kw-ok">{text}</span>;
  if (/\[PROGRESS\]|progress/i.test(text)) return <span className="kw-progress">{text}</span>;
  const stamped = text.match(/^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?\s*)([\s\S]*)$/);
  if (stamped) {
    return (
      <>
        <span className="kw-time">{stamped[1]}</span>
        {paintPlain(stamped[2])}
      </>
    );
  }
  const path = text.match(/((?:\/[\w.@+-]+)+)/);
  if (path && path.index !== undefined) {
    const i = path.index;
    return (
      <>
        {text.slice(0, i)}
        <span className="kw-path">{path[1]}</span>
        {text.slice(i + path[1].length)}
      </>
    );
  }
  return text;
}

function paintLine(line: string): ReactNode {
  if (!line.includes('\u001b[')) return paintPlain(line);
  const parts: ReactNode[] = [];
  let last = 0;
  let cls = '';
  let n = 0;
  ANSI.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = ANSI.exec(line))) {
    if (m.index > last) {
      const chunk = line.slice(last, m.index);
      parts.push(cls ? <span key={n++} className={cls}>{chunk}</span> : <span key={n++}>{paintPlain(chunk)}</span>);
    }
    const code = (m[1] || '0').split(';').pop() || '0';
    cls = code === '0' ? '' : (ANSI_CLASS[code] || '');
    last = m.index + m[0].length;
  }
  if (last < line.length) {
    const chunk = line.slice(last);
    parts.push(cls ? <span key={n++} className={cls}>{chunk}</span> : <span key={n++}>{paintPlain(chunk)}</span>);
  }
  return parts;
}

export function MacTerminal({
  lines,
  title = 'h2kvm — zsh',
  maxHeight = 420,
  isRunning,
  autoScroll = true,
  onToggleFollow,
}: Props) {
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (autoScroll && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [lines, autoScroll]);

  return (
    <div className="mac-terminal">
      <div className="mac-terminal-bar">
        <span className="mac-terminal-lights" aria-hidden>
          <i /><i /><i />
        </span>
        <span className="mac-terminal-title">{title}</span>
        <div className="mac-terminal-actions">
          {onToggleFollow && (
            <button type="button" className={`mac-terminal-follow${autoScroll ? ' is-on' : ''}`} onClick={onToggleFollow}>
              {autoScroll ? 'Following' : 'Paused'}
            </button>
          )}
        </div>
      </div>
      <div ref={bodyRef} className="mac-terminal-body" style={{ maxHeight }}>
        {lines.length === 0 ? (
          <div className="mac-terminal-empty">{isRunning ? 'Waiting for output…' : 'No output yet'}</div>
        ) : (
          lines.map((line, i) => (
            <div key={i} className="mac-terminal-line">
              <span className="mac-terminal-gutter">{i + 1}</span>
              {paintLine(line)}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
