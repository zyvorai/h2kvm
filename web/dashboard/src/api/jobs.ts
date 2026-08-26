// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { fetchAPI } from './client';
import type { Job, JobStats, MigrationConfig } from '../types/job';

/** Strip tri-state form values before JSON to Go (WinSecureBoot is *bool). */
function migrationConfigForAPI(config: MigrationConfig): MigrationConfig {
  const raw = { ...config } as Record<string, unknown>;
  const sb = raw.win_secure_boot;
  if (sb === 'auto' || sb === '' || sb === undefined) {
    delete raw.win_secure_boot;
  } else if (sb === 'true' || sb === true) {
    raw.win_secure_boot = true;
  } else if (sb === 'false' || sb === false) {
    raw.win_secure_boot = false;
  }
  return raw as unknown as MigrationConfig;
}

export const listJobs = () =>
  fetchAPI<Job[]>('/jobs');

export const getJob = (id: string) =>
  fetchAPI<Job>(`/jobs/${id}`);

export const getJobStats = () =>
  fetchAPI<JobStats>('/jobs/stats');

export const cancelJob = (id: string) =>
  fetchAPI<{ message: string }>(`/jobs/${id}/cancel`, { method: 'POST' });

export const getJobLogs = (id: string) =>
  fetchAPI<{ job_id: string; lines: string[] }>(`/jobs/${id}/logs`);

export const submitMigration = (config: MigrationConfig) =>
  fetchAPI<{ job_id: string; message: string }>('/migrations/submit', {
    method: 'POST',
    body: JSON.stringify(migrationConfigForAPI(config)),
  });

export const previewConfig = (config: MigrationConfig) =>
  fetchAPI<{ yaml: string }>('/migrations/preview', {
    method: 'POST',
    body: JSON.stringify(migrationConfigForAPI(config)),
  });
