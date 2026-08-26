// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.

/**
 * Zyvor suite branding — text only.
 * Footer: zyvor.dev · © 2026 (both orange) · optional host OS
 */
import React from 'react';

export const ZYVOR_URL = 'https://zyvor.dev';
export const ZYVOR_BRAND = 'Zyvor';
export const ZYVOR_COPY = '© 2026';
export const ZYVOR_COPYRIGHT_FULL = '© 2024–2026 Zyvor AI Labs';
export const ZYVOR_LICENSE = 'Proprietary — HyperSDK & hyper2kvm';
export const ZYVOR_CONTACT_EMAIL = 'info@zyvor.dev';
export const ZYVOR_LINE = `zyvor.dev · ${ZYVOR_COPY}`;

const ORANGE = '#f97316';
const MUTED = 'rgba(148, 163, 184, 0.75)';

const linkStyle: React.CSSProperties = {
  color: ORANGE,
  textDecoration: 'none',
  fontWeight: 600,
};

const linkHover = (e: React.MouseEvent<HTMLAnchorElement>) => {
  e.currentTarget.style.color = '#fb923c';
};

const linkLeave = (e: React.MouseEvent<HTMLAnchorElement>) => {
  e.currentTarget.style.color = ORANGE;
};

const sep = <span aria-hidden style={{ color: MUTED }}> · </span>;

function ZyvorDevLink({ className = '' }: { className?: string }) {
  return (
    <a
      href={ZYVOR_URL}
      target="_blank"
      rel="noopener noreferrer"
      className={className}
      style={linkStyle}
      onMouseEnter={linkHover}
      onMouseLeave={linkLeave}
    >
      zyvor.dev
    </a>
  );
}

type BrandProps = {
  /** @deprecated Ignored in footer — product name is not shown. */
  product?: string;
  className?: string;
  style?: React.CSSProperties;
  includeCopyright?: boolean;
};

/** Compact line: zyvor.dev · © 2026 */
export function ZyvorInline({
  className = '',
  style,
  includeCopyright = true,
}: BrandProps) {
  return (
    <span
      className={`zyvor-inline whitespace-normal ${className}`.trim()}
      style={{
        fontSize: '12px',
        lineHeight: 1.5,
        color: MUTED,
        ...style,
      }}
    >
      <ZyvorDevLink />
      {includeCopyright ? (
        <>
          {sep}
          <span style={{ color: ORANGE, fontWeight: 500 }}>{ZYVOR_COPY}</span>
        </>
      ) : null}
    </span>
  );
}

type FooterProps = {
  className?: string;
  /** Host OS pretty name (e.g. Rocky Linux 9.4) — shown when provided. */
  hostOs?: string;
  /** @deprecated Ignored — footer is zyvor.dev · © 2026 only. */
  product?: string;
};

/** Page footer — zyvor.dev · © 2026 inline (no bar). */
export function ZyvorFooter({ className = '', hostOs }: FooterProps) {
  return (
    <div
      className={`text-center py-2 ${className}`.trim()}
      role="contentinfo"
      style={{ background: 'transparent', border: 'none' }}
    >
      <ZyvorInline />
      {hostOs ? (
        <div className="mt-1 text-[11px] text-white/45" title="Daemon host operating system">
          {hostOs}
        </div>
      ) : null}
    </div>
  );
}

/** @deprecated Use ZyvorFooter or ZyvorInline. */
export function ZyvorHelpStrip(_props: BrandProps) {
  return null;
}

/** Header: zyvor.dev link only. */
export function ZyvorLogoMark({ className = '' }: { className?: string }) {
  return (
    <a
      href={ZYVOR_URL}
      target="_blank"
      rel="noopener noreferrer"
      title="zyvor.dev"
      className={className}
      style={{
        fontWeight: 600,
        fontSize: '13px',
        color: ORANGE,
        textDecoration: 'none',
      }}
      onMouseEnter={linkHover}
      onMouseLeave={linkLeave}
    >
      zyvor.dev
    </a>
  );
}

export default ZyvorFooter;
