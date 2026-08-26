// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useState } from 'react';
import { Search, Cpu, HardDrive } from 'lucide-react';
import { useVMs } from '../hooks/useProviders';
import { useAppStore } from '../stores/app';
import type { VMInfo } from '../types/provider';

interface VMBrowserProps {
  providerId: string;
}

export function VMBrowser({ providerId }: VMBrowserProps) {
  const [search, setSearch] = useState('');
  const { data: vms, isLoading, error } = useVMs(providerId, search || undefined);
  const { selectedVMs, toggleVM } = useAppStore();

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="skeleton h-16 rounded-xl" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-sm text-red-400">
        Error: {(error as Error).message}
      </div>
    );
  }

  return (
    <div>
      {/* Search */}
      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/45" />
        <input
          type="text"
          placeholder="Search VMs..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-10 pr-4 py-2.5 tahoe-glass-card border border-white/[0.12] rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-sm"
        />
      </div>

      <div className="text-xs text-white/45 mb-3">
        {vms?.length ?? 0} VMs found
        {selectedVMs.length > 0 && (
          <span className="ml-2 text-blue-400 font-medium">{selectedVMs.length} selected</span>
        )}
      </div>

      {/* VM list */}
      <div className="space-y-2">
        {vms?.map((vm) => (
          <VMRow key={vm.id} vm={vm} selected={selectedVMs.includes(vm.id)} onToggle={() => toggleVM(vm.id)} />
        ))}
        {vms?.length === 0 && (
          <div className="text-center py-8 text-sm text-white/45">No VMs found</div>
        )}
      </div>
    </div>
  );
}

function VMRow({ vm, selected, onToggle }: { vm: VMInfo; selected: boolean; onToggle: () => void }) {
  return (
    <div
      onClick={onToggle}
      className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-all hover:scale-[1.01] ${
        selected
          ? 'bg-blue-600/10 border-blue-500/50'
          : 'tahoe-glass-card border-white/[0.08] hover:glass hover:border-white/[0.12]'
      }`}
    >
      <input type="checkbox" checked={selected} readOnly className="accent-blue-500 h-4 w-4 rounded" />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-white truncate">{vm.name}</div>
        <div className="flex items-center gap-3 text-xs text-white/55 mt-1">
          <span className="flex items-center gap-1"><Cpu className="h-3 w-3" />{vm.num_cpus} vCPU</span>
          <span>{vm.memory_mb}MB</span>
          <span className="flex items-center gap-1"><HardDrive className="h-3 w-3" />{vm.storage_gb}GB</span>
        </div>
      </div>
      <StatusBadge state={vm.state} />
    </div>
  );
}

function StatusBadge({ state }: { state: string }) {
  const isOn = state === 'poweredOn' || state === 'running';
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
      isOn ? 'bg-green-500/10 text-green-500' : 'bg-white/[0.06] text-white/55'
    }`}>
      {state}
    </span>
  );
}
