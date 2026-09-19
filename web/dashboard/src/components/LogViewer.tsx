// Copyright (c) 2026 ZyvorAI Labs Private Limited.
// SPDX-License-Identifier: LicenseRef-Zyvor-Production-1.0
// https://zyvor.dev · info@zyvor.dev

import { MacTerminal } from './MacTerminal';

interface LogViewerProps {
  lines: string[];
  maxHeight?: number;
  title?: string;
}

export function LogViewer({ lines, maxHeight = 400, title }: LogViewerProps) {
  return <MacTerminal lines={lines} maxHeight={maxHeight} title={title ?? 'h2kvm — logs'} />;
}
