// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

type Props = {
  label: string;
  value: string;
  meta?: string;
  ok?: boolean;
};

export function StatusCard({ label, value, meta, ok }: Props) {
  return (
    <div className="status-card">
      <div className="status-card-label">{label}</div>
      <div className={`status-card-value${ok ? ' ok' : ''}`}>{value}</div>
      {meta && <div className="status-card-meta">{meta}</div>}
    </div>
  );
}
