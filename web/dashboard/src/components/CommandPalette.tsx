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
      className="cmd-overlay"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div className="cmd-panel" onClick={(e) => e.stopPropagation()}>
        <div className="cmd-search">
          <Search className="w-4 h-4 shrink-0" style={{ color: 'var(--zy-500)' }} />
          <input
            ref={inputRef}
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Jump to a view or action…"
            aria-label="Search commands"
          />
          <kbd>esc</kbd>
        </div>
        <ul className="cmd-list" role="listbox">
          {filteredItems.length === 0 && (
            <li className="cmd-group">No matching commands</li>
          )}
          {rows.map((row) =>
            row.kind === 'header' ? (
              <li key={`h-${row.label}`} className="cmd-group">{row.label}</li>
            ) : (
              <li key={row.item.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={row.index === activeIndex}
                  className={`cmd-item${row.index === activeIndex ? ' is-active' : ''}`}
                  onMouseEnter={() => setActiveIndex(row.index)}
                  onClick={() => {
                    row.item.onSelect();
                    onClose();
                  }}
                >
                  <span>{row.item.label}</span>
                  {query.trim() && row.item.group ? (
                    <span className="cmd-group" style={{ padding: 0 }}>{row.item.group}</span>
                  ) : null}
                </button>
              </li>
            )
          )}
        </ul>
        <div className="cmd-foot">
          <span>↑↓ navigate</span>
          <span>↵ open</span>
          <span>esc close</span>
        </div>
      </div>
    </div>
  );
}
