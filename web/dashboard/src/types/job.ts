// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

export type JobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface Job {
  id: string;
  config: MigrationConfig;
  status: JobStatus;
  progress?: JobProgress;
  log_lines?: string[];
  error?: string;
  pid?: number;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface JobProgress {
  phase: string;
  percent_complete: number;
  current_step: string;
  bytes_processed?: number;
  total_bytes?: number;
  rate?: string;
  eta?: string;
}

export interface JobStats {
  total: number;
  pending: number;
  running: number;
  completed: number;
  failed: number;
  cancelled: number;
}

export interface MigrationConfig {
  command: string;
  vmdk?: string;
  ova?: string;
  ovf?: string;
  vhd?: string;
  vsphere_host?: string;
  vsphere_username?: string;
  vsphere_password?: string;
  vsphere_insecure?: boolean;
  vm_path?: string;
  datacenter?: string;
  vs_action?: string;
  azure_subscription_id?: string;
  azure_resource_group?: string;
  azure_vm_name?: string;
  output_dir?: string;
  out_format?: string;
  to_output?: string;
  flatten?: boolean;
  compress?: boolean;
  fstab_mode?: string;
  regen_initramfs?: boolean;
  update_grub?: boolean;
  remove_vmware_tools?: boolean;
  enable_rdp?: boolean;
  guest_os?: string;
  serial_console?: boolean;
  uefi?: boolean;
  emit_domain_xml?: boolean;
  virsh_define?: boolean;
  vm_name?: string;
  memory?: number;
  vcpus?: number;
  libvirt_test?: boolean;
  keep_domain?: boolean;
  qemu_test?: boolean;
  deploy_k8s?: boolean;
  namespace?: string;
  deploy_openstack?: boolean;
  glance_name?: string;
  openstack_description?: string;
  openstack_visibility?: string;
  os_cloud?: string;
  os_auth_url?: string;
  os_username?: string;
  os_password?: string;
  os_project_name?: string;
  openstack_boot_instance?: boolean;
  openstack_server_name?: string;
  openstack_flavor?: string;
  openstack_network?: string;
  openstack_key_name?: string;
  openstack_security_group?: string;
  openstack_availability_zone?: string;
  openstack_wait?: boolean;
  compress_level?: number;
  raw?: string;
  allowed_dirs?: string[];
  dry_run?: boolean;
  verbose?: number;
  report?: string;
  // Encryption
  luks_passphrase?: string;
  luks_keyfile?: string;
  clevis_unlock?: boolean;
  win_tpm?: boolean;
  /** Form may use 'auto' | 'true' | 'false' strings; sanitize before API submit. */
  win_secure_boot?: boolean | 'auto' | 'true' | 'false';
}
