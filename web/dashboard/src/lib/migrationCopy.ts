// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

/** Shared labels for the hyper2kvm migration pipeline (dashboard + docs parity). */

export type MigrationDeployTarget = 'libvirt' | 'kubevirt' | 'openstack' | 'none';

export const MIGRATION_ENGINE = 'hyper2kvm';
export const MIGRATION_CLI = 'h2kvmctl';

export const MIGRATION_PIPELINE_TITLE = 'Full Migration Pipeline';
export const MIGRATION_PIPELINE_SUBTITLE = 'Export → Convert → Fix guest OS → Deploy';

export const MIGRATION_PIPELINE_STAGES = ['Export', 'Convert', 'Fix OS', 'Deploy'] as const;

export const MIGRATION_PIPELINE_BANNER =
  'Runs on this host via hyper2kvm (h2kvmctl). Libvirt deploy uses virsh define + domain XML — not virt-install.';

export const MIGRATION_GUEST_FIXES_HINT = 'Applied inside hyper2kvm guest repair';

export const MIGRATION_NETWORK_HINT =
  'Libvirt network name (default). Ignored for KubeVirt and OpenStack deploy.';

export const MIGRATION_DEPLOY_TARGET_LABEL = 'Deploy target (hyper2kvm stage)';

export type DeployTargetOption = {
  value: MigrationDeployTarget | '';
  label: string;
  description: string;
};

export const MIGRATION_DEPLOY_TARGETS: DeployTargetOption[] = [
  {
    value: 'libvirt',
    label: 'Libvirt / KVM (hyper2kvm · virsh define)',
    description: 'Defines a libvirt domain from hyper2kvm-generated XML (VirtIO Linux, SATA/e1000e Windows).',
  },
  {
    value: 'kubevirt',
    label: 'KubeVirt (Kubernetes VM)',
    description: 'Uploads disk and creates a VirtualMachine via deploy_k8s.',
  },
  {
    value: 'openstack',
    label: 'OpenStack (Glance + optional Nova)',
    description: 'Uploads QCOW2 to Glance via deploy_openstack.',
  },
  {
    value: 'none',
    label: 'No deployment (convert only)',
    description: 'Convert and fix guest OS; leave QCOW2 on disk.',
  },
];

export function deployTargetLabel(value: string): string {
  const found = MIGRATION_DEPLOY_TARGETS.find((t) => t.value === value);
  if (found) return found.label;
  if (value === '') return 'None (export only)';
  return value;
}

/** Progress stage labels for provider export jobs */
export const MIGRATION_JOB_STAGES = {
  exportOnly: ['Exporting VM'] as const,
  full: ['Exporting VM', 'Converting disk', 'Fixing guest OS', 'Deploying VM'] as const,
};

/** Backend pipeline phase ids (daemon/jobs/h2kvm_progress.go). */
export const MIGRATION_JOB_PHASE_IDS = [
  'export',
  'inspect',
  'fix',
  'convert',
  'validate',
  'deploy',
] as const;

export type MigrationJobPhaseId = (typeof MIGRATION_JOB_PHASE_IDS)[number];

const JOB_PHASE_ALIASES: Record<string, MigrationJobPhaseId> = {
  downloading: 'export',
  exporting: 'export',
  connecting: 'export',
  discovering: 'inspect',
  inspecting: 'inspect',
  fixing: 'fix',
  converting: 'convert',
  validating: 'validate',
  deploying: 'deploy',
  complete: 'deploy',
  done: 'deploy',
};

export function normalizeJobPhase(phase: string): MigrationJobPhaseId | string {
  const p = (phase || '').toLowerCase().replace(/[^a-z]/g, '');
  if ((MIGRATION_JOB_PHASE_IDS as readonly string[]).includes(p)) return p as MigrationJobPhaseId;
  return JOB_PHASE_ALIASES[p] || p;
}

export const MIGRATION_JOB_PHASE_LABELS: Record<MigrationJobPhaseId, string> = {
  export: 'Export',
  inspect: 'Inspect',
  fix: 'Fix guest OS',
  convert: 'Convert',
  validate: 'Validate',
  deploy: 'Deploy',
};

export function jobPhaseLabel(phase: string): string {
  const id = normalizeJobPhase(phase);
  if (id in MIGRATION_JOB_PHASE_LABELS) return MIGRATION_JOB_PHASE_LABELS[id as MigrationJobPhaseId];
  return phase || '—';
}

/** Index 0–3 into MIGRATION_PIPELINE_STAGES for high-level job UI. */
export function migrationPipelineStageIndex(phase: string): number {
  switch (normalizeJobPhase(phase)) {
    case 'export':
    case 'inspect':
      return 0;
    case 'convert':
      return 1;
    case 'fix':
    case 'validate':
      return 2;
    case 'deploy':
      return 3;
    default:
      return 0;
  }
}

export function migrationPipelineStageLabel(phase: string): string {
  const idx = migrationPipelineStageIndex(phase);
  return MIGRATION_PIPELINE_STAGES[idx] ?? MIGRATION_PIPELINE_STAGES[0];
}
