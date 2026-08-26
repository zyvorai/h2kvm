// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { fetchAPI } from './client';

export interface VMIPResult {
  vm_name: string;
  source: string;
  ips: string[];
  status: string;
}

export interface OpenStackDeployStatus {
  defined: boolean;
  running: boolean;
  status?: string;
  image_id?: string;
  server_id?: string;
  server_name?: string;
}

export interface VMDeployStatus {
  vm_name: string;
  libvirt: { defined: boolean; running: boolean; state?: string };
  kubevirt: { defined: boolean; running: boolean; phase?: string };
  openstack?: OpenStackDeployStatus;
}

export const getVMIP = (vmName: string) =>
  fetchAPI<VMIPResult>(`/deploy/${encodeURIComponent(vmName)}/ip`);

export const getVMStatus = (vmName: string) =>
  fetchAPI<VMDeployStatus>(`/deploy/${encodeURIComponent(vmName)}/status`);
