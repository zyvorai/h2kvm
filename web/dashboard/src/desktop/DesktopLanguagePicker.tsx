// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { getAvailableLocales, getLocale, setLocale, type Locale } from '../i18n';

type Props = {
  compact?: boolean;
};

export function DesktopLanguagePicker({ compact }: Props) {
  const locales = getAvailableLocales();
  const current = getLocale();

  return (
    <select
      value={current}
      onChange={(e) => setLocale(e.target.value as Locale)}
      className={
        compact
          ? 'w-full rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-xs text-white/80 focus:outline-none focus:ring-1 focus:ring-blue-400/50'
          : 'rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/80 focus:outline-none focus:ring-1 focus:ring-blue-400/50'
      }
      aria-label="Language"
    >
      {locales.map((loc) => (
        <option key={loc.code} value={loc.code} className="bg-zinc-900 text-white">
          {loc.label}
        </option>
      ))}
    </select>
  );
}
