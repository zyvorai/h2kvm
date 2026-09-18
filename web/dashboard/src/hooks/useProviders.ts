// Copyright (c) 2026 ZyvorAI Labs Private Limited.
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
// https://zyvor.dev · info@zyvor.dev

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as providersApi from '../api/providers';
import type { ProviderConfig } from '../types/provider';

export function useProviders() {
  return useQuery({
    queryKey: ['providers'],
    queryFn: providersApi.listProviders,
  });
}

export function useAddProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (config: ProviderConfig) => providersApi.addProvider(config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['providers'] });
    },
  });
}

export function useTestProvider() {
  return useMutation({
    mutationFn: (config: ProviderConfig) => providersApi.testProvider(config),
  });
}

export function useDeleteProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => providersApi.deleteProvider(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['providers'] });
    },
  });
}

export function useVMs(providerId: string, name?: string) {
  return useQuery({
    queryKey: ['vms', providerId, name],
    queryFn: () => providersApi.listVMs(providerId, name),
    enabled: !!providerId,
  });
}
