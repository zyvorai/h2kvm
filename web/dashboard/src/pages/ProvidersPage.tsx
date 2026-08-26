// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Server, Cloud, Monitor, Lock, User, Globe, Key, ChevronDown, ChevronRight, CheckCircle, XCircle, Loader2, LogIn, Cpu, HardDrive, Search, Eye, EyeOff, Plug } from 'lucide-react';
import { useProviders, useAddProvider, useDeleteProvider, useVMs } from '../hooks/useProviders';
import { useAppStore } from '../stores/app';
import type { ProviderConfig, ProviderType, VMInfo } from '../types/provider';
import { EmptyState } from '../components/EmptyState';
import { TahoeHero } from '../components/ui/TahoeHero';

interface ProviderCardDef {
  type: ProviderType;
  name: string;
  description: string;
  icon: React.ElementType;
  gradient: string;
  iconGradient: string;
  fields: FieldDef[];
}

interface FieldDef {
  key: string;
  label: string;
  placeholder: string;
  icon: React.ElementType;
  type?: string;
  meta?: boolean; // stored in metadata
}

const PROVIDERS: ProviderCardDef[] = [
  {
    type: 'vsphere',
    name: 'VMware vSphere',
    description: 'Connect to vCenter Server to discover and migrate VMs from ESXi hosts',
    icon: Server,
    gradient: 'from-blue-600 to-blue-800',
    iconGradient: 'from-blue-500 to-blue-700',
    fields: [
      { key: 'endpoint', label: 'vCenter Host', placeholder: 'vcenter.example.com', icon: Globe },
      { key: 'username', label: 'Username', placeholder: 'administrator@vsphere.local', icon: User },
      { key: 'password', label: 'Password', placeholder: 'Password', icon: Lock, type: 'password' },
      { key: 'datacenter', label: 'Datacenter', placeholder: 'Datacenter1', icon: Server, meta: true },
    ],
  },
  {
    type: 'azure',
    name: 'Microsoft Azure',
    description: 'Connect to Azure subscription to export and migrate virtual machines to KVM',
    icon: Cloud,
    gradient: 'from-cyan-600 to-blue-800',
    iconGradient: 'from-cyan-500 to-blue-600',
    fields: [
      { key: 'subscription_id', label: 'Subscription ID', placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx', icon: Key, meta: true },
      { key: 'resource_group', label: 'Resource Group', placeholder: 'my-resource-group', icon: Server, meta: true },
    ],
  },
  {
    type: 'ec2',
    name: 'AWS EC2',
    description: 'Connect to AWS account to discover EC2 instances and migrate AMIs to KVM',
    icon: Monitor,
    gradient: 'from-orange-600 to-amber-800',
    iconGradient: 'from-orange-500 to-amber-600',
    fields: [
      { key: 'region', label: 'Region', placeholder: 'us-east-1', icon: Globe },
      { key: 'profile', label: 'AWS Profile', placeholder: 'default (optional)', icon: User, meta: true },
    ],
  },
];

export function ProvidersPage() {
  const navigate = useNavigate();
  const { data: providers } = useProviders();
  const addProvider = useAddProvider();
  const deleteProvider = useDeleteProvider();
  const [expandedProvider, setExpandedProvider] = useState<ProviderType | null>(null);

  const isConnected = (type: ProviderType) =>
    providers?.some((p) => p.type === type && p.connected) ?? false;

  const getProviderId = (type: ProviderType) =>
    providers?.find((p) => p.type === type)?.id;

  const hasConnectedProvider = PROVIDERS.some((p) => isConnected(p.type));

  return (
    <div>
      <TahoeHero
        icon={<Server className="w-5 h-5 text-blue-300" />}
        title="Providers"
        subtitle="Connect to your cloud providers to discover and migrate virtual machines"
      />

      {!hasConnectedProvider && (
        <EmptyState
          icon={<Plug className="w-10 h-10 text-white/45" />}
          title="No providers connected yet"
          description="Connect vSphere, Azure, or AWS below to discover VMs. Or start from a local disk image on the Migrate hub."
          className="mb-8"
          actions={[
            {
              label: 'Connect vSphere',
              onClick: () => setExpandedProvider('vsphere'),
              primary: true,
            },
            { label: 'Migrate hub', onClick: () => navigate('/migrate') },
          ]}
        />
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {PROVIDERS.map((provDef) => {
          const connected = isConnected(provDef.type);
          const providerId = getProviderId(provDef.type);
          const expanded = expandedProvider === provDef.type;

          return (
            <ProviderCard
              key={provDef.type}
              def={provDef}
              connected={connected}
              providerId={providerId}
              expanded={expanded}
              onToggle={() => setExpandedProvider(expanded ? null : provDef.type)}
              onConnect={(config) => addProvider.mutate(config)}
              onDisconnect={() => providerId && deleteProvider.mutate(providerId)}
              isConnecting={addProvider.isPending}
              connectError={addProvider.error?.message}
            />
          );
        })}
      </div>
    </div>
  );
}

function ProviderCard({ def, connected, providerId, expanded, onToggle, onConnect, onDisconnect, isConnecting, connectError }: {
  def: ProviderCardDef;
  connected: boolean;
  providerId?: string;
  expanded: boolean;
  onToggle: () => void;
  onConnect: (config: ProviderConfig) => void;
  onDisconnect: () => void;
  isConnecting: boolean;
  connectError?: string;
}) {
  const [formData, setFormData] = useState<Record<string, string>>({});
  const [showPassword, setShowPassword] = useState(false);
  const Icon = def.icon;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const config: ProviderConfig = {
      id: '',
      type: def.type,
      name: `${def.name}`,
      endpoint: formData['endpoint'] || '',
      username: formData['username'] || '',
      password: formData['password'] || '',
      region: formData['region'] || '',
      insecure: true,
      metadata: {},
    };
    for (const field of def.fields) {
      if (field.meta && formData[field.key]) {
        config.metadata![field.key] = formData[field.key];
      }
    }
    onConnect(config);
  };

  return (
    <div className="flex flex-col tahoe-glass-card rounded-2xl border border-white/[0.08] overflow-hidden transition-all">
      {/* Header with gradient */}
      <div className={`bg-gradient-to-br ${def.gradient} p-6`}>
        <div className="flex items-start justify-between">
          <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${def.iconGradient} flex items-center justify-center shadow-lg`}>
            <Icon className="h-6 w-6 text-white" />
          </div>
          {connected ? (
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium bg-green-500/20 text-green-300 border border-green-500/30">
                <CheckCircle className="h-3.5 w-3.5" /> Connected
              </span>
              <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium bg-blue-500/20 text-blue-300 border border-blue-500/30">
                saved
              </span>
            </div>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium bg-white/[0.06] text-white/75 border border-white/20">
              <XCircle className="h-3.5 w-3.5" /> Not Connected
            </span>
          )}
        </div>
        <h3 className="text-lg font-bold text-white mt-4">{def.name}</h3>
        <p className="text-sm text-white/70 mt-1 leading-relaxed">{def.description}</p>
      </div>

      {/* Body */}
      <div className="p-5 flex-1 flex flex-col">
        {connected ? (
          /* Connected state — show VM browser */
          <ConnectedView providerId={providerId!} onDisconnect={onDisconnect} />
        ) : (
          /* Not connected — show login form */
          <>
            <button
              onClick={onToggle}
              className="flex items-center gap-2 w-full text-left text-sm font-medium text-white/75 hover:text-white transition-colors mb-4"
            >
              {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              <LogIn className="h-4 w-4" />
              Sign in to connect
            </button>

            {expanded && (
              <form onSubmit={handleSubmit} className="space-y-3 animate-fade-in">
                {def.fields.map((field) => {
                  const FieldIcon = field.icon;
                  return (
                    <div key={field.key}>
                      <label className="block text-xs font-medium text-white/55 mb-1.5">{field.label}</label>
                      <div className="relative">
                        <FieldIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/45" />
                        <input
                          type={field.type === 'password' && showPassword ? 'text' : (field.type || 'text')}
                          value={formData[field.key] || ''}
                          onChange={(e) => setFormData({ ...formData, [field.key]: e.target.value })}
                          placeholder={field.placeholder}
                          className={`w-full pl-10 ${field.type === 'password' ? 'pr-10' : 'pr-4'} py-2.5 tahoe-glass-card border border-white/[0.12] rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-sm`}
                        />
                        {field.type === 'password' && (
                          <button
                            type="button"
                            onClick={() => setShowPassword(!showPassword)}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-white/45 hover:text-white/75 transition-colors"
                          >
                            {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}

                {connectError && (
                  <div className="bg-red-900/30 border border-red-800/50 rounded-lg p-3 text-xs text-red-400">
                    {connectError}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={isConnecting}
                  className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white font-medium rounded-lg py-2.5 px-4 transition-all hover:scale-[1.02] text-sm disabled:opacity-50 disabled:hover:scale-100"
                >
                  {isConnecting ? (
                    <><Loader2 className="h-4 w-4 animate-spin" /> Connecting...</>
                  ) : (
                    <><LogIn className="h-4 w-4" /> Connect</>
                  )}
                </button>
              </form>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function ConnectedView({ providerId, onDisconnect }: { providerId: string; onDisconnect: () => void }) {
  const [search, setSearch] = useState('');
  const { data: vms, isLoading, error } = useVMs(providerId, search || undefined);
  const { selectedVMs, toggleVM } = useAppStore();

  return (
    <div className="flex-1 flex flex-col">
      {/* Search */}
      <div className="relative mb-3">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/45" />
        <input
          type="text"
          placeholder="Search VMs..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-10 pr-4 py-2 tahoe-glass-card border border-white/[0.12] rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-sm"
        />
      </div>

      {/* VM count */}
      <div className="text-xs text-white/45 mb-2">
        {isLoading ? 'Loading...' : `${vms?.length ?? 0} VMs`}
        {selectedVMs.length > 0 && <span className="ml-1 text-blue-400">({selectedVMs.length} selected)</span>}
      </div>

      {/* VM list */}
      <div className="flex-1 overflow-auto max-h-64 space-y-1.5">
        {isLoading && [1, 2, 3].map((i) => <div key={i} className="skeleton h-12 rounded-lg" />)}
        {error && <div className="text-xs text-red-400">Error: {(error as Error).message}</div>}
        {vms?.map((vm) => (
          <VMRow key={vm.id} vm={vm} selected={selectedVMs.includes(vm.id)} onToggle={() => toggleVM(vm.id)} />
        ))}
        {vms?.length === 0 && !isLoading && (
          <div className="text-center py-6 text-xs text-white/45">No VMs found</div>
        )}
      </div>

      {/* Disconnect */}
      <button
        onClick={onDisconnect}
        className="mt-4 w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-colors text-xs font-medium"
      >
        <XCircle className="h-3.5 w-3.5" /> Disconnect
      </button>
    </div>
  );
}

function VMRow({ vm, selected, onToggle }: { vm: VMInfo; selected: boolean; onToggle: () => void }) {
  const isOn = vm.state === 'poweredOn' || vm.state === 'running';
  return (
    <div
      onClick={onToggle}
      className={`flex items-center gap-2.5 p-2.5 rounded-lg border cursor-pointer transition-all text-xs ${
        selected
          ? 'bg-blue-600/10 border-blue-500/40'
          : 'tahoe-glass-card border-white/[0.06] hover:tahoe-glass-card hover:border-white/[0.12]'
      }`}
    >
      <input type="checkbox" checked={selected} readOnly className="accent-blue-500 h-3.5 w-3.5 rounded flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="font-medium text-white truncate">{vm.name}</div>
        <div className="flex items-center gap-2 text-white/45 mt-0.5">
          <span className="flex items-center gap-0.5"><Cpu className="h-2.5 w-2.5" />{vm.num_cpus}</span>
          <span>{vm.memory_mb}MB</span>
          <span className="flex items-center gap-0.5"><HardDrive className="h-2.5 w-2.5" />{vm.storage_gb}G</span>
        </div>
      </div>
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${isOn ? 'bg-green-400' : 'bg-white/30'}`} />
    </div>
  );
}
