// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

export type ProviderType = 'vsphere' | 'azure' | 'ec2';

export interface ProviderConfig {
  id: string;
  type: ProviderType;
  name: string;
  endpoint: string;
  username?: string;
  password?: string;
  region?: string;
  insecure?: boolean;
  metadata?: Record<string, string>;
}

export interface VMInfo {
  provider: ProviderType;
  id: string;
  name: string;
  state: string;
  location: string;
  guest_os: string;
  memory_mb: number;
  num_cpus: number;
  storage_gb: number;
  ip_addresses?: string[];
  created_at?: string;
  tags?: Record<string, string>;
  disks?: DiskInfo[];
}

export interface DiskInfo {
  id: string;
  name: string;
  size_gb: number;
  path: string;
  is_root: boolean;
}

export interface ProviderStatus {
  id: string;
  type: ProviderType;
  name: string;
  connected: boolean;
  vm_count?: number;
  error?: string;
  saved?: boolean;
}
