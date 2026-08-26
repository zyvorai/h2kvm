// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { fetchAPI } from './client';
import type { ProviderConfig, ProviderStatus, VMInfo } from '../types/provider';

export const listProviders = () =>
  fetchAPI<ProviderStatus[]>('/providers');

export const addProvider = (config: ProviderConfig) =>
  fetchAPI<{ id: string; message: string }>('/providers', {
    method: 'POST',
    body: JSON.stringify(config),
  });

export const testProvider = (config: ProviderConfig) =>
  fetchAPI<{ success: boolean; error?: string }>('/providers/test', {
    method: 'POST',
    body: JSON.stringify(config),
  });

export const deleteProvider = (id: string) =>
  fetchAPI<{ message: string }>(`/providers/${id}`, { method: 'DELETE' });

export const listVMs = (providerId: string, name?: string) => {
  const params = name ? `?name=${encodeURIComponent(name)}` : '';
  return fetchAPI<VMInfo[]>(`/providers/${providerId}/vms${params}`);
};

export const getVM = (providerId: string, vmId: string) =>
  fetchAPI<VMInfo>(`/providers/${providerId}/vms/${vmId}`);
