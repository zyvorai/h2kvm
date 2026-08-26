// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { fetchAPI } from './client';

export interface HostInfo {
  hostname: string;
  os_name: string;
  os_id: string;
  os_version: string;
  kernel: string;
  uptime_seconds: number;
  uptime_human: string;
  load_1m: string;
  load_5m: string;
  load_15m: string;
  cpu_cores: number;
  cpu_model: string;
  mem_total_mb: number;
  mem_used_mb: number;
  mem_available_mb: number;
  mem_percent: number;
  swap_total_mb: number;
  swap_used_mb: number;
  disk_total: string;
  disk_used: string;
  disk_avail: string;
  disk_percent: string;
  libvirt_vms: string[];
  libvirt_vm_count: number;
  libvirt_running: number;
  disks?: { name: string; size: string; mountpoint: string; fstype: string; used: string; avail: string; percent: string }[];
  kvm_available: boolean;
  qemu_version: string;
  k8s_available: boolean;
  k8s_endpoint?: string;
  k8s_version?: string;
  k8s_node_count?: number;
  k8s_nodes?: { name: string; status: string; roles: string }[];
  k8s_pod_count?: number;
  k3s?: boolean;
  kubevirt_available?: boolean;
  kubevirt_vmi_count?: number;
}

export const getHostInfo = () =>
  fetchAPI<HostInfo>('/host/info');
