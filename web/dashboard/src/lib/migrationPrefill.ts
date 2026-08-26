// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import type { MigrationConfig } from '../types/job';
import type { MigrationPreset } from './migrationPresets';

const STORAGE_KEY = 'h2kweb_migration_prefill';

export type MigrationPrefillSource = 'local' | 'vsphere' | 'azure' | 'ec2';
export type MigrationPrefillStep = 'source' | 'config' | 'review';

export type MigrationPrefill = {
  source?: MigrationPrefillSource;
  step?: MigrationPrefillStep;
  config?: Partial<MigrationConfig>;
  note?: string;
  from_preset?: string;
};

export function mergeMigrationConfig(
  prev: MigrationConfig,
  fields: Partial<MigrationConfig>
): MigrationConfig {
  const next: MigrationConfig = { ...prev, ...fields };
  if (fields.deploy_k8s === true) {
    next.deploy_openstack = false;
    next.emit_domain_xml = false;
    next.virsh_define = false;
    next.libvirt_test = false;
  }
  if (fields.deploy_openstack === true) {
    next.deploy_k8s = false;
    next.emit_domain_xml = false;
    next.virsh_define = false;
    next.libvirt_test = false;
  }
  if (
    fields.emit_domain_xml === true ||
    fields.virsh_define === true ||
    fields.libvirt_test === true
  ) {
    next.deploy_k8s = false;
    next.deploy_openstack = false;
  }
  return next;
}

export function saveMigrationPrefill(data: MigrationPrefill): void {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

export function hasMigrationPrefill(): boolean {
  try {
    return !!sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return false;
  }
}

export function consumeMigrationPrefill(): MigrationPrefill | null {
  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  sessionStorage.removeItem(STORAGE_KEY);
  try {
    return JSON.parse(raw) as MigrationPrefill;
  } catch {
    return null;
  }
}

export function buildPrefillFromPreset(preset: MigrationPreset): MigrationPrefill {
  return {
    from_preset: preset.name,
    config: preset.config,
    step: 'config',
    note:
      `Preset "${preset.name}" applied. Pick a source in step 1 if needed, then review flags before submit.`,
  };
}

export function buildPrefillForProviderSource(): MigrationPrefill {
  return {
    step: 'source',
    note:
      'Choose vSphere, Azure, or EC2 (requires a connected provider). Local disk images use Local File.',
  };
}

export function buildPrefillForLocalDisk(): MigrationPrefill {
  return {
    source: 'local',
    step: 'source',
    note: 'Browse or upload a VMDK, OVA, VHD, or QCOW2 on the server.',
  };
}
