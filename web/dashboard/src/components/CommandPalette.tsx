// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useEffect, useMemo, useRef, useState } from 'react';
import { Search } from 'lucide-react';

export type CommandPaletteItem = {
  id: string;
  label: string;
  group?: string;
  keywords?: string;
  onSelect: () => void;
};

type Props = {
  open: boolean;
  onClose: () => void;
  items: CommandPaletteItem[];
  title?: string;
};

type PaletteRow =
  | { kind: 'header'; label: string }
  | { kind: 'item'; item: CommandPaletteItem; index: number };

export function CommandPalette({ open, onClose, items, title = 'Command palette' }: Props) {
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const filteredItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((item) => {
      const hay = `${item.label} ${item.group ?? ''} ${item.keywords ?? ''}`.toLowerCase();
      return hay.includes(q);
    });
  }, [items, query]);

  const rows = useMemo((): PaletteRow[] => {
    const q = query.trim();
    if (q) {
      return filteredItems.map((item, index) => ({ kind: 'item' as const, item, index }));
    }
    const byGroup = new Map<string, CommandPaletteItem[]>();
    for (const item of items) {
      const g = item.group ?? 'Other';
      if (!byGroup.has(g)) byGroup.set(g, []);
      byGroup.get(g)!.push(item);
    }
    const out: PaletteRow[] = [];
    let index = 0;
    for (const [label, groupItems] of byGroup) {
      out.push({ kind: 'header', label });
      for (const item of groupItems) {
        out.push({ kind: 'item', item, index: index++ });
      }
    }
    return out;
  }, [items, query, filteredItems]);

  useEffect(() => {
    if (!open) {
      setQuery('');
      setActiveIndex(0);
      return;
    }
    const t = window.setTimeout(() => inputRef.current?.focus(), 0);
    return () => window.clearTimeout(t);
  }, [open]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex((i) => Math.min(i + 1, Math.max(filteredItems.length - 1, 0)));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex((i) => Math.max(i - 1, 0));
        return;
      }
      if (e.key === 'Enter' && filteredItems[activeIndex]) {
        e.preventDefault();
        filteredItems[activeIndex].onSelect();
        onClose();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, filteredItems, activeIndex, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[110] bg-black/60 backdrop-blur-sm flex items-start justify-center pt-[10vh] px-4 animate-fade-in"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div
        className="w-full max-w-xl rounded-2xl border border-white/10 glass-strong shadow-2xl overflow-hidden animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 px-4 py-3 border-b border-white/[0.08] glass">
          <Search className="w-4 h-4 text-blue-400/80 shrink-0" />
          <input
            ref={inputRef}
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Jump to a view or action…"
            className="flex-1 bg-transparent text-sm text-white placeholder-white/40 focus:outline-none"
            aria-label="Search commands"
          />
          <kbd className="hidden sm:inline px-1.5 py-0.5 text-[10px] font-mono text-white/45 border border-white/10 rounded">
            esc
          </kbd>
        </div>
        <ul className="max-h-[min(52vh,22rem)] overflow-y-auto py-2" role="listbox">
          {filteredItems.length === 0 && (
            <li className="px-4 py-8 text-center text-xs text-white/45">No matching commands</li>
          )}
          {rows.map((row) =>
            row.kind === 'header' ? (
              <li
                key={`h-${row.label}`}
                className="px-4 pt-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-white/45"
              >
                {row.label}
              </li>
            ) : (
              <li key={row.item.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={row.index === activeIndex}
                  className={`w-full flex items-center justify-between gap-3 px-4 py-2.5 text-left text-sm transition-colors ${
                    row.index === activeIndex
                      ? 'bg-blue-500/15 text-white border-l-2 border-blue-500'
                      : 'text-white/75 hover:bg-white/[0.04] border-l-2 border-transparent'
                  }`}
                  onMouseEnter={() => setActiveIndex(row.index)}
                  onClick={() => {
                    row.item.onSelect();
                    onClose();
                  }}
                >
                  <span>{row.item.label}</span>
                  {query.trim() && row.item.group ? (
                    <span className="text-[10px] text-white/45 uppercase tracking-wide shrink-0">{row.item.group}</span>
                  ) : null}
                </button>
              </li>
            )
          )}
        </ul>
        <div className="px-4 py-2 border-t border-white/[0.08] text-[10px] text-white/45 flex flex-wrap gap-x-3 gap-y-1">
          <span>↑↓ navigate</span>
          <span>↵ open</span>
          <span>esc close</span>
        </div>
      </div>
    </div>
  );
}
