// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { fetchAPI } from './client';

export interface ClusterEntry {
  id: string;
  name: string;
  source: string;
  original_path: string;
  filename: string;
  added_at: string;
  connected: boolean;
  version?: string;
  server_url?: string;
  is_active: boolean;
}

export interface KubeconfigListResponse {
  active: string;
  clusters: ClusterEntry[];
}

export const listKubeconfigs = () =>
  fetchAPI<KubeconfigListResponse>('/kubeconfigs');

export const addKubeconfigByPath = (name: string, path: string) =>
  fetchAPI<ClusterEntry>('/kubeconfigs/add', {
    method: 'POST',
    body: JSON.stringify({ name, path }),
  });

export async function addKubeconfigByUpload(name: string, file: File): Promise<ClusterEntry> {
  const form = new FormData();
  form.append('name', name);
  form.append('kubeconfig', file);

  const res = await fetch('/api/v1/kubeconfigs/add', {
    method: 'POST',
    credentials: 'include',
    body: form,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(body.error || `HTTP ${res.status}`);
  }

  return res.json();
}

export const activateKubeconfig = (id: string) =>
  fetchAPI<{ status: string; active: string }>(`/kubeconfigs/${encodeURIComponent(id)}/activate`, {
    method: 'PUT',
  });

export const deleteKubeconfig = (id: string) =>
  fetchAPI<{ status: string; cluster: string }>(`/kubeconfigs/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
