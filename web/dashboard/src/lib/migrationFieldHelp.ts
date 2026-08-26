// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

/** Contextual help copy for migration YAML / export fields. */

export type MigrationFieldHelpTopic = 'virsh_define' | 'fstab_mode' | 'deploy_target';

export const MIGRATION_FIELD_HELP: Record<
  MigrationFieldHelpTopic,
  { title: string; body: string }
> = {
  virsh_define: {
    title: 'virsh define',
    body:
      'Defines a libvirt domain from hyper2kvm-generated XML on this host. This is the supported libvirt deploy path — not virt-install. Requires emit_domain_xml and a reachable libvirtd.',
  },
  fstab_mode: {
    title: 'fstab mode',
    body:
      'How h2kvmctl rewrites /etc/fstab inside the guest before first boot on KVM. stabilize-all converts device paths to UUID (recommended for Linux). uuid is a lighter pass; none skips fstab edits.',
  },
  deploy_target: {
    title: 'Deploy target',
    body:
      'Where hyper2kvm deploys after convert + guest fix. Libvirt uses virsh define; KubeVirt uploads disk + creates a VM; OpenStack uploads to Glance (optional Nova boot). None leaves QCOW2 on disk only.',
  },
};

export function fieldHelpTopicForKey(key: string): MigrationFieldHelpTopic | undefined {
  if (key === 'virsh_define') return 'virsh_define';
  if (key === 'fstab_mode') return 'fstab_mode';
  return undefined;
}
