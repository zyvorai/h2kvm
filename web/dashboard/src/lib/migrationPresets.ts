// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import type { MigrationConfig } from '../types/job';

export interface MigrationPreset {
  name: string;
  builtin: boolean;
  config: Partial<MigrationConfig>;
}

export const PRESETS_STORAGE_KEY = 'h2kweb_migration_presets';

export const BUILTIN_PRESETS: MigrationPreset[] = [
  {
    name: 'VMware Windows 10/11',
    builtin: true,
    config: {
      flatten: true,
      compress: true,
      out_format: 'qcow2',
      fstab_mode: 'noop',
      emit_domain_xml: true,
      vm_name: 'auto',
      guest_os: 'windows',
      enable_rdp: true,
      regen_initramfs: false,
      update_grub: false,
    },
  },
  {
    name: 'VMware Linux (full fixes)',
    builtin: true,
    config: {
      flatten: true,
      compress: true,
      out_format: 'qcow2',
      fstab_mode: 'stabilize-all',
      regen_initramfs: true,
      remove_vmware_tools: true,
      emit_domain_xml: true,
      virsh_define: true,
    },
  },
  {
    name: 'Quick Convert (no fixes)',
    builtin: true,
    config: {
      flatten: true,
      compress: true,
      out_format: 'qcow2',
      fstab_mode: 'noop',
    },
  },
  {
    name: 'LUKS Encrypted Linux',
    builtin: true,
    config: {
      flatten: true,
      compress: true,
      out_format: 'qcow2',
      fstab_mode: 'stabilize-all',
      regen_initramfs: true,
      remove_vmware_tools: true,
      emit_domain_xml: true,
      virsh_define: true,
      luks_passphrase: '',
    },
  },
  {
    name: 'Clevis/NBDE Auto-unlock',
    builtin: true,
    config: {
      flatten: true,
      compress: true,
      out_format: 'qcow2',
      fstab_mode: 'stabilize-all',
      regen_initramfs: true,
      emit_domain_xml: true,
      virsh_define: true,
      clevis_unlock: true,
    },
  },
];

export function loadCustomPresets(): MigrationPreset[] {
  try {
    const raw = localStorage.getItem(PRESETS_STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as MigrationPreset[];
  } catch {
    return [];
  }
}

export function saveCustomPresets(presets: MigrationPreset[]): void {
  try {
    localStorage.setItem(PRESETS_STORAGE_KEY, JSON.stringify(presets));
  } catch {
    console.error('Failed to save presets (localStorage quota exceeded)');
  }
}
