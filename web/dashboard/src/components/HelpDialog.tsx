// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import type { ReactNode } from 'react';
import { X, Keyboard, Info } from 'lucide-react';
import { Link } from 'react-router-dom';
import { t } from '../i18n';
import {
  ZYVOR_URL,
  ZYVOR_COPY,
  ZYVOR_COPYRIGHT_FULL,
  ZYVOR_LICENSE,
  ZYVOR_CONTACT_EMAIL,
  ZyvorInline,
} from './ZyvorBrand';

export type HelpTab = 'shortcuts' | 'about';

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);
const mod = isMac ? '⌘' : 'Ctrl';

const shortcuts = [
  { keys: [mod, 'K'], description: 'Open command palette (jump to any view)' },
  { keys: ['F3'], description: 'Open Mission Control' },
  { keys: ['?'], description: 'Show keyboard shortcuts' },
  { keys: ['Esc'], description: 'Close dialogs and overlays' },
];

type HelpDialogProps = {
  open: boolean;
  tab: HelpTab;
  onClose: () => void;
  onTabChange: (tab: HelpTab) => void;
};

const TABS: { id: HelpTab; label: string; icon: ReactNode }[] = [
  { id: 'shortcuts', label: 'Shortcuts', icon: <Keyboard className="w-4 h-4" aria-hidden /> },
  { id: 'about', label: 'About', icon: <Info className="w-4 h-4" aria-hidden /> },
];

const ACCENT = '#3b82f6';

export default function HelpDialog({ open, tab, onClose, onTabChange }: HelpDialogProps) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm flex items-start justify-center pt-[8vh] px-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Help"
      onKeyDown={(e) => {
        if (e.key === 'Escape') onClose();
      }}
    >
      <div
        className="w-full max-w-lg rounded-2xl shadow-2xl border border-white/[0.08] glass overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.08]">
          <h2 className="text-lg font-semibold text-white">Help</h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-white/55 hover:glass hover:text-white transition"
            aria-label="Close help"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex border-b border-white/[0.08] px-2 pt-1" role="tablist" aria-label="Help sections">
          {TABS.map((tdef) => (
            <button
              key={tdef.id}
              type="button"
              role="tab"
              aria-selected={tab === tdef.id}
              onClick={() => onTabChange(tdef.id)}
              className={`flex items-center gap-2 px-3 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
                tab === tdef.id
                  ? 'border-blue-500 text-blue-400'
                  : 'border-transparent text-white/45 hover:text-white/75'
              }`}
            >
              {tdef.icon}
              {tdef.label}
            </button>
          ))}
        </div>

        <div className="max-h-[min(70vh,32rem)] overflow-y-auto p-4">
          {tab === 'shortcuts' ? (
            <div role="tabpanel" className="space-y-3">
              {shortcuts.map((s) => (
                <div key={s.description} className="flex items-center justify-between gap-4">
                  <span className="text-sm text-white/75">{s.description}</span>
                  <kbd className="px-1.5 py-0.5 bg-white/[0.08] border border-white/[0.12] rounded text-xs font-mono text-white/75">
                    {s.keys[0]}
                  </kbd>
                </div>
              ))}
              <p className="text-xs text-white/45 pt-3 border-t border-white/[0.08]">
                Open <strong className="text-white/55">Help → About</strong> for zyvor.dev links, copyright, and
                documentation.
              </p>
              <Link
                to="/about"
                onClick={onClose}
                className="inline-block text-sm text-blue-400 hover:text-blue-300"
              >
                View full About page →
              </Link>
            </div>
          ) : (
            <div role="tabpanel" className="space-y-4 text-sm text-white/75">
              <div>
                <h3 className="text-lg font-semibold text-white">hyper2kvm</h3>
                <p className="text-white/55 mt-1">{t('about.subtitle')}</p>
              </div>
              <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 p-4 space-y-2">
                <p>
                  <a
                    href={ZYVOR_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-semibold hover:underline"
                    style={{ color: ACCENT }}
                  >
                    zyvor.dev
                  </a>{' '}
                  — {t('about.zyvor_blurb')}
                </p>
                <ZyvorInline />
              </div>
              <ul className="space-y-1.5 text-white/75">
                <li>
                  <a href="https://zyvor.dev/hyper2kvm" target="_blank" rel="noopener noreferrer" className="hover:text-blue-400">
                    Zyvor — hyper2kvm product page
                  </a>
                </li>
                <li>
                  <a href={ZYVOR_URL} target="_blank" rel="noopener noreferrer" className="hover:text-blue-400">
                    Zyvor platform & suite
                  </a>
                </li>
                <li>
                  <Link to="/api-docs" onClick={onClose} className="hover:text-blue-400">
                    API documentation (in-app)
                  </Link>
                </li>
              </ul>
              <div className="text-xs text-white/45 space-y-1 pt-2 border-t border-white/[0.08]">
                <p>{ZYVOR_COPYRIGHT_FULL}</p>
                <p>{ZYVOR_LICENSE}</p>
                <p>
                  {ZYVOR_COPY} ·{' '}
                  <a href={`mailto:${ZYVOR_CONTACT_EMAIL}`} className="text-blue-400 hover:text-blue-300">
                    {ZYVOR_CONTACT_EMAIL}
                  </a>
                </p>
              </div>
              <Link
                to="/about"
                onClick={onClose}
                className="inline-block text-sm text-blue-400 hover:text-blue-300"
              >
                View full About page →
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
