// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useNavigate, Link } from 'react-router-dom';
import { ArrowRightLeft, Server, FolderOpen, BookOpen, ChevronRight } from 'lucide-react';
import { MigrationPipelineBanner } from '../components/MigrationPipelineBanner';
import { MIGRATION_PIPELINE_SUBTITLE } from '../lib/migrationCopy';
import {
  buildPrefillForLocalDisk,
  buildPrefillForProviderSource,
  buildPrefillFromPreset,
  saveMigrationPrefill,
} from '../lib/migrationPrefill';
import { BUILTIN_PRESETS } from '../lib/migrationPresets';
import { TahoeHero } from '../components/ui/TahoeHero';

const PATHS = [
  {
    id: 'provider' as const,
    title: 'From provider VM',
    description: 'Export from vSphere, Azure, or EC2. Connect providers first, then select VMs in the wizard.',
    gradient: 'from-blue-500 to-indigo-700',
    icon: Server,
    recommended: true,
  },
  {
    id: 'local' as const,
    title: 'From disk image (h2kvmctl YAML)',
    description: 'Local VMDK, OVA, VHD, or QCOW2 on the server. Full control over guest fixes and deploy flags.',
    gradient: 'from-blue-500 to-indigo-700',
    icon: FolderOpen,
  },
];

export function MigrationEntryPage() {
  const navigate = useNavigate();

  return (
    <div>
      <TahoeHero
        icon={<ArrowRightLeft className="w-5 h-5 text-emerald-300" />}
        title="Migrate"
        subtitle={`${MIGRATION_PIPELINE_SUBTITLE} — choose how to start`}
      />
      <MigrationPipelineBanner className="mb-6" />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
        {PATHS.map((path) => {
          const Icon = path.icon;
          return (
            <button
              key={path.id}
              type="button"
              onClick={() => {
                if (path.id === 'provider') {
                  saveMigrationPrefill(buildPrefillForProviderSource());
                } else {
                  saveMigrationPrefill(buildPrefillForLocalDisk());
                }
                navigate('/migrate/wizard');
              }}
              className="text-left p-5 rounded-xl border border-white/[0.08] tahoe-glass-card hover:border-white/30 hover:scale-[1.01] transition-all group"
            >
              <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${path.gradient} flex items-center justify-center mb-3 shadow-lg`}>
                <Icon className="w-6 h-6 text-white" />
              </div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm font-bold text-white">{path.title}</span>
                {path.recommended && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-500/15 text-blue-300 font-medium">
                    recommended
                  </span>
                )}
              </div>
              <p className="text-xs text-white/55 leading-relaxed mb-3">{path.description}</p>
              <span className="text-xs text-blue-400 group-hover:text-blue-300 inline-flex items-center gap-1">
                Continue <ChevronRight className="w-3.5 h-3.5" />
              </span>
            </button>
          );
        })}
      </div>

      <p className="text-xs text-white/45 mb-6">
        First time?{' '}
        <Link to="/providers" className="text-emerald-400 hover:text-emerald-300 font-medium">
          Connect a provider
        </Link>{' '}
        before exporting VMs, or pick disk / preset paths below.
      </p>

      <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
        <div className="flex items-center gap-2 mb-3">
          <BookOpen className="h-4 w-4 text-purple-400" />
          <h3 className="text-sm font-semibold text-white">From preset</h3>
        </div>
        <p className="text-xs text-white/45 mb-4">
          Open a built-in preset to jump to Configure with h2kvmctl flags pre-set. Custom presets are saved in the wizard.
        </p>
        <div className="flex flex-wrap gap-2">
          {BUILTIN_PRESETS.map((preset) => (
            <button
              key={preset.name}
              type="button"
              onClick={() => {
                saveMigrationPrefill(buildPrefillFromPreset(preset));
                navigate('/migrate/wizard');
              }}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-white/[0.08]/50 hover:bg-white/[0.04] border border-white/[0.12]/50 rounded-lg text-xs text-white/75 hover:text-white transition-colors"
            >
              <BookOpen className="h-3 w-3 text-purple-400" />
              {preset.name}
              <span className="text-[10px] text-blue-400 ml-1">Open in Migrate</span>
            </button>
          ))}
        </div>
      </div>

      <p className="text-[11px] text-white/45 mt-6 text-center">
        All paths use h2kvm (h2kvmctl). Libvirt deploy is virsh define — not virt-install.
      </p>
    </div>
  );
}
