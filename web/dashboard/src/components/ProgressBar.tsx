// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

interface ProgressBarProps {
  percent: number;
  label?: string;
  showPercent?: boolean;
}

export function ProgressBar({ percent, label, showPercent = true }: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, percent));
  return (
    <div>
      {(label || showPercent) && (
        <div className="flex justify-between text-xs text-white/55 mb-1.5">
          <span>{label || 'Progress'}</span>
          {showPercent && <span className="font-medium">{Math.round(clamped)}%</span>}
        </div>
      )}
      <div className="h-2 glass rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ease-out ${
            clamped >= 100 ? 'bg-green-500' : 'bg-blue-500'
          }`}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}
