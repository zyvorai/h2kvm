// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { Link } from 'react-router-dom';
import { ExternalLink, HelpCircle, Info, Mail, FileText, BookOpen } from 'lucide-react';
import { t } from '../i18n';
import {
  ZYVOR_URL,
  ZYVOR_COPYRIGHT_FULL,
  ZYVOR_LICENSE,
  ZYVOR_CONTACT_EMAIL,
  ZyvorInline,
} from '../components/ZyvorBrand';

const DOCS_BASE = 'https://github.com/ssahani/h2kvm-/tree/main/docs';

type HelpLink = {
  labelKey: string;
  descKey: string;
  href?: string;
  to?: string;
  icon: React.ElementType;
};

const HELP_LINKS: HelpLink[] = [
  {
    labelKey: 'about.link.product',
    descKey: 'about.link.product_desc',
    href: 'https://zyvor.dev/h2kvm',
    icon: ExternalLink,
  },
  { labelKey: 'about.link.zyvor', descKey: 'about.link.zyvor_desc', href: ZYVOR_URL, icon: ExternalLink },
  {
    labelKey: 'about.link.docs',
    descKey: 'about.link.docs_desc',
    href: DOCS_BASE,
    icon: BookOpen,
  },
  {
    labelKey: 'about.link.dashboard_guide',
    descKey: 'about.link.dashboard_guide_desc',
    href: `${DOCS_BASE}/guides/web-dashboard-guide.md`,
    icon: FileText,
  },
  { labelKey: 'about.link.api', descKey: 'about.link.api_desc', to: '/api-docs', icon: HelpCircle },
];

export function AboutPage() {
  const metaRows = [
    { label: t('about.product'), value: 'h2kvm' },
    { label: t('about.ui'), value: 'h2kweb dashboard' },
    { label: t('about.cli'), value: 'h2kvmctl' },
    { label: t('about.copyright'), value: ZYVOR_COPYRIGHT_FULL },
    { label: t('about.license'), value: ZYVOR_LICENSE },
    {
      label: t('about.contact'),
      value: ZYVOR_CONTACT_EMAIL,
      href: `mailto:${ZYVOR_CONTACT_EMAIL}`,
    },
  ];

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-gradient-green mb-2 flex items-center gap-2">
          <Info className="w-7 h-7 text-emerald-400" />
          {t('about.title')}
        </h2>
        <p className="text-sm text-white/55">{t('about.subtitle')}</p>
      </div>

      <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-5 py-4">
        <p className="text-sm text-white/75 leading-relaxed mb-3">
          <a
            href={ZYVOR_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="text-orange-400 font-semibold hover:text-orange-300"
          >
            {ZYVOR_URL.replace('https://', '')}
          </a>{' '}
          {t('about.zyvor_blurb')}
        </p>
        <ZyvorInline />
      </div>

      <div className="tahoe-glass-card border border-white/[0.08] rounded-xl p-6">
        <h3 className="text-sm font-semibold text-white flex items-center gap-2 mb-4">
          <HelpCircle className="w-4 h-4 text-blue-400" />
          {t('about.help_section')}
        </h3>
        <div className="space-y-2">
          {HELP_LINKS.map((link) => {
            const Icon = link.icon;
            const content = (
              <>
                <Icon className="w-4 h-4 text-white/45 shrink-0 mt-0.5" />
                <div className="min-w-0">
                  <div className="text-sm font-medium text-white">{t(link.labelKey)}</div>
                  <div className="text-xs text-white/45">{t(link.descKey)}</div>
                </div>
                {(link.href?.startsWith('http')) && <ExternalLink className="w-3.5 h-3.5 text-white/40 shrink-0" />}
              </>
            );
            const className =
              'flex items-start gap-3 p-3 rounded-lg border border-white/[0.08] tahoe-glass-card hover:border-white/[0.12] hover:tahoe-glass-card transition-colors';
            if (link.to) {
              return (
                <Link key={link.labelKey} to={link.to} className={className}>
                  {content}
                </Link>
              );
            }
            return (
              <a
                key={link.labelKey}
                href={link.href}
                target="_blank"
                rel="noopener noreferrer"
                className={className}
              >
                {content}
              </a>
            );
          })}
        </div>
      </div>

      <div className="tahoe-glass-card border border-white/[0.08] rounded-xl p-6">
        <h3 className="text-sm font-semibold text-white mb-4">{t('about.info_section')}</h3>
        <div className="space-y-0">
          {metaRows.map((row) => (
            <div
              key={row.label}
              className="flex items-center justify-between py-2.5 border-b border-white/[0.06] last:border-0 gap-4"
            >
              <span className="text-sm text-white/55 shrink-0">{row.label}</span>
              {'href' in row && row.href ? (
                <a
                  href={row.href}
                  className="text-sm font-medium text-orange-400 hover:text-orange-300 text-right truncate"
                >
                  {row.value}
                </a>
              ) : (
                <span className="text-sm font-medium text-white text-right truncate">{row.value}</span>
              )}
            </div>
          ))}
        </div>
      </div>

      <p className="text-center text-[11px] text-white/45 pb-2">
        {t('about.footer_note')}{' '}
        <a
          href={`mailto:${ZYVOR_CONTACT_EMAIL}`}
          className="text-orange-400 hover:text-orange-300 inline-flex items-center gap-1"
        >
          <Mail className="w-3 h-3" />
          {ZYVOR_CONTACT_EMAIL}
        </a>
      </p>
    </div>
  );
}
