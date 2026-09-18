// Copyright (c) 2026 ZyvorAI Labs Private Limited.
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
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
