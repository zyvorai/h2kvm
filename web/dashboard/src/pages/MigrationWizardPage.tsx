// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useState, useRef, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { LabelWithHelp } from '../components/FieldHelp';
import { fieldHelpTopicForKey } from '../lib/migrationFieldHelp';
import { useQuery } from '@tanstack/react-query';
import {
  ChevronRight, Play, Eye, Upload, FolderOpen, Server, Cloud, Monitor,
  HardDrive, ChevronUp, ChevronDown as ChevronDownIcon, ArrowLeft, FileText,
  CheckCircle, AlertCircle, UploadCloud, Save, Trash2, BookOpen,
} from 'lucide-react';
import { useProviders } from '../hooks/useProviders';
import { useSubmitMigration, usePreviewConfig } from '../hooks/useJobs';
import { VMBrowser } from '../components/VMBrowser';
import { MigrationPipelineBanner } from '../components/MigrationPipelineBanner';
import { TahoeHero } from '../components/ui/TahoeHero';
import { useAppStore } from '../stores/app';
import { browsePath } from '../api/browse';
import type { MigrationConfig } from '../types/job';
import { MIGRATION_PIPELINE_SUBTITLE } from '../lib/migrationCopy';
import { consumeMigrationPrefill, mergeMigrationConfig } from '../lib/migrationPrefill';
import {
  BUILTIN_PRESETS,
  loadCustomPresets,
  saveCustomPresets,
  type MigrationPreset,
} from '../lib/migrationPresets';

type SourceType = 'local' | 'vsphere' | 'azure' | 'ec2';
type Step = 'source' | 'config' | 'review';

const STEPS: { id: Step; label: string }[] = [
  { id: 'source', label: 'Source' },
  { id: 'config', label: 'Configure' },
  { id: 'review', label: 'Review' },
];

const SOURCE_OPTIONS: { type: SourceType; label: string; icon: React.ElementType; desc: string; gradient: string }[] = [
  { type: 'local', label: 'Local File', icon: FolderOpen, desc: 'Browse VMDK, OVA, VHD files on the server', gradient: 'from-blue-600 to-indigo-900' },
  { type: 'vsphere', label: 'VMware vSphere', icon: Server, desc: 'Select from connected vCenter', gradient: 'from-blue-600 to-blue-800' },
  { type: 'azure', label: 'Microsoft Azure', icon: Cloud, desc: 'Select from Azure subscription', gradient: 'from-cyan-600 to-blue-800' },
  { type: 'ec2', label: 'AWS EC2', icon: Monitor, desc: 'Select from EC2 instances', gradient: 'from-orange-600 to-amber-800' },
];

// All YAML config fields organized by category
const CONFIG_CATEGORIES = [
  {
    name: 'Output',
    expanded: true,
    fields: [
      { key: 'output_dir', label: 'Output Directory', type: 'text', placeholder: '/tmp/h2kweb-output' },
      { key: 'out_format', label: 'Output Format', type: 'select', options: ['qcow2', 'raw', 'vdi'] },
      { key: 'to_output', label: 'Output Filename', type: 'text', placeholder: 'Auto from source' },
    ],
  },
  {
    name: 'Processing',
    expanded: true,
    fields: [
      { key: 'flatten', label: 'Flatten Snapshots', type: 'toggle' },
      { key: 'compress', label: 'Compress Output', type: 'toggle' },
      { key: 'compress_level', label: 'Compress Level (0-22)', type: 'number', placeholder: '0' },
    ],
  },
  {
    name: 'Guest Fixes',
    expanded: true,
    fields: [
      { key: 'fstab_mode', label: 'fstab Mode', type: 'select', options: ['stabilize-all', 'uuid', 'none'] },
      { key: 'regen_initramfs', label: 'Regenerate Initramfs', type: 'toggle' },
      { key: 'update_grub', label: 'Update GRUB', type: 'toggle' },
      { key: 'remove_vmware_tools', label: 'Remove VMware Tools', type: 'toggle' },
      { key: 'enable_rdp', label: 'Enable Remote Desktop (RDP)', type: 'toggle' },
      { key: 'guest_os', label: 'Guest OS', type: 'select', options: ['', 'linux', 'windows'] },
      { key: 'serial_console', label: 'Serial Console (COM1)', type: 'toggle' },
      { key: 'uefi', label: 'UEFI firmware', type: 'toggle' },
    ],
  },
  {
    name: 'Libvirt (h2kvm · virsh define)',
    expanded: false,
    fields: [
      { key: 'emit_domain_xml', label: 'Emit Domain XML', type: 'toggle' },
      { key: 'virsh_define', label: 'Define VM (virsh define)', type: 'toggle' },
      { key: 'libvirt_test', label: 'Start VM (virsh start)', type: 'toggle' },
      { key: 'vm_name', label: 'VM Name', type: 'text', placeholder: 'Auto from source' },
      { key: 'memory', label: 'Memory (MB)', type: 'number', placeholder: 'From source' },
      { key: 'vcpus', label: 'vCPUs', type: 'number', placeholder: 'From source' },
    ],
  },
  {
    name: 'Kubernetes',
    expanded: false,
    fields: [
      { key: 'deploy_k8s', label: 'Deploy to KubeVirt', type: 'toggle' },
      { key: 'namespace', label: 'Namespace', type: 'text', placeholder: 'default' },
    ],
  },
  {
    name: 'OpenStack',
    expanded: false,
    fields: [
      { key: 'deploy_openstack', label: 'Upload to Glance', type: 'toggle' },
      { key: 'glance_name', label: 'Glance image name', type: 'text', placeholder: 'Same as VM name if empty' },
      { key: 'os_cloud', label: 'OS_CLOUD (clouds.yaml)', type: 'text', placeholder: 'production' },
      { key: 'openstack_description', label: 'Image description', type: 'text' },
      {
        key: 'openstack_visibility',
        label: 'Visibility',
        type: 'select',
        options: ['private', 'shared', 'public'],
      },
      { key: 'openstack_boot_instance', label: 'Boot Nova instance', type: 'toggle' },
      { key: 'openstack_flavor', label: 'Nova flavor', type: 'text', placeholder: 'm1.medium' },
      { key: 'openstack_network', label: 'Neutron network UUID', type: 'text' },
      { key: 'openstack_key_name', label: 'Keypair name', type: 'text' },
      { key: 'openstack_server_name', label: 'Nova server name', type: 'text', placeholder: '<glance-name>-instance' },
      { key: 'openstack_security_group', label: 'Security group', type: 'text' },
      { key: 'openstack_availability_zone', label: 'Availability zone', type: 'text' },
      { key: 'openstack_wait', label: 'Wait for ACTIVE', type: 'toggle' },
    ],
  },
  {
    name: 'Disk Encryption',
    expanded: false,
    fields: [
      { key: 'luks_passphrase', label: 'LUKS Passphrase', type: 'password', placeholder: 'Leave empty if not encrypted' },
      { key: 'luks_keyfile', label: 'LUKS Keyfile', type: 'file_upload', placeholder: 'Server path or upload from browser' },
      { key: 'clevis_unlock', label: 'Clevis/NBDE Auto-unlock (Tang/TPM2)', type: 'toggle' },
      { key: 'win_tpm', label: 'Windows TPM 2.0', type: 'toggle' },
      {
        key: 'win_secure_boot',
        label: 'UEFI Secure Boot (auto / on / off)',
        type: 'select',
        options: ['auto', 'true', 'false'],
      },
    ],
  },
  {
    name: 'Advanced',
    expanded: false,
    fields: [
      { key: 'dry_run', label: 'Dry Run', type: 'toggle' },
      { key: 'verbose', label: 'Verbose Level (0-3)', type: 'number', placeholder: '0' },
      { key: 'report', label: 'Report Path', type: 'text', placeholder: 'e.g. migration-report.md (empty=no report)' },
    ],
  },
];

export function MigrationWizardPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>('source');
  const [sourceType, setSourceType] = useState<SourceType | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [prefillNote, setPrefillNote] = useState<string | undefined>();
  const [config, setConfig] = useState<MigrationConfig>({
    command: 'local', output_dir: '/tmp/h2kweb-output', out_format: 'qcow2',
    flatten: true, compress: true,
    regen_initramfs: true, update_grub: true, remove_vmware_tools: true,
    enable_rdp: true, guest_os: 'linux', serial_console: true,
    emit_domain_xml: true, virsh_define: true, libvirt_test: true, keep_domain: true,
    fstab_mode: 'stabilize-all',
    win_secure_boot: 'auto',
  });
  const { data: providers } = useProviders();
  const { selectedProvider, setSelectedProvider, selectedVMs } = useAppStore();
  const submitMigration = useSubmitMigration();
  const previewConfig = usePreviewConfig();
  const [yamlPreview, setYamlPreview] = useState('');
  const [expandedCats, setExpandedCats] = useState<Record<string, boolean>>(
    Object.fromEntries(CONFIG_CATEGORIES.map((c) => [c.name, c.expanded]))
  );
  const [customPresets, setCustomPresets] = useState<MigrationPreset[]>(loadCustomPresets);
  const [showSavePreset, setShowSavePreset] = useState(false);
  const [presetName, setPresetName] = useState('');

  const allPresets = [...BUILTIN_PRESETS, ...customPresets];

  const updateMigrationConfig = (fields: Partial<MigrationConfig>) => {
    setConfig((prev) => mergeMigrationConfig(prev, fields));
  };

  useEffect(() => {
    const prefill = consumeMigrationPrefill();
    if (!prefill) return;
    if (prefill.config) {
      setConfig((prev) => mergeMigrationConfig(prev, prefill.config!));
    }
    if (prefill.source) setSourceType(prefill.source);
    if (prefill.step) setStep(prefill.step);
    if (prefill.note) setPrefillNote(prefill.note);
  }, []);

  const applyPreset = (preset: MigrationPreset) => {
    updateMigrationConfig(preset.config);
  };

  const saveCurrentAsPreset = () => {
    if (!presetName.trim()) return;
    const newPreset: MigrationPreset = { name: presetName.trim(), builtin: false, config: { ...config } };
    const updated = [...customPresets, newPreset];
    setCustomPresets(updated);
    saveCustomPresets(updated);
    setPresetName('');
    setShowSavePreset(false);
  };

  const deletePreset = (name: string) => {
    const updated = customPresets.filter((p) => p.name !== name);
    setCustomPresets(updated);
    saveCustomPresets(updated);
  };

  const inputClass = "w-full px-3 py-2.5 tahoe-glass-card border border-white/[0.12] rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-sm";
  const labelClass = "block text-xs font-medium text-white/55 mb-1.5";

  const canProceedFromSource = () => {
    if (sourceType === 'local') return !!selectedFile;
    return selectedVMs.length > 0;
  };

  const handleGoToConfig = () => {
    // Auto-set command and source path
    if (sourceType === 'local' && selectedFile) {
      const ext = selectedFile.split('.').pop()?.toLowerCase();
      const cmdMap: Record<string, string> = { vmdk: 'local', ova: 'ova', ovf: 'ovf', vhd: 'vhd', raw: 'local' };
      const keyMap: Record<string, string> = { vmdk: 'vmdk', ova: 'ova', ovf: 'ovf', vhd: 'vhd', raw: 'raw' };
      // Auto-derive vm_name, output to libvirt images dir
      const fileDir = selectedFile.substring(0, selectedFile.lastIndexOf('/')) || '/';
      const fileName = selectedFile.split('/').pop() || 'vm';
      const vmName = fileName.replace(/\.[^.]+$/, '').replace(/[^a-zA-Z0-9_-]/g, '-');
      const outputDir = '/var/lib/libvirt/images';
      // Auto-detect Windows from filename
      const isWindows = /win/i.test(fileName);
      setConfig({
        ...config,
        command: cmdMap[ext || ''] || 'local',
        [keyMap[ext || ''] || 'vmdk']: selectedFile,
        allowed_dirs: [fileDir, fileDir + '/work', outputDir, outputDir + '/work'],
        output_dir: outputDir,
        vm_name: vmName,
        to_output: `${vmName}.qcow2`,
        // Windows auto-detection: disable Linux-specific fixes
        ...(isWindows ? {
          guest_os: 'windows',
          enable_rdp: true,
          fstab_mode: 'noop',
          regen_initramfs: false,
          update_grub: false,
          remove_vmware_tools: false,
          emit_domain_xml: true,
          memory: 8192,
          vcpus: 4,
          serial_console: true,
        } : { guest_os: 'linux', enable_rdp: false }),
      });
    } else if (sourceType === 'vsphere') {
      setConfig({ ...config, command: 'vsphere', vs_action: 'export_vm' });
    } else if (sourceType === 'azure') {
      setConfig({ ...config, command: 'azure' });
    }
    setStep('config');
  };

  const handlePreview = () => {
    previewConfig.mutate(config, {
      onSuccess: (data) => { setYamlPreview(data.yaml); setStep('review'); },
    });
  };

  const toggleCat = (name: string) => setExpandedCats((prev) => ({ ...prev, [name]: !prev[name] }));

  return (
    <div>
      <button
        type="button"
        onClick={() => navigate('/migrate')}
        className="flex items-center gap-1.5 text-sm text-white/55 hover:text-white transition-colors mb-4"
      >
        <ArrowLeft className="h-4 w-4" /> Back to migration hub
      </button>
      <TahoeHero
        icon={<Play className="w-5 h-5 text-blue-300" />}
        title="Migration wizard"
        subtitle={MIGRATION_PIPELINE_SUBTITLE}
      />
      <MigrationPipelineBanner className="mb-4" />
      {prefillNote && (
        <div className="mb-4 rounded-lg border border-blue-500/20 bg-blue-500/5 px-4 py-3 text-xs text-white/75 leading-relaxed">
          {prefillNote}
        </div>
      )}

      {/* Step bar */}
      <div className="flex items-center gap-2 mb-8">
        {STEPS.map((s, i) => (
          <div key={s.id} className="flex items-center gap-2">
            {i > 0 && <ChevronRight className="h-4 w-4 text-white/40" />}
            <button
              onClick={() => setStep(s.id)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                step === s.id ? 'bg-blue-600/20 text-blue-400' : 'text-white/45 hover:text-white/75'
              }`}
            >
              <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                step === s.id ? 'bg-blue-500 text-white' : 'bg-white/[0.08] text-white/55'
              }`}>{i + 1}</span>
              {s.label}
            </button>
          </div>
        ))}
      </div>

      {/* === STEP: SOURCE === */}
      {step === 'source' && (
        <div>
          {/* Source type selection */}
          {!sourceType && (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
              {SOURCE_OPTIONS.map((opt) => {
                const Icon = opt.icon;
                const providerConnected = opt.type === 'local' || providers?.some((p) => p.type === opt.type && p.connected);
                return (
                  <button
                    key={opt.type}
                    onClick={() => {
                      setSourceType(opt.type);
                      if (opt.type !== 'local') {
                        const prov = providers?.find((p) => p.type === opt.type && p.connected);
                        if (prov) setSelectedProvider(prov.id);
                      }
                    }}
                    disabled={opt.type !== 'local' && !providerConnected}
                    className={`text-left p-5 rounded-xl border transition-all hover:scale-[1.02] ${
                      providerConnected
                        ? 'tahoe-glass-card border-white/[0.08] hover:border-white/30 cursor-pointer'
                        : 'tahoe-glass-card opacity-50 border-white/[0.08] opacity-50 cursor-not-allowed'
                    }`}
                  >
                    <div className={`w-10 h-10 rounded-lg bg-gradient-to-br ${opt.gradient} flex items-center justify-center mb-3`}>
                      <Icon className="h-5 w-5 text-white" />
                    </div>
                    <div className="text-sm font-semibold text-white">{opt.label}</div>
                    <div className="text-xs text-white/45 mt-1">{opt.desc}</div>
                    {opt.type !== 'local' && !providerConnected && (
                      <div className="text-xs text-yellow-400 mt-2">Not connected</div>
                    )}
                  </button>
                );
              })}
            </div>
          )}

          {/* Source content */}
          {sourceType && (
            <div>
              <button onClick={() => { setSourceType(null); setSelectedFile(null); }} className="flex items-center gap-1.5 text-sm text-white/55 hover:text-white transition-colors mb-4">
                <ArrowLeft className="h-4 w-4" /> Back to source selection
              </button>

              {sourceType === 'local' ? (
                <LocalSourcePanel selectedFile={selectedFile} onSelect={setSelectedFile} />
              ) : (
                <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
                  {selectedProvider ? (
                    <VMBrowser providerId={selectedProvider} />
                  ) : (
                    <div className="text-center py-8 text-sm text-white/45">No provider connected for {sourceType}</div>
                  )}
                </div>
              )}

              <button
                onClick={handleGoToConfig}
                disabled={!canProceedFromSource()}
                className="mt-6 flex items-center gap-2 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white font-medium rounded-lg py-2.5 px-5 transition-all hover:scale-[1.02] text-sm disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:scale-100"
              >
                Next: Configure
                {sourceType === 'local' && selectedFile && (
                  <span className="text-xs bg-blue-500/30 px-2 py-0.5 rounded-full truncate max-w-[200px]">{selectedFile.split('/').pop()}</span>
                )}
                {sourceType !== 'local' && selectedVMs.length > 0 && (
                  <span className="text-xs bg-blue-500/30 px-2 py-0.5 rounded-full">{selectedVMs.length} VMs</span>
                )}
              </button>
            </div>
          )}
        </div>
      )}

      {/* === STEP: CONFIG === */}
      {step === 'config' && (
        <div>
          {/* Presets */}
          <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4 mb-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <BookOpen className="h-4 w-4 text-purple-400" />
                <span className="text-sm font-semibold text-white">Presets</span>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => navigate('/migrate')}
                  className="flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 transition-colors"
                >
                  <BookOpen className="h-3 w-3" /> Open presets on hub
                </button>
                <button
                  onClick={() => setShowSavePreset(!showSavePreset)}
                  className="flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 transition-colors"
                >
                  <Save className="h-3 w-3" /> Save Current as Preset
                </button>
              </div>
            </div>

            {showSavePreset && (
              <div className="flex gap-2 mb-3">
                <input
                  type="text"
                  value={presetName}
                  onChange={(e) => setPresetName(e.target.value)}
                  placeholder="Preset name..."
                  className="flex-1 px-2.5 py-1.5 tahoe-glass-card border border-white/[0.12] rounded-lg text-white placeholder-white/40 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                  onKeyDown={(e) => { if (e.key === 'Enter') saveCurrentAsPreset(); }}
                />
                <button
                  onClick={saveCurrentAsPreset}
                  disabled={!presetName.trim()}
                  className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs hover:bg-blue-500 transition-colors disabled:opacity-50"
                >
                  Save
                </button>
              </div>
            )}

            <div className="flex flex-wrap gap-2">
              {allPresets.map((preset) => (
                <div key={preset.name} className="flex items-center gap-1">
                  <button
                    onClick={() => applyPreset(preset)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-white/[0.08]/50 hover:bg-white/[0.04] border border-white/[0.12]/50 rounded-lg text-xs text-white/75 hover:text-white transition-colors"
                  >
                    <BookOpen className="h-3 w-3 text-purple-400" />
                    {preset.name}
                    {preset.builtin && <span className="text-[10px] text-white/45 ml-1">(built-in)</span>}
                  </button>
                  {!preset.builtin && (
                    <button
                      onClick={() => deletePreset(preset.name)}
                      className="h-6 w-6 rounded hover:bg-red-500/10 text-white/45 hover:text-red-400 flex items-center justify-center transition-colors"
                      title="Delete preset"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Collapsible categories with all YAML options */}
          <div className="space-y-3">
            {CONFIG_CATEGORIES.map((cat) => (
              <div key={cat.name} className="tahoe-glass-card rounded-xl border border-white/[0.08] overflow-hidden">
                <button
                  onClick={() => toggleCat(cat.name)}
                  className="w-full flex items-center justify-between px-5 py-3 text-sm font-semibold text-white hover:bg-white/[0.04]/20 transition-colors"
                >
                  {cat.name}
                  {expandedCats[cat.name] ? <ChevronUp className="h-4 w-4 text-blue-400" /> : <ChevronDownIcon className="h-4 w-4 text-blue-400" />}
                </button>

                {expandedCats[cat.name] && (
                  <div className="px-5 pb-5 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 animate-fade-in">
                    {cat.fields.map((field) => (
                      <ConfigField
                        key={field.key}
                        field={field}
                        value={(config as unknown as Record<string, unknown>)[field.key]}
                        onChange={(val) =>
                          updateMigrationConfig({ [field.key]: val } as Partial<MigrationConfig>)
                        }
                        inputClass={inputClass}
                        labelClass={labelClass}
                      />
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="flex gap-3 mt-6">
            <button onClick={() => setStep('source')} className="px-4 py-2.5 rounded-lg border border-white/[0.12] text-white/75 hover:bg-white/[0.04] transition-colors text-sm">
              <ArrowLeft className="h-4 w-4 inline mr-1" /> Back
            </button>
            <button onClick={handlePreview} className="flex items-center gap-2 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white font-medium rounded-lg py-2.5 px-5 transition-all hover:scale-[1.02] text-sm">
              <Eye className="h-4 w-4" /> Review YAML
            </button>
          </div>
        </div>
      )}

      {/* === STEP: REVIEW === */}
      {step === 'review' && (
        <div>
          <div className="tahoe-glass-card rounded-xl border border-white/[0.08] overflow-hidden">
            <div className="flex items-center gap-2 px-5 py-3 border-b border-white/[0.06]">
              <FileText className="h-4 w-4 text-blue-400" />
              <span className="text-sm font-medium text-white/75">h2kvmctl YAML Configuration</span>
            </div>
            <pre className="p-5 text-xs leading-relaxed overflow-auto max-h-96 text-cyan-300 font-mono">{yamlPreview || '# Loading...'}</pre>
          </div>

          {submitMigration.isSuccess && (
            <div className="mt-4 bg-green-500/10 border border-green-500/20 rounded-xl p-4 text-sm text-green-400">
              Migration submitted! Job ID: <span className="font-mono font-bold">{submitMigration.data?.job_id}</span>
            </div>
          )}
          {submitMigration.error && (
            <div className="mt-4 bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-sm text-red-400">
              Error: {submitMigration.error.message}
            </div>
          )}

          <div className="flex gap-3 mt-6">
            <button onClick={() => setStep('config')} className="px-4 py-2.5 rounded-lg border border-white/[0.12] text-white/75 hover:bg-white/[0.04] transition-colors text-sm">
              <ArrowLeft className="h-4 w-4 inline mr-1" /> Back
            </button>
            <button
              onClick={() => submitMigration.mutate(config)}
              disabled={submitMigration.isPending}
              className="flex items-center gap-2 bg-gradient-to-r from-green-600 to-green-700 hover:from-green-500 hover:to-green-600 text-white font-medium rounded-lg py-2.5 px-5 transition-all hover:scale-[1.02] text-sm disabled:opacity-50"
            >
              <Play className="h-4 w-4" />
              {submitMigration.isPending ? 'Submitting...' : 'Start Migration'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// --- Config field renderer ---

function ConfigField({ field, value, onChange, inputClass, labelClass }: {
  field: { key: string; label: string; type: string; placeholder?: string; options?: string[] };
  value: unknown;
  onChange: (val: unknown) => void;
  inputClass: string;
  labelClass: string;
}) {
  const helpTopic = fieldHelpTopicForKey(field.key);
  const labelNode = <LabelWithHelp label={field.label} topic={helpTopic} />;

  if (field.type === 'toggle') {
    return (
      <label className="flex items-center gap-3 cursor-pointer py-2">
        <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} className="accent-blue-500 h-4 w-4 rounded" />
        <span className="text-sm text-white/75">{labelNode}</span>
      </label>
    );
  }
  if (field.type === 'file_upload') {
    return (
      <div>
        <label className={labelClass}>{labelNode}</label>
        <div className="flex gap-1">
          <input type="text" value={(value as string) ?? ''} onChange={(e) => onChange(e.target.value)}
            placeholder={field.placeholder} className={inputClass + ' flex-1'} />
          <label className="px-3 py-2 bg-white/[0.08] hover:bg-white/20 text-white/75 rounded-lg text-sm cursor-pointer flex items-center shrink-0">
            <input type="file" className="hidden" onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              const form = new FormData();
              form.append('file', file);
              form.append('dest_dir', '/var/lib/h2kvm/keys');
              try {
                const res = await fetch('/api/v1/upload', { method: 'POST', body: form });
                if (res.ok) {
                  const data = await res.json();
                  onChange(data.path || `/var/lib/h2kvm/keys/${file.name}`);
                }
              } catch { /* silent */ }
            }} />
            Upload
          </label>
        </div>
      </div>
    );
  }
  if (field.type === 'select') {
    return (
      <div>
        <label className={labelClass}>{labelNode}</label>
        <select value={(value as string) || field.options?.[0] || ''} onChange={(e) => onChange(e.target.value)} className={inputClass}>
          {field.options?.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      </div>
    );
  }
  return (
    <div>
      <label className={labelClass}>{labelNode}</label>
      <input
        type={field.type === 'number' ? 'number' : field.type === 'password' ? 'password' : 'text'}
        value={(value as string) ?? ''}
        onChange={(e) => onChange(field.type === 'number' ? (parseInt(e.target.value) || undefined) : e.target.value)}
        placeholder={field.placeholder}
        className={inputClass}
      />
    </div>
  );
}

// --- Upload helper ---

const ACCEPTED_EXTENSIONS = '.vmdk,.ova,.ovf,.vhd,.vhdx,.qcow2,.raw,.img';

interface UploadResult {
  path: string;
  name: string;
  size: number;
  format: string;
}

type UploadState = 'idle' | 'uploading' | 'complete' | 'error';

interface UploadHandle {
  promise: Promise<UploadResult>;
  abort: () => void;
}

function uploadFile(file: File, onProgress: (pct: number) => void): UploadHandle {
  const xhr = new XMLHttpRequest();

  const promise = new Promise<UploadResult>((resolve, reject) => {
    xhr.open('POST', '/api/v1/upload');
    xhr.withCredentials = true;

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };

    xhr.onload = () => {
      if (xhr.status === 200) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.error || 'Upload failed'));
        } catch {
          reject(new Error(xhr.responseText || 'Upload failed'));
        }
      }
    };
    xhr.onerror = () => reject(new Error('Upload failed — network error'));
    xhr.onabort = () => reject(new Error('Upload cancelled'));

    const formData = new FormData();
    formData.append('file', file);
    xhr.send(formData);
  });

  return { promise, abort: () => xhr.abort() };
}

// --- Chunked / resumable upload ---

const CHUNK_SIZE = 10 * 1024 * 1024; // 10 MB
const CHUNK_RETRY_COUNT = 3;
const CHUNK_RETRY_DELAY = 2000; // 2s
const SESSION_STORAGE_KEY = 'h2kweb_chunked_upload';

interface ChunkedUploadSession {
  upload_id: string;
  filename: string;
  total_chunks: number;
  chunk_size: number;
  file_size: number;
}

interface ChunkedUploadHandle {
  promise: Promise<UploadResult>;
  abort: () => void;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function uploadChunkWithRetry(
  uploadId: string,
  chunkIndex: number,
  blob: Blob,
  retries: number = CHUNK_RETRY_COUNT,
): Promise<void> {
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      const formData = new FormData();
      formData.append('upload_id', uploadId);
      formData.append('chunk_index', String(chunkIndex));
      formData.append('chunk', blob);

      const res = await fetch('/api/v1/upload/chunk', {
        method: 'POST',
        credentials: 'include',
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Upload chunk failed' }));
        throw new Error(err.error || `HTTP ${res.status}`);
      }
      return;
    } catch (err) {
      if (attempt === retries) throw err;
      await sleep(CHUNK_RETRY_DELAY);
    }
  }
}

function chunkedUploadFile(
  file: File,
  onProgress: (pct: number) => void,
  startFromChunk: number = 0,
  existingSession?: ChunkedUploadSession,
): ChunkedUploadHandle {
  let aborted = false;
  const state: { reject: ((err: Error) => void) | null } = { reject: null };

  const promise = (async () => {
    // Step 1: Init session (or reuse existing).
    let session: ChunkedUploadSession;
    if (existingSession) {
      session = existingSession;
    } else {
      const initRes = await fetch('/api/v1/upload/init', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: file.name,
          size: file.size,
          chunk_size: CHUNK_SIZE,
        }),
      });
      if (!initRes.ok) {
        const err = await initRes.json().catch(() => ({ error: 'Init failed' }));
        throw new Error(err.error || 'Failed to initialize upload');
      }
      const initData = await initRes.json();
      session = {
        upload_id: initData.upload_id,
        filename: file.name,
        total_chunks: initData.total_chunks,
        chunk_size: initData.chunk_size,
        file_size: file.size,
      };
    }

    // Persist session for resume on page refresh.
    try {
      sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
    } catch { /* ignore */ }

    // Step 2: Upload chunks sequentially.
    for (let i = startFromChunk; i < session.total_chunks; i++) {
      if (aborted) {
        throw new Error('Upload cancelled');
      }

      const start = i * session.chunk_size;
      const end = Math.min(start + session.chunk_size, file.size);
      const blob = file.slice(start, end);

      await new Promise<void>((resolve, reject) => {
        state.reject = reject;
        uploadChunkWithRetry(session.upload_id, i, blob)
          .then(resolve)
          .catch(reject);
      });

      const pct = Math.round(((i + 1) / session.total_chunks) * 100);
      onProgress(pct);
    }

    // Step 3: Finalize.
    const completeRes = await fetch('/api/v1/upload/complete', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ upload_id: session.upload_id }),
    });
    if (!completeRes.ok) {
      const err = await completeRes.json().catch(() => ({ error: 'Complete failed' }));
      throw new Error(err.error || 'Failed to finalize upload');
    }

    // Clear session storage on success.
    try { sessionStorage.removeItem(SESSION_STORAGE_KEY); } catch { /* ignore */ }

    return (await completeRes.json()) as UploadResult;
  })();

  return {
    promise,
    abort: () => {
      aborted = true;
      if (state.reject) state.reject(new Error('Upload cancelled'));
    },
  };
}

// --- Local source panel (tabs: Browse Server / Upload from Computer) ---

function LocalSourcePanel({ selectedFile, onSelect }: { selectedFile: string | null; onSelect: (path: string) => void }) {
  const [tab, setTab] = useState<'browse' | 'upload'>('browse');

  return (
    <div>
      {/* Tab bar */}
      <div className="flex items-center gap-1 mb-4">
        <button
          onClick={() => setTab('browse')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            tab === 'browse' ? 'bg-white/[0.08]/50 text-white' : 'text-white/55 hover:text-white/90 hover:bg-white/[0.04]/20'
          }`}
        >
          <FolderOpen className="h-4 w-4" /> Browse Server
        </button>
        <button
          onClick={() => setTab('upload')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            tab === 'upload' ? 'bg-white/[0.08]/50 text-white' : 'text-white/55 hover:text-white/90 hover:bg-white/[0.04]/20'
          }`}
        >
          <UploadCloud className="h-4 w-4" /> Upload from Computer
        </button>
      </div>

      {tab === 'browse' ? (
        <FileBrowser selectedFile={selectedFile} onSelect={onSelect} />
      ) : (
        <FileUploadZone onUploaded={(path) => onSelect(path)} />
      )}
    </div>
  );
}

// --- File upload drop zone ---

function FileUploadZone({ onUploaded }: { onUploaded: (path: string) => void }) {
  const [uploadState, setUploadState] = useState<UploadState>('idle');
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [fileName, setFileName] = useState('');
  const [resumable, setResumable] = useState(false);
  const [pendingResume, setPendingResume] = useState<ChunkedUploadSession | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const resumeFileRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<(() => void) | null>(null);

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  };

  // Check for pending chunked upload on mount.
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(SESSION_STORAGE_KEY);
      if (!raw) return;
      const session: ChunkedUploadSession = JSON.parse(raw);
      // Verify the session still exists on the server.
      fetch(`/api/v1/upload/status/${encodeURIComponent(session.upload_id)}`, { credentials: 'include' })
        .then((res) => {
          if (res.ok) return res.json();
          throw new Error('not found');
        })
        .then((data) => {
          if (!data.complete) {
            setPendingResume(session);
            setResumable(true);
          } else {
            sessionStorage.removeItem(SESSION_STORAGE_KEY);
          }
        })
        .catch(() => {
          sessionStorage.removeItem(SESSION_STORAGE_KEY);
        });
    } catch { /* ignore */ }
  }, []);

  const handleCancel = useCallback(() => {
    abortRef.current?.();
    abortRef.current = null;
    setUploadState('idle');
    setProgress(0);
    setError('');
    setFileName('');
  }, []);

  const handleFile = useCallback(async (file: File) => {
    setUploadState('uploading');
    setProgress(0);
    setError('');
    setResult(null);
    setFileName(file.name);

    let handle: UploadHandle | ChunkedUploadHandle;
    if (resumable) {
      handle = chunkedUploadFile(file, setProgress);
    } else {
      handle = uploadFile(file, setProgress);
    }
    abortRef.current = handle.abort;

    try {
      const res = await handle.promise;
      abortRef.current = null;
      setResult(res);
      setUploadState('complete');
      setPendingResume(null);
      onUploaded(res.path);
    } catch (err) {
      abortRef.current = null;
      const msg = (err as Error).message;
      if (msg === 'Upload cancelled') {
        setUploadState('idle');
      } else {
        setError(msg);
        setUploadState('error');
      }
    }
  }, [onUploaded, resumable]);

  const handleResume = useCallback(async (file: File) => {
    if (!pendingResume) return;
    // Check how many chunks are already done.
    setUploadState('uploading');
    setProgress(0);
    setError('');
    setResult(null);
    setFileName(pendingResume.filename);

    try {
      const statusRes = await fetch(`/api/v1/upload/status/${encodeURIComponent(pendingResume.upload_id)}`, { credentials: 'include' });
      if (!statusRes.ok) throw new Error('Session expired');
      const status = await statusRes.json();

      const receivedSet = new Set<number>(status.received_chunks || []);
      // Find the first missing chunk.
      let startChunk = 0;
      for (let i = 0; i < pendingResume.total_chunks; i++) {
        if (!receivedSet.has(i)) { startChunk = i; break; }
        if (i === pendingResume.total_chunks - 1) startChunk = pendingResume.total_chunks;
      }

      const initialPct = Math.round((startChunk / pendingResume.total_chunks) * 100);
      setProgress(initialPct);

      const handle = chunkedUploadFile(file, setProgress, startChunk, pendingResume);
      abortRef.current = handle.abort;

      const res = await handle.promise;
      abortRef.current = null;
      setResult(res);
      setUploadState('complete');
      setPendingResume(null);
      onUploaded(res.path);
    } catch (err) {
      abortRef.current = null;
      const msg = (err as Error).message;
      if (msg === 'Upload cancelled') {
        setUploadState('idle');
      } else {
        setError(msg);
        setUploadState('error');
      }
    }
  }, [pendingResume, onUploaded]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setDragOver(false);
  }, []);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const reset = useCallback(() => {
    setUploadState('idle');
    setProgress(0);
    setResult(null);
    setError('');
    if (inputRef.current) inputRef.current.value = '';
  }, []);

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] overflow-hidden">
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_EXTENSIONS}
        onChange={handleInputChange}
        className="hidden"
      />
      <input
        ref={resumeFileRef}
        type="file"
        accept={ACCEPTED_EXTENSIONS}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleResume(f); }}
        className="hidden"
      />

      {/* Resume banner */}
      {uploadState === 'idle' && pendingResume && (
        <div className="px-4 py-3 bg-amber-500/10 border-b border-amber-500/20 flex items-center gap-3 text-sm">
          <AlertCircle className="h-4 w-4 text-amber-400 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <span className="text-amber-300 font-medium">Incomplete upload: </span>
            <span className="text-white/75 font-mono text-xs truncate">{pendingResume.filename}</span>
            <span className="text-white/45 text-xs ml-2">({formatSize(pendingResume.file_size)})</span>
          </div>
          <button
            type="button"
            onClick={() => resumeFileRef.current?.click()}
            className="text-xs px-3 py-1.5 bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded-lg hover:bg-amber-500/30 transition-colors font-medium"
          >
            Resume
          </button>
          <button
            type="button"
            onClick={() => { setPendingResume(null); try { sessionStorage.removeItem(SESSION_STORAGE_KEY); } catch { /* ignore */ } }}
            className="text-xs text-white/45 hover:text-white/75 transition-colors"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Drop zone */}
      {uploadState === 'idle' && (
        <div>
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            className={`w-full flex flex-col items-center justify-center gap-3 py-16 px-6 cursor-pointer transition-all ${
              dragOver
                ? 'bg-blue-500/10 border-2 border-dashed border-blue-400'
                : 'hover:bg-white/[0.04]/20 border-2 border-dashed border-white/[0.12]'
            } rounded-lg m-4`}
            style={{ width: 'calc(100% - 2rem)' }}
          >
            <UploadCloud className={`h-10 w-10 ${dragOver ? 'text-blue-400' : 'text-blue-400/50'} transition-colors`} />
            <div className="text-sm text-white/75 font-medium">
              Drag & drop VM image here, or click to browse
            </div>
            <div className="text-xs text-white/45">
              Accepts: VMDK, OVA, OVF, VHD, VHDX, QCOW2, RAW, IMG (up to 50 GB)
            </div>
          </button>

          {/* Resumable upload toggle */}
          <div className="px-5 pb-4 flex items-center gap-2">
            <label className="flex items-center gap-2 cursor-pointer text-xs text-white/45 hover:text-white/75 transition-colors">
              <input
                type="checkbox"
                checked={resumable}
                onChange={(e) => setResumable(e.target.checked)}
                className="accent-blue-500 h-3.5 w-3.5 rounded"
              />
              <span>Resumable upload</span>
            </label>
            {resumable && (
              <span className="text-[10px] text-white/40">(chunked, can resume after interruption)</span>
            )}
          </div>
        </div>
      )}

      {/* Uploading state */}
      {uploadState === 'uploading' && (
        <div className="p-6 space-y-4">
          <div className="flex items-center gap-3">
            <Upload className="h-5 w-5 text-blue-400 animate-pulse" />
            <div className="flex-1 min-w-0">
              <div className="text-sm text-white font-medium truncate">{fileName || 'Uploading...'}</div>
              <div className="text-xs text-white/55 mt-0.5">
                {progress}% complete
                {resumable && <span className="ml-2 text-white/40">(resumable)</span>}
              </div>
            </div>
            <span className="text-sm font-mono text-blue-400">{progress}%</span>
            <button
              type="button"
              onClick={handleCancel}
              className="text-xs px-2.5 py-1 bg-red-500/10 text-red-400 border border-red-500/30 rounded-lg hover:bg-red-500/20 transition-colors"
            >
              Cancel
            </button>
          </div>
          <div className="w-full bg-white/[0.08] rounded-full h-2 overflow-hidden">
            <div
              className="bg-gradient-to-r from-blue-500 to-blue-400 h-full rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {/* Complete state */}
      {uploadState === 'complete' && result && (
        <div className="p-6 space-y-3">
          <div className="flex items-center gap-3">
            <CheckCircle className="h-5 w-5 text-green-400" />
            <div className="flex-1">
              <div className="text-sm text-white font-medium">Upload complete</div>
              <div className="text-xs text-white/55 mt-0.5 font-mono">{result.path}</div>
            </div>
            <span className="text-xs text-white/45">{formatSize(result.size)}</span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded font-medium">{result.format.toUpperCase()}</span>
            <span className="text-green-400">Ready for migration</span>
            <button onClick={reset} className="ml-auto text-white/55 hover:text-white transition-colors">
              Upload another
            </button>
          </div>
        </div>
      )}

      {/* Error state */}
      {uploadState === 'error' && (
        <div className="p-6 space-y-3">
          <div className="flex items-center gap-3">
            <AlertCircle className="h-5 w-5 text-red-400" />
            <div className="flex-1">
              <div className="text-sm text-red-400 font-medium">Upload failed</div>
              <div className="text-xs text-white/55 mt-0.5">{error}</div>
            </div>
          </div>
          <button onClick={reset} className="text-xs text-blue-400 hover:text-blue-300 transition-colors">
            Try again
          </button>
        </div>
      )}
    </div>
  );
}

// --- Server file browser ---

function FileBrowser({ selectedFile, onSelect }: { selectedFile: string | null; onSelect: (path: string) => void }) {
  const [currentPath, setCurrentPath] = useState('/');
  const [pathInput, setPathInput] = useState('/');
  const [showAllFiles, setShowAllFiles] = useState(false);
  const { data, isLoading, error } = useQuery({
    queryKey: ['browse', currentPath],
    queryFn: () => browsePath(currentPath),
  });

  const handlePathSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setCurrentPath(pathInput);
  };

  const navigateTo = (path: string) => {
    setCurrentPath(path);
    setPathInput(path);
  };

  const formatSize = (bytes: number) => {
    if (bytes === 0) return '';
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  };

  // Filter entries
  const entries = data?.entries?.filter((e) => {
    if (e.is_dir) return true;
    if (showAllFiles) return true;
    return e.is_vm;
  }) ?? [];

  const vmCount = data?.entries?.filter((e) => !e.is_dir && e.is_vm).length ?? 0;
  const totalCount = data?.entries?.filter((e) => !e.is_dir).length ?? 0;

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] overflow-hidden">
      {/* Path input */}
      <form onSubmit={handlePathSubmit} className="flex items-center gap-2 px-4 py-3 border-b border-white/[0.06]">
        <FolderOpen className="h-4 w-4 text-yellow-400 flex-shrink-0" />
        <input
          type="text"
          value={pathInput}
          onChange={(e) => setPathInput(e.target.value)}
          placeholder="Enter path..."
          className="flex-1 bg-transparent text-sm text-white placeholder-white/40 outline-none"
        />
        <button type="submit" className="text-xs text-blue-400 hover:text-blue-300 font-medium px-2 py-1 rounded hover:bg-blue-500/10 transition-colors">
          Go
        </button>
      </form>

      {/* Breadcrumb */}
      <div className="flex items-center gap-1 px-4 py-2 border-b border-white/[0.08]/20 text-xs overflow-x-auto tahoe-glass-card">
        <button onClick={() => navigateTo('/')} className="text-white/45 hover:text-blue-400 transition-colors">/</button>
        {data?.path?.split('/').filter(Boolean).map((part, i, arr) => {
          const fullPath = '/' + arr.slice(0, i + 1).join('/');
          return (
            <span key={fullPath} className="flex items-center gap-1">
              <ChevronRight className="h-3 w-3 text-white/40" />
              <button onClick={() => navigateTo(fullPath)} className="text-white/55 hover:text-blue-400 transition-colors whitespace-nowrap">
                {part}
              </button>
            </span>
          );
        })}
      </div>

      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-white/[0.08]/20 text-xs">
        <div className="text-white/45">
          {entries.filter(e => e.is_dir).length} dirs
          {vmCount > 0 && <span className="ml-2 text-blue-400">{vmCount} VM files</span>}
          {totalCount > vmCount && <span className="ml-1 text-white/40">/ {totalCount} total</span>}
        </div>
        <label className="flex items-center gap-1.5 cursor-pointer text-white/45 hover:text-white/75 transition-colors">
          <input type="checkbox" checked={showAllFiles} onChange={(e) => setShowAllFiles(e.target.checked)} className="accent-blue-500 h-3 w-3 rounded" />
          Show all files
        </label>
      </div>

      {/* Go up */}
      {data?.parent && data.parent !== data.path && (
        <button
          onClick={() => navigateTo(data.parent)}
          className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-white/55 hover:bg-white/[0.04]/20 hover:text-white transition-colors border-b border-white/[0.08]/10"
        >
          <ArrowLeft className="h-4 w-4" />
          <span className="text-white/45">..</span>
          <span className="text-xs text-white/40 ml-auto">{data.parent}</span>
        </button>
      )}

      {/* File list */}
      <div className="max-h-96 overflow-auto">
        {isLoading && (
          <div className="space-y-1 p-2">
            {[1,2,3,4,5].map((i) => <div key={i} className="skeleton h-10 rounded-lg" />)}
          </div>
        )}
        {error && <div className="p-4 text-sm text-red-400">Error: {(error as Error).message}</div>}
        {!isLoading && entries.length === 0 && (
          <div className="p-8 text-center">
            <FolderOpen className="h-8 w-8 text-yellow-400/30 mx-auto mb-2" />
            <div className="text-sm text-white/45">Empty directory</div>
            <div className="text-xs text-white/40 mt-1">
              {!showAllFiles && totalCount > 0 ? (
                <button onClick={() => setShowAllFiles(true)} className="text-blue-400 hover:underline">
                  Show all {totalCount} files
                </button>
              ) : (
                'No files here'
              )}
            </div>
          </div>
        )}
        {entries.map((entry) => {
          const isSelected = !entry.is_dir && selectedFile === entry.path;
          return (
            <button
              key={entry.path}
              onClick={() => {
                if (entry.is_dir) {
                  navigateTo(entry.path);
                } else {
                  onSelect(entry.path);
                }
              }}
              className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors border-b border-white/[0.08]/10 ${
                isSelected
                  ? 'bg-blue-600/15 text-blue-300'
                  : entry.is_vm
                    ? 'text-white hover:bg-white/[0.04]/30'
                    : 'text-white/55 hover:bg-white/[0.04]/20 hover:text-white/90'
              }`}
            >
              {entry.is_dir ? (
                <FolderOpen className="h-4 w-4 text-yellow-500 flex-shrink-0" />
              ) : entry.is_vm ? (
                <HardDrive className="h-4 w-4 text-blue-400 flex-shrink-0" />
              ) : (
                <FileText className="h-4 w-4 text-blue-400/50 flex-shrink-0" />
              )}
              <span className="flex-1 text-left truncate">{entry.name}</span>
              {entry.is_vm && !entry.is_dir && (
                <span className="text-[10px] font-medium text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded flex-shrink-0">
                  {entry.name.split('.').pop()?.toUpperCase()}
                </span>
              )}
              {!entry.is_dir && entry.size > 0 && (
                <span className="text-xs text-white/45 flex-shrink-0">{formatSize(entry.size)}</span>
              )}
              {isSelected && (
                <span className="inline-flex items-center gap-1 text-xs text-blue-400 flex-shrink-0">
                  <Upload className="h-3 w-3" /> Selected
                </span>
              )}
              {entry.is_dir && <ChevronRight className="h-3.5 w-3.5 text-white/40 flex-shrink-0" />}
            </button>
          );
        })}
      </div>

      {/* Selected file bar */}
      {selectedFile && (
        <div className="px-4 py-3 border-t border-white/[0.06] bg-blue-600/5 flex items-center gap-2 text-xs">
          <HardDrive className="h-3.5 w-3.5 text-blue-400 flex-shrink-0" />
          <span className="text-blue-400 font-semibold">Selected:</span>
          <span className="text-white truncate font-mono">{selectedFile}</span>
          <span className="text-white/45 ml-auto flex-shrink-0">{selectedFile.split('.').pop()?.toUpperCase()}</span>
        </div>
      )}
    </div>
  );
}
