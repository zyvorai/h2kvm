// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as jobsApi from '../api/jobs';
import type { MigrationConfig } from '../types/job';

export function useJobs() {
  return useQuery({
    queryKey: ['jobs'],
    queryFn: jobsApi.listJobs,
    refetchInterval: 5000,
  });
}

export function useJob(id: string) {
  return useQuery({
    queryKey: ['jobs', id],
    queryFn: () => jobsApi.getJob(id),
    refetchInterval: 2000,
    enabled: !!id,
  });
}

export function useJobStats() {
  return useQuery({
    queryKey: ['jobs', 'stats'],
    queryFn: jobsApi.getJobStats,
    refetchInterval: 5000,
  });
}

export function useSubmitMigration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (config: MigrationConfig) => jobsApi.submitMigration(config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

export function useCancelJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => jobsApi.cancelJob(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

export function usePreviewConfig() {
  return useMutation({
    mutationFn: (config: MigrationConfig) => jobsApi.previewConfig(config),
  });
}
