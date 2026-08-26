// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { fetchAPI } from './client';

export interface FileEntry {
  name: string;
  path: string;
  is_dir: boolean;
  is_vm: boolean;
  size: number;
}

export interface BrowseResult {
  path: string;
  parent: string;
  entries: FileEntry[];
}

export const browsePath = (path: string, filterVM = false) => {
  const params = new URLSearchParams({ path });
  if (filterVM) params.set('filter', 'vm');
  return fetchAPI<BrowseResult>(`/browse?${params.toString()}`);
};
