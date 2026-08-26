// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Server, Play, Square, RefreshCw, Trash2, Monitor, Cpu, MemoryStick,
  Network, AlertCircle, Loader2, Power, XCircle, Camera, RotateCcw, Plus,
  HardDrive, Image, Activity, Download, Search, Terminal, CheckSquare, Square as SquareIcon,
  HeartPulse, CheckCircle, XOctagon, Wifi, FileCode, ChevronDown, ChevronRight, Info,
  Copy, Globe, Database, Shield, AlertTriangle, Zap, WifiOff, X, Edit2, Save, Upload,
  Disc, Clock, MinusCircle, History, Cloud, ArrowRightLeft,
} from 'lucide-react';
import { fetchAPI } from '../api/client';
import { VNCConsoleModal } from '../components/VNCConsole';
import { showToast } from '../components/Toast';
import { HardwareEditor } from '../components/HardwareEditor';
import { TahoeHero } from '../components/ui/TahoeHero';

interface LibvirtVM {
  name: string;
  state: string;
  id: string;
  autostart: string;
  memory: string;
  vcpus: string;
  ip?: string;
  os_type?: string;
  disk_bus?: string;
  disk_path?: string;
  disk_format?: string;
  guest_agent?: boolean;
}

function OSIcon({ os }: { os: string }) {
  if (os === 'windows') {
    return (
      <svg viewBox="0 0 16 16" className="w-3.5 h-3.5 flex-shrink-0" fill="currentColor">
        <path d="M0 2.5L6.5 1.6V7.5H0V2.5ZM7.5 1.5L16 0V7.5H7.5V1.5ZM0 8.5H6.5V14.4L0 13.5V8.5ZM7.5 8.5H16V16L7.5 14.5V8.5Z"/>
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 16 16" className="w-3.5 h-3.5 flex-shrink-0" fill="currentColor">
      <path d="M8 1C6 1 4.5 3 4.5 5.5C4.5 7 5 8 4 10C3 12 2 13 3 14.5C4 14.5 5 14 6 13.5C7 14 9 14 10 13.5C11 14 12 14.5 13 14.5C14 13 13 12 12 10C11 8 11.5 7 11.5 5.5C11.5 3 10 1 8 1ZM6.5 5C7 5 7.5 5.5 7.5 6C7.5 6.5 7 7 6.5 7C6 7 5.5 6.5 5.5 6C5.5 5.5 6 5 6.5 5ZM9.5 5C10 5 10.5 5.5 10.5 6C10.5 6.5 10 7 9.5 7C9 7 8.5 6.5 8.5 6C8.5 5.5 9 5 9.5 5ZM6.5 8.5H9.5C9.5 9.5 8.5 10.5 8 10.5C7.5 10.5 6.5 9.5 6.5 8.5Z"/>
    </svg>
  );
}

function getOSDisplay(osType?: string): { label: string; color: string; bg: string } {
  switch (osType) {
    case 'windows': return { label: 'Windows', color: 'text-blue-400', bg: 'bg-blue-500/10 border-blue-500/30' };
    case 'kali': return { label: 'Kali', color: 'text-red-400', bg: 'bg-red-500/10 border-red-500/30' };
    case 'ubuntu': return { label: 'Ubuntu', color: 'text-orange-400', bg: 'bg-orange-500/10 border-orange-500/30' };
    case 'rhel': return { label: 'RHEL', color: 'text-red-400', bg: 'bg-red-500/10 border-red-500/30' };
    case 'debian': return { label: 'Debian', color: 'text-red-400', bg: 'bg-red-500/10 border-red-500/30' };
    case 'fedora': return { label: 'Fedora', color: 'text-blue-400', bg: 'bg-blue-500/10 border-blue-500/30' };
    default: return { label: 'Linux', color: 'text-green-400', bg: 'bg-green-500/10 border-green-500/30' };
  }
}

export function VMsPage() {
  const queryClient = useQueryClient();
  const { data: vms, isLoading } = useQuery({
    queryKey: ['libvirt-vms'],
    queryFn: () => fetchAPI<LibvirtVM[]>('/vms'),
    refetchInterval: 5000,
  });
  const [selectedVM, setSelectedVM] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [consoleVM, setConsoleVM] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [stateFilter, setStateFilter] = useState<'all' | 'running' | 'shut off' | 'windows' | 'linux'>('all');
  const [checkedVMs, setCheckedVMs] = useState<Set<string>>(new Set());
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);

  const vmAction = useMutation({
    mutationFn: ({ name, action }: { name: string; action: string }) =>
      fetchAPI<{ message: string }>(`/vms/${name}/${action}`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['libvirt-vms'] }),
  });

  const vmDelete = useMutation({
    mutationFn: (name: string) =>
      fetchAPI<{ message: string }>(`/vms/${name}/delete`, { method: 'POST' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['libvirt-vms'] });
      setConfirmDelete(null);
      setSelectedVM(null);
    },
  });

  const bulkAction = useMutation({
    mutationFn: ({ names, action }: { names: string[]; action: string }) =>
      fetchAPI<{ results: { name: string; success: boolean; error?: string }[] }>('/vms/bulk-action', {
        method: 'POST',
        body: JSON.stringify({ names, action }),
      }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['libvirt-vms'] });
      const successes = data.results.filter((r) => r.success).length;
      const failures = data.results.filter((r) => !r.success);
      if (successes > 0) showToast('success', `${successes} VM(s) action completed`);
      failures.forEach((f) => showToast('error', `${f.name}: ${f.error || 'failed'}`));
      setCheckedVMs(new Set());
    },
    onError: (err) => showToast('error', (err as Error).message),
  });

  const filteredVMs = useMemo(() => {
    if (!vms) return [];
    return vms.filter((vm) => {
      // Search filter
      if (searchQuery && !vm.name.toLowerCase().includes(searchQuery.toLowerCase())) return false;
      // State filter
      if (stateFilter === 'running') return vm.state === 'running';
      if (stateFilter === 'shut off') return vm.state === 'shut off';
      if (stateFilter === 'windows') return vm.os_type === 'windows';
      if (stateFilter === 'linux') return vm.os_type !== 'windows';
      return true;
    });
  }, [vms, searchQuery, stateFilter]);

  const running = vms?.filter((v) => v.state === 'running').length ?? 0;
  const total = vms?.length ?? 0;
  const selected = vms?.find((v) => v.name === selectedVM);
  const allFilteredChecked = filteredVMs.length > 0 && filteredVMs.every((vm) => checkedVMs.has(vm.name));

  const toggleCheck = (name: string) => {
    setCheckedVMs((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name); else next.add(name);
      return next;
    });
  };

  const toggleAllChecked = () => {
    if (allFilteredChecked) {
      setCheckedVMs(new Set());
    } else {
      setCheckedVMs(new Set(filteredVMs.map((vm) => vm.name)));
    }
  };

  return (
    <div>
      <TahoeHero
        icon={<Monitor className="w-5 h-5 text-blue-300" />}
        title="Virtual Machines"
        subtitle={`${running}/${total} running — manage libvirt domains`}
        actions={
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowImportModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-500 hover:to-emerald-500 text-white rounded-lg text-xs font-medium transition-all hover:scale-[1.02]"
            >
              <HardDrive className="h-3.5 w-3.5" /> Import
            </button>
            <button
              onClick={() => setShowCreateModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-white rounded-lg text-xs font-medium transition-all hover:scale-[1.02]"
            >
              <Plus className="h-3.5 w-3.5" /> Create VM
            </button>
          </div>
        }
      />

      {/* Search & Filter */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 mb-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-blue-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search VMs..."
            className="w-full pl-9 pr-3 py-2 tahoe-glass-card border border-white/[0.08] rounded-lg text-sm text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
          />
        </div>
        <div className="flex items-center gap-2">
          {(['all', 'running', 'shut off', 'windows', 'linux'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setStateFilter(f)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                stateFilter === f
                  ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                  : 'tahoe-glass-card text-white/55 border border-white/[0.08] hover:text-white/90 hover:bg-white/[0.04]'
              }`}
            >
              {f === 'shut off' ? 'Shut Off' : f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-6">
        {/* VM Table */}
        <div className="tahoe-glass-card rounded-xl border border-white/[0.08] overflow-hidden">
          <div className="px-5 py-3 border-b border-white/[0.06] flex items-center gap-2">
            <button
              onClick={toggleAllChecked}
              className="h-4 w-4 flex items-center justify-center text-white/55 hover:text-white transition-colors"
              title={allFilteredChecked ? 'Deselect all' : 'Select all'}
            >
              {allFilteredChecked ? <CheckSquare className="h-4 w-4 text-blue-400" /> : <SquareIcon className="h-4 w-4" />}
            </button>
            <Server className="h-4 w-4 text-blue-400" />
            <span className="text-sm font-semibold text-white">Libvirt Domains</span>
            <span className="text-xs text-white/45 ml-auto">{filteredVMs.length}/{total} shown</span>
          </div>

          {isLoading ? (
            <div className="p-4 space-y-2">{[1,2,3].map(i => <div key={i} className="skeleton h-14 rounded-lg" />)}</div>
          ) : (
            <div className="divide-y divide-white/[0.06]">
              {filteredVMs.map((vm) => {
                const isRunning = vm.state === 'running';
                const isPaused = vm.state === 'paused';
                const isChecked = checkedVMs.has(vm.name);
                return (
                  <div
                    key={vm.name}
                    onClick={() => setSelectedVM(vm.name)}
                    className={`flex items-center gap-4 px-5 py-3 cursor-pointer vm-card ${isRunning ? 'vm-running' : ''} ${
                      selectedVM === vm.name ? 'bg-blue-600/10 border-l-2 border-l-blue-500' : ''
                    }`}
                  >
                    <button
                      onClick={(e) => { e.stopPropagation(); toggleCheck(vm.name); }}
                      className="h-4 w-4 flex items-center justify-center text-white/55 hover:text-white transition-colors flex-shrink-0"
                    >
                      {isChecked ? <CheckSquare className="h-4 w-4 text-blue-400" /> : <SquareIcon className="h-4 w-4" />}
                    </button>
                    <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
                      isRunning ? 'bg-green-400 shadow-green-400/50 shadow-sm' :
                      isPaused ? 'bg-yellow-400' : 'bg-white/30'
                    }`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-white truncate">{vm.name}</span>
                        {(() => { const os = getOSDisplay(vm.os_type); return (
                          <span className={`inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full border ${os.bg} ${os.color}`}><OSIcon os={vm.os_type || 'linux'} /> {os.label}</span>
                        ); })()}
                        {vm.disk_bus && (
                          <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${
                            vm.disk_bus === 'virtio' ? 'bg-green-500/10 text-green-400' :
                            vm.disk_bus === 'sata' ? 'bg-yellow-500/10 text-yellow-400' :
                            'bg-white/[0.06] text-white/55'
                          }`}>{vm.disk_bus}</span>
                        )}
                        {vm.guest_agent && (
                          <span className="w-2 h-2 rounded-full bg-cyan-400 flex-shrink-0" title="Guest agent active" />
                        )}
                      </div>
                      <div className="flex items-center gap-3 text-xs text-white/45 mt-0.5">
                        {vm.vcpus && <span className="flex items-center gap-1"><Cpu className="h-3 w-3" />{vm.vcpus}</span>}
                        {vm.memory && <span className="flex items-center gap-1"><MemoryStick className="h-3 w-3" />{vm.memory}</span>}
                        {vm.ip && <span className="flex items-center gap-1 text-green-400"><Network className="h-3 w-3" />{vm.ip}</span>}
                      </div>
                    </div>

                    {/* Quick actions */}
                    <div className="flex items-center gap-1">
                      {isRunning ? (
                        <>
                          <button onClick={(e) => { e.stopPropagation(); vmAction.mutate({ name: vm.name, action: 'reboot' }); }}
                            className="h-7 w-7 rounded-lg hover:bg-yellow-500/10 text-white/55 hover:text-yellow-400 flex items-center justify-center transition-colors" title="Reboot">
                            <RefreshCw className="h-3.5 w-3.5" />
                          </button>
                          <button onClick={(e) => { e.stopPropagation(); vmAction.mutate({ name: vm.name, action: 'stop' }); }}
                            className="h-7 w-7 rounded-lg hover:bg-red-500/10 text-white/55 hover:text-red-400 flex items-center justify-center transition-colors" title="Shutdown">
                            <Square className="h-3.5 w-3.5" />
                          </button>
                        </>
                      ) : (
                        <button onClick={(e) => { e.stopPropagation(); vmAction.mutate({ name: vm.name, action: 'start' }); }}
                          className="h-7 w-7 rounded-lg hover:bg-green-500/10 text-white/55 hover:text-green-400 flex items-center justify-center transition-colors" title="Start">
                          <Play className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>

                    <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${
                      isRunning ? 'bg-green-500/10 text-green-400' :
                      isPaused ? 'bg-yellow-500/10 text-yellow-400' :
                      'bg-white/[0.06] text-white/55'
                    }`}>{vm.state}</span>
                  </div>
                );
              })}
              {filteredVMs.length === 0 && (
                <div className="p-8 text-center text-sm text-white/45">
                  {total === 0 ? 'No VMs defined' : 'No VMs match your search/filter'}
                </div>
              )}
            </div>
          )}
        </div>

        {/* VM Detail Panel */}
        <div className="space-y-4">
          {selected ? (
            <>
              <VMDetailCard vm={selected} onAction={(action) => vmAction.mutate({ name: selected.name, action })} />

              {/* Clone & Resize */}
              <CloneCard vmName={selected.name} />
              <ResizeCard vmName={selected.name} vcpus={selected.vcpus} memory={selected.memory} isRunning={selected.state === 'running'} />
              <MigrateToKubeVirtCard vmName={selected.name} vmState={selected.state} />

              {/* VNC Console */}
              {selected.state === 'running' && (
                <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Monitor className="h-4 w-4 text-cyan-400" />
                    <span className="text-sm font-semibold text-white">Console</span>
                  </div>
                  <button
                    onClick={() => setConsoleVM(selected.name)}
                    className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-cyan-600 to-blue-700 hover:from-cyan-500 hover:to-blue-600 text-white font-medium rounded-lg py-2.5 px-4 transition-all hover:scale-[1.02] text-sm"
                  >
                    <Monitor className="h-4 w-4" /> Open VNC Console
                  </button>
                </div>
              )}

              {/* Serial Console note */}
              {selected.state === 'running' && (
                <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <Terminal className="h-4 w-4 text-green-400" />
                    <span className="text-sm font-semibold text-white">Serial Console</span>
                  </div>
                  <p className="text-xs text-white/55">
                    Serial console: use <code className="glass px-1.5 py-0.5 rounded text-green-400 font-mono">virsh console {selected.name}</code> in terminal
                  </p>
                </div>
              )}

              {/* Enable RDP (Windows VMs only) */}
              {selected.state === 'running' && selected.os_type === 'windows' && (
                <EnableRDPCard vmName={selected.name} ip={selected.ip} />
              )}

              {/* Health Check */}
              {selected.state === 'running' && (
                <HealthCheckCard vmName={selected.name} />
              )}

              {/* Resource Usage */}
              {selected.state === 'running' && (
                <VMResourceStats vmName={selected.name} />
              )}

              {/* Screenshot */}
              {selected.state === 'running' && (
                <ScreenshotCard vmName={selected.name} />
              )}

              {/* Snapshots */}
              <SnapshotCard vmName={selected.name} />

              {/* Status Detail */}
              <StatusDetailCard vmName={selected.name} />

              {/* Guest Agent Insights */}
              {selected.state === 'running' && (
                <GuestAgentCard vmName={selected.name} />
              )}

              {/* Domain XML Viewer */}
              <DomainXMLCard vmName={selected.name} />

              {/* Connectivity Test (running VMs only) */}
              {selected.state === 'running' && (
                <ConnectivityTestCard vmName={selected.name} />
              )}

              {/* Network Detail (running VMs only) */}
              {selected.state === 'running' && (
                <NetworkDetailCard vmName={selected.name} />
              )}

              {/* Recommendations */}
              <RecommendationsCard vmName={selected.name} />

              {/* Security */}
              <SecurityCard vmName={selected.name} />

              {/* Storage Detail */}
              <StorageDetailCard vmName={selected.name} />

              {/* Disk & CDROM Management */}
              <DiskManagementCard vmName={selected.name} />

              {/* Hardware Editor */}
              <HardwareEditor vmName={selected.name} vmState={selected.state} />

              {/* VM Events */}
              <EventsCard vmName={selected.name} />

              {/* Process Viewer */}
              {selected.state === 'running' && (
                <ProcessViewerCard vmName={selected.name} />
              )}

              {/* Delete */}
              <div className="tahoe-glass-card rounded-xl border border-red-500/20 p-4">
                {confirmDelete === selected.name ? (
                  <div>
                    <p className="text-xs text-red-400 mb-3">Delete VM "{selected.name}" and all its storage? This cannot be undone.</p>
                    <div className="flex gap-2">
                      <button onClick={() => vmDelete.mutate(selected.name)}
                        disabled={vmDelete.isPending}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white rounded-lg text-xs font-medium transition-colors">
                        {vmDelete.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />} Confirm Delete
                      </button>
                      <button onClick={() => setConfirmDelete(null)}
                        className="px-3 py-1.5 border border-white/[0.12] text-white/75 rounded-lg text-xs transition-colors hover:bg-white/[0.04]">
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <button onClick={() => setConfirmDelete(selected.name)}
                    className="flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300 transition-colors">
                    <Trash2 className="h-3.5 w-3.5" /> Delete VM
                  </button>
                )}
              </div>
            </>
          ) : (
            <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5 text-center py-16 text-sm text-white/45">
              Select a VM to view details
            </div>
          )}

          {vmAction.error && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-3 text-xs text-red-400">
              <AlertCircle className="h-3.5 w-3.5 inline mr-1" />
              {(vmAction.error as Error).message}
            </div>
          )}
        </div>
      </div>

      {/* Bulk Action Bar */}
      {checkedVMs.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 flex flex-wrap items-center gap-2 sm:gap-3 px-3 sm:px-5 py-3 glass border border-white/[0.12] rounded-xl shadow-2xl backdrop-blur-xl max-w-[95vw]">
          <span className="text-sm text-white font-medium">{checkedVMs.size} VM(s) selected</span>
          <div className="w-px h-6 bg-white/15" />
          <button
            onClick={() => bulkAction.mutate({ names: Array.from(checkedVMs), action: 'start' })}
            disabled={bulkAction.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-green-500/10 text-green-400 rounded-lg text-xs font-medium hover:bg-green-500/20 transition-colors disabled:opacity-50"
          >
            <Play className="h-3 w-3" /> Start Selected
          </button>
          <button
            onClick={() => bulkAction.mutate({ names: Array.from(checkedVMs), action: 'stop' })}
            disabled={bulkAction.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-yellow-500/10 text-yellow-400 rounded-lg text-xs font-medium hover:bg-yellow-500/20 transition-colors disabled:opacity-50"
          >
            <Square className="h-3 w-3" /> Stop Selected
          </button>
          <button
            onClick={() => bulkAction.mutate({ names: Array.from(checkedVMs), action: 'delete' })}
            disabled={bulkAction.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-red-500/10 text-red-400 rounded-lg text-xs font-medium hover:bg-red-500/20 transition-colors disabled:opacity-50"
          >
            <Trash2 className="h-3 w-3" /> Delete Selected
          </button>
          <button
            onClick={() => setCheckedVMs(new Set())}
            className="flex items-center gap-1 px-2 py-1.5 text-white/55 hover:text-white text-xs transition-colors"
          >
            <XCircle className="h-3 w-3" /> Clear
          </button>
        </div>
      )}

      {/* VNC Console Modal */}
      {consoleVM && (
        <VNCConsoleModal vmName={consoleVM} onClose={() => setConsoleVM(null)} />
      )}

      {/* Create VM Modal */}
      {showCreateModal && (
        <CreateVMModal
          onClose={() => setShowCreateModal(false)}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: ['libvirt-vms'] });
            setShowCreateModal(false);
          }}
        />
      )}

      {/* Import VM Modal */}
      {showImportModal && (
        <ImportVMModal
          onClose={() => setShowImportModal(false)}
          onImported={() => {
            queryClient.invalidateQueries({ queryKey: ['libvirt-vms'] });
            setShowImportModal(false);
          }}
        />
      )}
    </div>
  );
}

function VMDetailCard({ vm, onAction }: { vm: LibvirtVM; onAction: (action: string) => void }) {
  const isRunning = vm.state === 'running';
  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-white">{vm.name}</h3>
          <span className={`text-xs font-medium ${isRunning ? 'text-green-400' : 'text-white/55'}`}>{vm.state}</span>
        </div>
        <div className="flex gap-2">
          {isRunning ? (
            <>
              <button onClick={() => onAction('reboot')} className="flex items-center gap-1 px-2.5 py-1.5 bg-yellow-500/10 text-yellow-400 rounded-lg text-xs hover:bg-yellow-500/20 transition-colors">
                <RefreshCw className="h-3 w-3" /> Reboot
              </button>
              <button onClick={() => onAction('stop')} className="flex items-center gap-1 px-2.5 py-1.5 bg-red-500/10 text-red-400 rounded-lg text-xs hover:bg-red-500/20 transition-colors">
                <Power className="h-3 w-3" /> Shutdown
              </button>
              <button onClick={() => onAction('destroy')} className="flex items-center gap-1 px-2.5 py-1.5 bg-red-500/10 text-red-400 rounded-lg text-xs hover:bg-red-500/20 transition-colors" title="Force power off">
                <XCircle className="h-3 w-3" /> Force Off
              </button>
            </>
          ) : (
            <button onClick={() => onAction('start')} className="flex items-center gap-1 px-2.5 py-1.5 bg-green-500/10 text-green-400 rounded-lg text-xs hover:bg-green-500/20 transition-colors">
              <Play className="h-3 w-3" /> Start
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <InfoBox icon={Cpu} label="vCPUs" value={vm.vcpus || '-'} />
        <InfoBox icon={MemoryStick} label="Memory" value={vm.memory || '-'} />
        <InfoBox icon={Monitor} label="ID" value={vm.id || '-'} />
        <InfoBox icon={Network} label="IP" value={vm.ip || 'N/A'} color={vm.ip ? 'text-green-400' : undefined} />
        <InfoBox icon={HardDrive} label="Disk Bus" value={vm.disk_bus || '-'} color={vm.disk_bus === 'virtio' ? 'text-green-400' : undefined} />
        <InfoBox icon={HardDrive} label="Disk Format" value={vm.disk_format || '-'} />
      </div>

      {/* Download Disk */}
      {vm.disk_path && (
        <div className="mt-4 pt-4 border-t border-white/[0.06]">
          <div className="flex items-center gap-2 mb-2">
            <Download className="h-3.5 w-3.5 text-green-400" />
            <span className="text-xs text-white/55 font-mono truncate">{vm.disk_path}</span>
          </div>
          <button
            onClick={() => window.open(`/api/v1/download?path=${encodeURIComponent(vm.disk_path!)}`, '_blank')}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-500/10 text-blue-400 rounded-lg text-xs hover:bg-blue-500/20 transition-colors"
          >
            <Download className="h-3 w-3" /> Download Disk Image
          </button>
        </div>
      )}
    </div>
  );
}


function SnapshotCard({ vmName }: { vmName: string }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ['snapshots', vmName],
    queryFn: () => fetchAPI<{ snapshots: { name: string; created: string; state: string }[] | null }>(`/vms/${vmName}/snapshots`),
  });
  const [newName, setNewName] = useState('');
  const [showCreate, setShowCreate] = useState(false);

  const createSnap = useMutation({
    mutationFn: (name: string) => fetchAPI(`/vms/${vmName}/snapshots`, { method: 'POST', body: JSON.stringify({ name }) }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['snapshots', vmName] }); setShowCreate(false); setNewName(''); },
  });
  const revertSnap = useMutation({
    mutationFn: (name: string) => fetchAPI(`/vms/${vmName}/snapshots/${name}/revert`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['libvirt-vms'] }),
  });
  const deleteSnap = useMutation({
    mutationFn: (name: string) => fetchAPI(`/vms/${vmName}/snapshots/${name}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['snapshots', vmName] }),
  });

  const snaps = data?.snapshots || [];

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Camera className="h-4 w-4 text-purple-400" />
          <span className="text-sm font-medium text-white">Snapshots</span>
          <span className="text-[10px] text-white/45">{snaps.length}</span>
        </div>
        <button onClick={() => setShowCreate(!showCreate)} className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors">
          <Plus className="h-3 w-3" /> Create
        </button>
      </div>

      {showCreate && (
        <div className="flex gap-2 mb-3">
          <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="snapshot-name"
            className="flex-1 px-2.5 py-1.5 tahoe-glass-card border border-white/[0.12] rounded-lg text-white placeholder-white/40 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500" />
          <button onClick={() => createSnap.mutate(newName || `snap-${Date.now()}`)} disabled={createSnap.isPending}
            className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs hover:bg-blue-500 transition-colors disabled:opacity-50">
            {createSnap.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Create'}
          </button>
        </div>
      )}

      {snaps.length > 0 ? (
        <div className="space-y-1.5">
          {snaps.map((snap) => (
            <div key={snap.name} className="flex items-center gap-2 p-2 tahoe-glass-card rounded-lg text-xs">
              <Camera className="h-3 w-3 text-purple-400 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-white/75 font-mono truncate">{snap.name}</div>
                <div className="text-[10px] text-white/45">{snap.created}</div>
              </div>
              <button onClick={() => revertSnap.mutate(snap.name)} title="Revert"
                className="h-6 w-6 rounded hover:bg-yellow-500/10 text-white/55 hover:text-yellow-400 flex items-center justify-center transition-colors">
                <RotateCcw className="h-3 w-3" />
              </button>
              <button onClick={() => deleteSnap.mutate(snap.name)} title="Delete"
                className="h-6 w-6 rounded hover:bg-red-500/10 text-white/55 hover:text-red-400 flex items-center justify-center transition-colors">
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-xs text-white/45 text-center py-2">No snapshots</div>
      )}
    </div>
  );
}

function ScreenshotCard({ vmName }: { vmName: string }) {
  const [key, setKey] = useState(0);
  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Image className="h-4 w-4 text-blue-400" />
          <span className="text-sm font-semibold text-white">Screenshot</span>
        </div>
        <button
          onClick={() => setKey((k) => k + 1)}
          className="flex items-center gap-1 text-xs text-white/55 hover:text-white transition-colors"
        >
          <RefreshCw className="h-3 w-3" /> Refresh
        </button>
      </div>
      <div className="rounded-lg overflow-hidden tahoe-glass-card border border-white/[0.06]">
        <img
          key={key}
          src={`/api/v1/vms/${vmName}/screenshot?t=${key}`}
          alt={`${vmName} screenshot`}
          className="w-full h-auto"
          onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
        />
      </div>
    </div>
  );
}

function InfoBox({ icon: Icon, label, value, color }: { icon: React.ElementType; label: string; value: string; color?: string }) {
  return (
    <div className="p-2.5 tahoe-glass-card rounded-lg">
      <div className="flex items-center gap-1.5 text-[10px] text-white/45 mb-0.5">
        <Icon className="h-3 w-3 text-blue-400" />{label}
      </div>
      <div className={`text-xs font-medium ${color || 'text-white/75'}`}>{value}</div>
    </div>
  );
}

interface HealthResult {
  vm_name: string;
  running: boolean;
  ip: string;
  ssh_reachable: boolean;
  guest_agent: boolean;
}

function EnableRDPCard({ vmName, ip }: { vmName: string; ip?: string }) {
  const [result, setResult] = useState<{ enabled?: boolean; method?: string; ip?: string; message?: string; instructions?: string[] } | null>(null);
  const [loading, setLoading] = useState(false);

  const handleEnable = async () => {
    setLoading(true);
    try {
      const res = await fetchAPI<typeof result>(`/vms/${vmName}/enable-rdp`, { method: 'POST' });
      setResult(res);
      if (res?.enabled) {
        showToast('success', res.message || 'RDP enabled');
      }
    } catch (err) {
      showToast('error', (err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Monitor className="h-4 w-4 text-blue-400" />
          <span className="text-sm font-semibold text-white">Remote Desktop (RDP)</span>
        </div>
        <button
          onClick={handleEnable}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-500/10 text-blue-400 rounded-lg text-xs hover:bg-blue-500/20 transition-colors disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Monitor className="h-3 w-3" />}
          Enable RDP
        </button>
      </div>

      {ip && !result && (
        <p className="text-xs text-white/45">
          Connect: <code className="glass px-1.5 py-0.5 rounded text-blue-400 font-mono">mstsc /v:{ip}</code>
        </p>
      )}

      {result && result.enabled && (
        <div className="mt-2 p-3 bg-green-500/10 border border-green-500/20 rounded-lg">
          <p className="text-xs text-green-400 font-medium">RDP enabled via guest agent</p>
          {result.ip && (
            <p className="text-xs text-white/55 mt-1">
              Connect: <code className="glass px-1.5 py-0.5 rounded text-green-400 font-mono">mstsc /v:{result.ip}</code>
            </p>
          )}
        </div>
      )}

      {result && !result.enabled && result.instructions && (
        <div className="mt-2 p-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg">
          <p className="text-xs text-yellow-400 font-medium mb-2">Guest agent not available — enable manually:</p>
          <ol className="text-xs text-white/55 space-y-1 list-decimal list-inside">
            {result.instructions.map((step, i) => (
              <li key={i}>{step}</li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

function HealthCheckCard({ vmName }: { vmName: string }) {
  const [health, setHealth] = useState<HealthResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sshUser, setSshUser] = useState('root');

  const runCheck = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = sshUser && sshUser !== 'root' ? `?ssh_user=${encodeURIComponent(sshUser)}` : '';
      const result = await fetchAPI<HealthResult>(`/vms/${encodeURIComponent(vmName)}/health${params}`);
      setHealth(result);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const checks = health ? [
    { label: 'VM Running', pass: health.running, icon: Power },
    { label: 'IP Address', pass: !!health.ip, icon: Network, detail: health.ip || 'N/A' },
    { label: 'SSH Reachable', pass: health.ssh_reachable, icon: Wifi },
    { label: 'Guest Agent', pass: health.guest_agent, icon: Monitor },
  ] : [];

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <HeartPulse className="h-4 w-4 text-pink-400" />
          <span className="text-sm font-semibold text-white">Health Check</span>
        </div>
        <button
          onClick={runCheck}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-pink-500/10 text-pink-400 rounded-lg text-xs font-medium hover:bg-pink-500/20 transition-colors disabled:opacity-50"
        >
          {loading ? <><Loader2 className="h-3 w-3 animate-spin" /> Checking...</> : <><HeartPulse className="h-3 w-3" /> Run Check</>}
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-xs text-red-400">
          <AlertCircle className="h-3.5 w-3.5 inline mr-1" /> {error}
        </div>
      )}

      {health && (
        <div className="space-y-2">
          {checks.map((check) => {
            const Icon = check.icon;
            return (
              <div key={check.label} className="flex items-center gap-3 p-2.5 tahoe-glass-card rounded-lg">
                <div className={`w-5 h-5 rounded-full flex items-center justify-center ${
                  check.pass ? 'bg-green-500/20' : 'bg-red-500/20'
                }`}>
                  {check.pass ? (
                    <CheckCircle className="h-3 w-3 text-green-400" />
                  ) : (
                    <XOctagon className="h-3 w-3 text-red-400" />
                  )}
                </div>
                <Icon className="h-3.5 w-3.5 text-blue-400" />
                <span className="text-xs text-white/75 flex-1">{check.label}</span>
                {check.detail && (
                  <span className="text-xs font-mono text-white/55">{check.detail}</span>
                )}
                <span className={`text-[10px] font-medium ${check.pass ? 'text-green-400' : 'text-red-400'}`}>
                  {check.pass ? 'PASS' : 'FAIL'}
                </span>
              </div>
            );
          })}
        </div>
      )}

      <div className="flex items-center gap-2 mb-2">
        <label className="text-xs text-white/45">SSH User:</label>
        <input
          type="text"
          value={sshUser}
          onChange={(e) => setSshUser(e.target.value)}
          placeholder="root"
          className="px-2 py-1 tahoe-glass-card border border-white/[0.08] rounded text-xs text-white/75 w-28 focus:outline-none focus:border-pink-500/50"
        />
      </div>

      {!health && !loading && !error && (
        <p className="text-xs text-white/45">Click "Run Check" to verify VM health: running state, IP, SSH, guest agent.</p>
      )}
    </div>
  );
}

interface VMStats {
  cpu_percent: number;
  memory_percent: number;
  memory_used_mb?: number;
  memory_total_mb?: number;
}

function VMResourceStats({ vmName }: { vmName: string }) {
  const { data: stats } = useQuery({
    queryKey: ['vm-stats', vmName],
    queryFn: () => fetchAPI<VMStats>(`/vms/${vmName}/stats/live`),
    refetchInterval: 5000,
    retry: false,
  });

  if (!stats) return null;

  const cpuPct = Math.round(stats.cpu_percent ?? 0);
  const memPct = Math.round(stats.memory_percent ?? 0);

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
      <div className="flex items-center gap-2 mb-3">
        <Activity className="h-4 w-4 text-green-400" />
        <span className="text-sm font-semibold text-white">Resource Usage</span>
        <span className="text-[10px] text-white/45 ml-auto">Live</span>
      </div>
      <div className="space-y-3">
        {/* CPU */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-1.5 text-xs text-white/55">
              <Cpu className="h-3 w-3" /> CPU
            </div>
            <span className={`text-xs font-medium ${cpuPct > 90 ? 'text-red-400' : cpuPct > 75 ? 'text-yellow-400' : 'text-blue-400'}`}>
              {cpuPct}%
            </span>
          </div>
          <div className="h-2 bg-white/[0.08] rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${cpuPct > 90 ? 'bg-red-500' : cpuPct > 75 ? 'bg-yellow-500' : 'bg-blue-500'}`}
              style={{ width: `${cpuPct}%` }}
            />
          </div>
        </div>
        {/* Memory */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-1.5 text-xs text-white/55">
              <MemoryStick className="h-3 w-3" /> Memory
              {stats.memory_used_mb != null && stats.memory_total_mb != null && (
                <span className="text-[10px] text-white/45">
                  ({stats.memory_used_mb}MB / {stats.memory_total_mb}MB)
                </span>
              )}
            </div>
            <span className={`text-xs font-medium ${memPct > 90 ? 'text-red-400' : memPct > 75 ? 'text-yellow-400' : 'text-green-400'}`}>
              {memPct}%
            </span>
          </div>
          <div className="h-2 bg-white/[0.08] rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${memPct > 90 ? 'bg-red-500' : memPct > 75 ? 'bg-yellow-500' : 'bg-green-500'}`}
              style={{ width: `${memPct}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

interface StatusDetailData {
  state: string;
  reason: string;
  warnings: string[];
  cpu_percent?: number;
  memory_percent?: number;
}

function StatusDetailCard({ vmName }: { vmName: string }) {
  const { data: statusDetail } = useQuery({
    queryKey: ['vm-status-detail', vmName],
    queryFn: () => fetchAPI<StatusDetailData>(`/vms/${encodeURIComponent(vmName)}/status-detail`),
    refetchInterval: 10000,
    retry: false,
  });

  if (!statusDetail) return null;

  const hasWarnings = statusDetail.warnings && statusDetail.warnings.length > 0;
  const cpuPct = Math.round(statusDetail.cpu_percent ?? 0);
  const memPct = Math.round(statusDetail.memory_percent ?? 0);
  const stateColor = statusDetail.state === 'running' ? 'text-green-400' :
    statusDetail.state === 'shut off' ? 'text-white/55' : 'text-yellow-400';

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
      <div className="flex items-center gap-2 mb-3">
        <Search className="h-4 w-4 text-indigo-400" />
        <span className="text-sm font-semibold text-white">Status Detail</span>
      </div>

      <div className="space-y-2">
        {/* State with reason */}
        <div className="flex items-center gap-2 p-2.5 tahoe-glass-card rounded-lg">
          <Info className="h-3.5 w-3.5 text-blue-400 flex-shrink-0" />
          <span className="text-xs text-white/75">State:</span>
          <span className={`text-xs font-medium ${stateColor}`}>
            {statusDetail.state}{statusDetail.reason ? ` (${statusDetail.reason})` : ''}
          </span>
          {!hasWarnings && (
            <span className="text-[10px] text-green-400 ml-auto">no issues</span>
          )}
        </div>

        {/* Warnings */}
        {hasWarnings && (
          <div className="space-y-1">
            {statusDetail.warnings.map((warn, i) => (
              <div key={i} className="flex items-start gap-2 p-2 bg-yellow-500/5 border border-yellow-500/20 rounded-lg">
                <AlertCircle className="h-3.5 w-3.5 text-yellow-400 flex-shrink-0 mt-0.5" />
                <span className="text-xs text-yellow-400">{warn}</span>
              </div>
            ))}
          </div>
        )}

        {/* Resource pressure bars */}
        {(statusDetail.cpu_percent != null || statusDetail.memory_percent != null) && (
          <div className="space-y-2 pt-1">
            {statusDetail.cpu_percent != null && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-1.5 text-xs text-white/55">
                    <Cpu className="h-3 w-3" /> CPU
                  </div>
                  <span className={`text-xs font-medium ${cpuPct > 90 ? 'text-red-400' : cpuPct > 75 ? 'text-yellow-400' : 'text-blue-400'}`}>
                    {cpuPct}%
                  </span>
                </div>
                <div className="h-1.5 bg-white/[0.08] rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${cpuPct > 90 ? 'bg-red-500' : cpuPct > 75 ? 'bg-yellow-500' : 'bg-blue-500'}`}
                    style={{ width: `${cpuPct}%` }}
                  />
                </div>
              </div>
            )}
            {statusDetail.memory_percent != null && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-1.5 text-xs text-white/55">
                    <MemoryStick className="h-3 w-3" /> Memory
                  </div>
                  <span className={`text-xs font-medium ${memPct > 90 ? 'text-red-400' : memPct > 75 ? 'text-yellow-400' : 'text-green-400'}`}>
                    {memPct}%
                  </span>
                </div>
                <div className="h-1.5 bg-white/[0.08] rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${memPct > 90 ? 'bg-red-500' : memPct > 75 ? 'bg-yellow-500' : 'bg-green-500'}`}
                    style={{ width: `${memPct}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

interface GuestInfoData {
  available: boolean;
  hostname?: string;
  os_name?: string;
  os_version?: string;
  kernel?: string;
  filesystems?: {
    mountpoint: string;
    used_bytes: number;
    total_bytes: number;
    percent: number;
  }[];
  interfaces?: {
    name: string;
    ip: string;
    mac: string;
  }[];
}

function GuestAgentCard({ vmName }: { vmName: string }) {
  const { data: guestInfo } = useQuery({
    queryKey: ['vm-guest-info', vmName],
    queryFn: () => fetchAPI<GuestInfoData>(`/vms/${encodeURIComponent(vmName)}/guest-info`),
    refetchInterval: 15000,
    retry: false,
  });

  if (!guestInfo) return null;

  const formatBytes = (bytes: number): string => {
    if (bytes >= 1073741824) return `${(bytes / 1073741824).toFixed(1)}G`;
    if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(0)}M`;
    return `${(bytes / 1024).toFixed(0)}K`;
  };

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
      <div className="flex items-center gap-2 mb-3">
        <Globe className="h-4 w-4 text-cyan-400" />
        <span className="text-sm font-semibold text-white">Guest Agent</span>
        <span className={`text-[10px] font-medium ml-auto px-2 py-0.5 rounded-full ${
          guestInfo.available ? 'bg-green-500/10 text-green-400' : 'bg-white/[0.06] text-white/55'
        }`}>
          {guestInfo.available ? 'Available' : 'Unavailable'}
        </span>
      </div>

      {!guestInfo.available ? (
        <p className="text-xs text-white/45">
          Guest agent is not running. Install <code className="glass px-1 py-0.5 rounded text-white/55 font-mono">qemu-guest-agent</code> inside the VM to enable this feature.
        </p>
      ) : (
        <div className="space-y-3">
          {/* System info */}
          <div className="grid grid-cols-1 gap-1.5">
            {guestInfo.hostname && (
              <div className="flex items-center gap-2 p-2 tahoe-glass-card rounded-lg">
                <Server className="h-3 w-3 text-blue-400 flex-shrink-0" />
                <span className="text-[10px] text-white/45 w-14">Hostname</span>
                <span className="text-xs text-white/75 font-mono truncate">{guestInfo.hostname}</span>
              </div>
            )}
            {guestInfo.os_name && (
              <div className="flex items-center gap-2 p-2 tahoe-glass-card rounded-lg">
                <Monitor className="h-3 w-3 text-blue-400 flex-shrink-0" />
                <span className="text-[10px] text-white/45 w-14">OS</span>
                <span className="text-xs text-white/75 truncate">
                  {guestInfo.os_name}{guestInfo.os_version ? ` ${guestInfo.os_version}` : ''}
                </span>
              </div>
            )}
            {guestInfo.kernel && (
              <div className="flex items-center gap-2 p-2 tahoe-glass-card rounded-lg">
                <Terminal className="h-3 w-3 text-blue-400 flex-shrink-0" />
                <span className="text-[10px] text-white/45 w-14">Kernel</span>
                <span className="text-xs text-white/75 font-mono truncate">{guestInfo.kernel}</span>
              </div>
            )}
          </div>

          {/* Filesystems */}
          {guestInfo.filesystems && guestInfo.filesystems.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 text-xs text-white/55 mb-1.5">
                <Database className="h-3 w-3" /> Filesystems
              </div>
              <div className="space-y-1.5">
                {guestInfo.filesystems.map((fs) => {
                  const pct = Math.round(fs.percent);
                  return (
                    <div key={fs.mountpoint} className="p-2 tahoe-glass-card rounded-lg">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[10px] text-white/55 font-mono">{fs.mountpoint}</span>
                        <span className="text-[10px] text-white/45">
                          {formatBytes(fs.used_bytes)} / {formatBytes(fs.total_bytes)}
                        </span>
                      </div>
                      <div className="h-1.5 bg-white/[0.08] rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${
                            pct > 90 ? 'bg-red-500' : pct > 75 ? 'bg-yellow-500' : 'bg-cyan-500'
                          }`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <div className="text-right mt-0.5">
                        <span className={`text-[10px] font-medium ${
                          pct > 90 ? 'text-red-400' : pct > 75 ? 'text-yellow-400' : 'text-cyan-400'
                        }`}>{pct}%</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Network interfaces */}
          {guestInfo.interfaces && guestInfo.interfaces.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 text-xs text-white/55 mb-1.5">
                <Network className="h-3 w-3" /> Interfaces
              </div>
              <div className="space-y-1.5">
                {guestInfo.interfaces.map((iface) => (
                  <div key={iface.name} className="flex items-center gap-2 p-2 tahoe-glass-card rounded-lg">
                    <Network className="h-3 w-3 text-cyan-400 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-xs text-white/75 font-mono">{iface.name}</div>
                      <div className="text-[10px] text-white/45">{iface.ip} &middot; {iface.mac}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DomainXMLCard({ vmName }: { vmName: string }) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const { data: xmlData } = useQuery({
    queryKey: ['vm-xml', vmName],
    queryFn: () => fetchAPI<{ xml: string }>(`/vms/${encodeURIComponent(vmName)}/xml`),
    enabled: expanded,
    retry: false,
  });

  const handleCopy = async () => {
    if (xmlData?.xml) {
      await navigator.clipboard.writeText(xmlData.xml);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full text-left"
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4 text-white/55" />
        ) : (
          <ChevronRight className="h-4 w-4 text-white/55" />
        )}
        <FileCode className="h-4 w-4 text-amber-400" />
        <span className="text-sm font-semibold text-white">Domain XML</span>
      </button>

      {expanded && (
        <div className="mt-3">
          <div className="flex justify-end mb-2">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 px-2.5 py-1 bg-white/[0.08]/50 hover:bg-white/[0.04] text-white/75 rounded-lg text-xs transition-colors"
            >
              <Copy className="h-3 w-3" />
              {copied ? 'Copied!' : 'Copy'}
            </button>
          </div>
          {xmlData?.xml ? (
            <pre className="text-[11px] text-white/75 font-mono tahoe-glass-card border border-white/[0.06] rounded-lg p-3 overflow-x-auto max-h-80 overflow-y-auto whitespace-pre">
              {xmlData.xml}
            </pre>
          ) : (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="h-4 w-4 animate-spin text-white/55" />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface ConnectivityResult {
  ip: string;
  reachable: boolean;
  ports: { port: number; name: string; open: boolean }[];
}

function ConnectivityTestCard({ vmName }: { vmName: string }) {
  const [result, setResult] = useState<ConnectivityResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runTest = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAPI<ConnectivityResult>(`/vms/${encodeURIComponent(vmName)}/connectivity-test`);
      setResult(data);
    } catch (e) {
      setError((e as Error).message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Wifi className="h-4 w-4 text-teal-400" />
          <span className="text-sm font-semibold text-white">Connectivity Test</span>
        </div>
        <button
          onClick={runTest}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-teal-500/10 text-teal-400 rounded-lg text-xs font-medium hover:bg-teal-500/20 transition-colors disabled:opacity-50"
        >
          {loading ? (
            <><Loader2 className="h-3 w-3 animate-spin" /> Testing...</>
          ) : (
            <><Zap className="h-3 w-3" /> Test Connectivity</>
          )}
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-xs text-red-400">
          <AlertCircle className="h-3.5 w-3.5 inline mr-1" /> {error}
        </div>
      )}

      {result && (
        <div className="space-y-3">
          {/* IP and ping status */}
          <div className="flex items-center gap-3 p-2.5 tahoe-glass-card rounded-lg">
            <Globe className="h-3.5 w-3.5 text-blue-400 flex-shrink-0" />
            <span className="text-xs text-white/75 flex-1">
              IP: <span className="font-mono text-white/90">{result.ip || 'N/A'}</span>
            </span>
            <div className="flex items-center gap-1.5">
              {result.reachable ? (
                <><Wifi className="h-3 w-3 text-green-400" /><span className="text-[10px] font-medium text-green-400">Reachable</span></>
              ) : (
                <><WifiOff className="h-3 w-3 text-red-400" /><span className="text-[10px] font-medium text-red-400">Unreachable</span></>
              )}
            </div>
          </div>

          {/* Port grid */}
          {result.ports && result.ports.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 text-xs text-white/55 mb-1.5">
                <Network className="h-3 w-3" /> Ports
              </div>
              <div className="grid grid-cols-2 gap-1.5">
                {result.ports.map((p) => (
                  <div key={p.port} className="flex items-center gap-2 p-2 tahoe-glass-card rounded-lg">
                    <div className={`w-2 h-2 rounded-full flex-shrink-0 ${p.open ? 'bg-green-400 shadow-green-400/50 shadow-sm' : 'bg-red-400'}`} />
                    <span className="text-xs text-white/75 flex-1 truncate">{p.name}</span>
                    <span className="text-[10px] font-mono text-white/45">{p.port}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {!result && !loading && !error && (
        <p className="text-xs text-white/45">Click "Test Connectivity" to check IP reachability and open ports.</p>
      )}
    </div>
  );
}

interface Recommendation {
  type: string;
  severity: string;
  title: string;
  detail: string;
  action: string;
}

interface RecommendationsData {
  recommendations: Recommendation[];
  score: number;
}

function ScoreBadge({ score }: { score: number }) {
  const color = score > 80 ? 'text-green-400 border-green-500/30 bg-green-500/10' :
    score > 50 ? 'text-yellow-400 border-yellow-500/30 bg-yellow-500/10' :
    'text-red-400 border-red-500/30 bg-red-500/10';

  return (
    <div className={`w-9 h-9 rounded-full border-2 flex items-center justify-center text-xs font-bold ${color}`}>
      {score}
    </div>
  );
}

function SeverityIcon({ severity }: { severity: string }) {
  switch (severity) {
    case 'high':
      return <AlertCircle className="h-3.5 w-3.5 text-red-400 flex-shrink-0" />;
    case 'medium':
      return <AlertTriangle className="h-3.5 w-3.5 text-yellow-400 flex-shrink-0" />;
    case 'low':
      return <Info className="h-3.5 w-3.5 text-blue-400 flex-shrink-0" />;
    default:
      return <Info className="h-3.5 w-3.5 text-white/55 flex-shrink-0" />;
  }
}

function severityBorder(severity: string): string {
  switch (severity) {
    case 'high': return 'border-l-2 border-l-red-500/50';
    case 'medium': return 'border-l-2 border-l-yellow-500/50';
    case 'low': return 'border-l-2 border-l-blue-500/50';
    default: return 'border-l-2 border-l-white/20';
  }
}

function RecommendationsCard({ vmName }: { vmName: string }) {
  const { data } = useQuery({
    queryKey: ['vm-recommendations', vmName],
    queryFn: () => fetchAPI<RecommendationsData>(`/vms/${encodeURIComponent(vmName)}/recommendations`),
    refetchInterval: 30000,
    retry: false,
  });

  if (!data) return null;

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Zap className="h-4 w-4 text-amber-400" />
          <span className="text-sm font-semibold text-white">Recommendations</span>
        </div>
        <ScoreBadge score={data.score} />
      </div>

      {data.recommendations.length > 0 ? (
        <div className="space-y-1.5">
          {data.recommendations.map((rec, i) => (
            <div key={i} className={`p-2.5 tahoe-glass-card rounded-lg ${severityBorder(rec.severity)}`}>
              <div className="flex items-start gap-2">
                <SeverityIcon severity={rec.severity} />
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-white/90 font-medium">{rec.title}</div>
                  <div className="text-[11px] text-white/55 mt-0.5">{rec.detail}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-xs text-white/45 text-center py-2">No recommendations -- looking good!</div>
      )}
    </div>
  );
}

interface SecurityFinding {
  severity: string;
  category: string;
  title: string;
  detail: string;
}

interface SecurityData {
  findings: SecurityFinding[];
  score: number;
  summary: string;
}

function SecurityCard({ vmName }: { vmName: string }) {
  const { data } = useQuery({
    queryKey: ['vm-security', vmName],
    queryFn: () => fetchAPI<SecurityData>(`/vms/${encodeURIComponent(vmName)}/security`),
    refetchInterval: 30000,
    retry: false,
  });

  if (!data) return null;

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Shield className="h-4 w-4 text-violet-400" />
          <span className="text-sm font-semibold text-white">Security</span>
        </div>
        <ScoreBadge score={data.score} />
      </div>

      {data.summary && (
        <p className="text-xs text-white/55 mb-3">{data.summary}</p>
      )}

      {data.findings.length > 0 ? (
        <div className="space-y-1.5">
          {data.findings.map((finding, i) => (
            <div key={i} className={`p-2.5 tahoe-glass-card rounded-lg ${severityBorder(finding.severity)}`}>
              <div className="flex items-start gap-2">
                <SeverityIcon severity={finding.severity} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-white/90 font-medium">{finding.title}</span>
                    <span className="text-[10px] text-white/45 px-1.5 py-0.5 bg-white/[0.04] rounded">{finding.category}</span>
                  </div>
                  <div className="text-[11px] text-white/55 mt-0.5">{finding.detail}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-xs text-green-400 text-center py-2 flex items-center justify-center gap-1.5">
          <Shield className="h-3 w-3" /> No security findings
        </div>
      )}
    </div>
  );
}

function fmtBytes(b: number): string {
  if (b > 1e9) return (b / 1e9).toFixed(1) + ' GB';
  if (b > 1e6) return (b / 1e6).toFixed(1) + ' MB';
  if (b > 1e3) return (b / 1e3).toFixed(1) + ' KB';
  return b + ' B';
}

interface StorageDetailDisk {
  target: string;
  read_bytes: number;
  write_bytes: number;
  read_ops: number;
  write_ops: number;
  errors: number;
}

interface StorageDetailData {
  disks: StorageDetailDisk[];
  capacity: number;
  allocation: number;
  snapshot_tree: string;
  pool_name: string;
  pool_capacity: number;
  pool_used: number;
}

function StorageDetailCard({ vmName }: { vmName: string }) {
  const { data } = useQuery({
    queryKey: ['vm-storage-detail', vmName],
    queryFn: () => fetchAPI<StorageDetailData>(`/vms/${encodeURIComponent(vmName)}/storage-detail`),
    refetchInterval: 15000,
    retry: false,
  });

  if (!data) return null;

  const allocPct = data.capacity > 0 ? Math.round((data.allocation / data.capacity) * 100) : 0;
  const poolPct = data.pool_capacity > 0 ? Math.round((data.pool_used / data.pool_capacity) * 100) : 0;

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
      <div className="flex items-center gap-2 mb-3">
        <HardDrive className="h-4 w-4 text-yellow-400" />
        <span className="text-sm font-semibold text-white">Storage Detail</span>
      </div>

      {/* Disk I/O Table */}
      {data.disks && data.disks.length > 0 && (
        <div className="mb-4">
          <div className="text-xs text-white/55 mb-1.5">Disk I/O</div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-white/45">
                  <th className="text-left py-1 pr-2 font-medium">Target</th>
                  <th className="text-right py-1 px-2 font-medium">Read</th>
                  <th className="text-right py-1 px-2 font-medium">Write</th>
                  <th className="text-right py-1 px-2 font-medium">R Ops</th>
                  <th className="text-right py-1 px-2 font-medium">W Ops</th>
                  <th className="text-right py-1 pl-2 font-medium">Errors</th>
                </tr>
              </thead>
              <tbody>
                {data.disks.map((disk) => (
                  <tr key={disk.target} className="border-t border-white/[0.06]">
                    <td className="py-1.5 pr-2 text-white/75 font-mono">{disk.target}</td>
                    <td className="py-1.5 px-2 text-right text-white/55">{fmtBytes(disk.read_bytes)}</td>
                    <td className="py-1.5 px-2 text-right text-white/55">{fmtBytes(disk.write_bytes)}</td>
                    <td className="py-1.5 px-2 text-right text-white/55">{disk.read_ops}</td>
                    <td className="py-1.5 px-2 text-right text-white/55">{disk.write_ops}</td>
                    <td className={`py-1.5 pl-2 text-right font-medium ${disk.errors > 0 ? 'text-red-400' : 'text-white/55'}`}>
                      {disk.errors}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Capacity Bar */}
      {data.capacity > 0 && (
        <div className="mb-4">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-white/55">Capacity</span>
            <span className="text-xs text-white/55">
              {fmtBytes(data.allocation)} / {fmtBytes(data.capacity)} ({allocPct}%)
            </span>
          </div>
          <div className="h-2 bg-white/[0.08] rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                allocPct > 90 ? 'bg-red-500' : allocPct > 75 ? 'bg-yellow-500' : 'bg-blue-500'
              }`}
              style={{ width: `${allocPct}%` }}
            />
          </div>
        </div>
      )}

      {/* Snapshot Tree */}
      {data.snapshot_tree && (
        <div className="mb-4">
          <div className="text-xs text-white/55 mb-1.5">Snapshot Tree</div>
          <pre className="text-[11px] text-white/75 font-mono tahoe-glass-card border border-white/[0.06] rounded-lg p-3 overflow-x-auto max-h-40 overflow-y-auto whitespace-pre">
            {data.snapshot_tree}
          </pre>
        </div>
      )}

      {/* Pool Usage */}
      {data.pool_capacity > 0 && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-white/55">Pool: {data.pool_name || 'default'}</span>
            <span className="text-xs text-white/55">
              {fmtBytes(data.pool_used)} / {fmtBytes(data.pool_capacity)}
            </span>
          </div>
          <div className="h-2 bg-white/[0.08] rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                poolPct > 90 ? 'bg-red-500' : poolPct > 75 ? 'bg-yellow-500' : 'bg-cyan-500'
              }`}
              style={{ width: `${poolPct}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

interface ProcessInfo {
  user: string;
  pid: number;
  cpu: number;
  mem: number;
  command: string;
}

interface ProcessData {
  available: boolean;
  processes: ProcessInfo[];
}

function ProcessViewerCard({ vmName }: { vmName: string }) {
  const [result, setResult] = useState<ProcessData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchProcesses = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAPI<ProcessData>(`/vms/${encodeURIComponent(vmName)}/processes`);
      setResult(data);
    } catch (e) {
      setError((e as Error).message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-green-400" />
          <span className="text-sm font-semibold text-white">Process Viewer</span>
        </div>
        <button
          onClick={fetchProcesses}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-green-500/10 text-green-400 rounded-lg text-xs font-medium hover:bg-green-500/20 transition-colors disabled:opacity-50"
        >
          {loading ? (
            <><Loader2 className="h-3 w-3 animate-spin" /> Loading...</>
          ) : (
            <><Activity className="h-3 w-3" /> View Processes</>
          )}
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-xs text-red-400">
          <AlertCircle className="h-3.5 w-3.5 inline mr-1" /> {error}
        </div>
      )}

      {result && !result.available && (
        <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-3 text-xs text-yellow-400">
          <AlertTriangle className="h-3.5 w-3.5 inline mr-1" /> Guest agent required to view processes.
          Install <code className="glass px-1 py-0.5 rounded text-white/55 font-mono">qemu-guest-agent</code> inside the VM.
        </div>
      )}

      {result && result.available && result.processes && result.processes.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-white/45">
                <th className="text-left py-1 pr-2 font-medium">User</th>
                <th className="text-right py-1 px-2 font-medium">PID</th>
                <th className="text-right py-1 px-2 font-medium">CPU%</th>
                <th className="text-right py-1 px-2 font-medium">MEM%</th>
                <th className="text-left py-1 pl-2 font-medium">Command</th>
              </tr>
            </thead>
            <tbody>
              {result.processes.map((proc) => (
                <tr
                  key={proc.pid}
                  className={`border-t border-white/[0.06] ${proc.cpu > 50 ? 'bg-red-500/10' : ''}`}
                >
                  <td className="py-1.5 pr-2 text-white/75">{proc.user}</td>
                  <td className="py-1.5 px-2 text-right text-white/55 font-mono">{proc.pid}</td>
                  <td className={`py-1.5 px-2 text-right font-medium ${proc.cpu > 50 ? 'text-red-400' : 'text-white/55'}`}>
                    {proc.cpu.toFixed(1)}
                  </td>
                  <td className="py-1.5 px-2 text-right text-white/55">{proc.mem.toFixed(1)}</td>
                  <td className="py-1.5 pl-2 text-white/75 font-mono truncate max-w-[150px]">{proc.command}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!result && !loading && !error && (
        <p className="text-xs text-white/45">Click "View Processes" to list running processes inside the VM via guest agent.</p>
      )}
    </div>
  );
}

// --- Network Detail ---

interface NetworkInterface {
  name: string;
  mac: string;
  source: string;
  model: string;
  rx_bytes: number;
  tx_bytes: number;
  rx_packets: number;
  tx_packets: number;
  rx_errors: number;
  tx_errors: number;
  rx_drops: number;
  tx_drops: number;
}

function NetworkDetailCard({ vmName }: { vmName: string }) {
  const { data } = useQuery({
    queryKey: ['vm-network-detail', vmName],
    queryFn: () => fetchAPI<{ interfaces: NetworkInterface[] }>(`/vms/${encodeURIComponent(vmName)}/network-detail`),
    refetchInterval: 10000,
    retry: false,
  });

  if (!data || !data.interfaces || data.interfaces.length === 0) return null;

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
      <div className="flex items-center gap-2 mb-3">
        <Network className="h-4 w-4 text-teal-400" />
        <span className="text-sm font-semibold text-white">Network Detail</span>
        <span className="text-[10px] text-white/45 ml-auto">{data.interfaces.length} interface(s)</span>
      </div>

      <div className="space-y-3">
        {data.interfaces.map((iface) => (
          <div key={iface.name} className="p-3 tahoe-glass-card rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Network className="h-3 w-3 text-teal-400 flex-shrink-0" />
              <span className="text-xs text-white/90 font-mono font-medium">{iface.name}</span>
              {iface.model && (
                <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${
                  iface.model === 'virtio' ? 'bg-green-500/10 text-green-400' : 'bg-white/[0.06] text-white/55'
                }`}>{iface.model}</span>
              )}
            </div>

            {/* Interface info */}
            <div className="grid grid-cols-2 gap-1.5 mb-2">
              {iface.mac && (
                <div className="text-[10px]">
                  <span className="text-white/45">MAC: </span>
                  <span className="text-white/75 font-mono">{iface.mac}</span>
                </div>
              )}
              {iface.source && (
                <div className="text-[10px]">
                  <span className="text-white/45">Bridge: </span>
                  <span className="text-white/75 font-mono">{iface.source}</span>
                </div>
              )}
            </div>

            {/* Traffic stats */}
            <div className="overflow-x-auto">
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="text-white/45">
                    <th className="text-left py-0.5 font-medium">Direction</th>
                    <th className="text-right py-0.5 font-medium">Bytes</th>
                    <th className="text-right py-0.5 font-medium">Packets</th>
                    <th className="text-right py-0.5 font-medium">Errors</th>
                    <th className="text-right py-0.5 font-medium">Drops</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-t border-white/[0.06]">
                    <td className="py-1 text-white/75">RX</td>
                    <td className="py-1 text-right text-white/55">{fmtNetBytes(iface.rx_bytes)}</td>
                    <td className="py-1 text-right text-white/55">{iface.rx_packets.toLocaleString()}</td>
                    <td className={`py-1 text-right font-medium ${iface.rx_errors > 0 ? 'text-red-400' : 'text-white/55'}`}>{iface.rx_errors}</td>
                    <td className={`py-1 text-right font-medium ${iface.rx_drops > 0 ? 'text-red-400' : 'text-white/55'}`}>{iface.rx_drops}</td>
                  </tr>
                  <tr className="border-t border-white/[0.06]">
                    <td className="py-1 text-white/75">TX</td>
                    <td className="py-1 text-right text-white/55">{fmtNetBytes(iface.tx_bytes)}</td>
                    <td className="py-1 text-right text-white/55">{iface.tx_packets.toLocaleString()}</td>
                    <td className={`py-1 text-right font-medium ${iface.tx_errors > 0 ? 'text-red-400' : 'text-white/55'}`}>{iface.tx_errors}</td>
                    <td className={`py-1 text-right font-medium ${iface.tx_drops > 0 ? 'text-red-400' : 'text-white/55'}`}>{iface.tx_drops}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function fmtNetBytes(b: number): string {
  if (b > 1e9) return (b / 1e9).toFixed(1) + ' GB';
  if (b > 1e6) return (b / 1e6).toFixed(1) + ' MB';
  if (b > 1e3) return (b / 1e3).toFixed(1) + ' KB';
  return b + ' B';
}

// --- Create VM Modal ---

function CreateVMModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState({
    name: '',
    vcpus: 2,
    memory_mb: 2048,
    disk_gb: 20,
    os_variant: 'generic',
    network: 'default',
    cdrom: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) {
      setError('VM name is required');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { ...form };
      if (!form.cdrom) delete body.cdrom;
      await fetchAPI('/vms/create', {
        method: 'POST',
        body: JSON.stringify(body),
      });
      showToast('success', `VM "${form.name}" created successfully`);
      onCreated();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="glass border border-white/[0.08] rounded-xl shadow-2xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.06]">
          <div className="flex items-center gap-2">
            <Plus className="h-4 w-4 text-blue-400" />
            <h3 className="text-sm font-semibold text-white">Create Virtual Machine</h3>
          </div>
          <button onClick={onClose} className="text-white/55 hover:text-white transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {error && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-xs text-red-400">
              <AlertCircle className="h-3.5 w-3.5 inline mr-1" /> {error}
            </div>
          )}

          {/* Name */}
          <div>
            <label className="block text-xs text-white/55 mb-1">Name <span className="text-red-400">*</span></label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="my-new-vm"
              disabled={loading}
              className="w-full px-3 py-2 tahoe-glass-card border border-white/[0.12] rounded-lg text-sm text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
              autoFocus
            />
          </div>

          {/* vCPUs and Memory */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-white/55 mb-1">vCPUs</label>
              <input
                type="number"
                min={1}
                max={64}
                value={form.vcpus}
                onChange={(e) => setForm({ ...form, vcpus: parseInt(e.target.value) || 1 })}
                disabled={loading}
                className="w-full px-3 py-2 tahoe-glass-card border border-white/[0.12] rounded-lg text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
              />
            </div>
            <div>
              <label className="block text-xs text-white/55 mb-1">Memory (MB)</label>
              <input
                type="number"
                min={256}
                step={256}
                value={form.memory_mb}
                onChange={(e) => setForm({ ...form, memory_mb: parseInt(e.target.value) || 1024 })}
                disabled={loading}
                className="w-full px-3 py-2 tahoe-glass-card border border-white/[0.12] rounded-lg text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
              />
            </div>
          </div>

          {/* Disk GB */}
          <div>
            <label className="block text-xs text-white/55 mb-1">Disk (GB)</label>
            <input
              type="number"
              min={1}
              value={form.disk_gb}
              onChange={(e) => setForm({ ...form, disk_gb: parseInt(e.target.value) || 10 })}
              disabled={loading}
              className="w-full px-3 py-2 tahoe-glass-card border border-white/[0.12] rounded-lg text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
            />
          </div>

          {/* OS Variant */}
          <div>
            <label className="block text-xs text-white/55 mb-1">OS Variant</label>
            <select
              value={form.os_variant}
              onChange={(e) => setForm({ ...form, os_variant: e.target.value })}
              disabled={loading}
              className="w-full px-3 py-2 tahoe-glass-card border border-white/[0.12] rounded-lg text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
            >
              <option value="generic">Generic</option>
              <option value="fedora-unknown">Fedora</option>
              <option value="ubuntu24.04">Ubuntu</option>
              <option value="win10">Windows 10</option>
              <option value="win11">Windows 11</option>
              <option value="rhel9-unknown">RHEL 9</option>
            </select>
          </div>

          {/* Network */}
          <div>
            <label className="block text-xs text-white/55 mb-1">Network</label>
            <input
              type="text"
              value={form.network}
              onChange={(e) => setForm({ ...form, network: e.target.value })}
              placeholder="default"
              disabled={loading}
              className="w-full px-3 py-2 tahoe-glass-card border border-white/[0.12] rounded-lg text-sm text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
            />
          </div>

          {/* ISO Path */}
          <div>
            <label className="block text-xs text-white/55 mb-1">ISO Path (optional)</label>
            <input
              type="text"
              value={form.cdrom}
              onChange={(e) => setForm({ ...form, cdrom: e.target.value })}
              placeholder="/path/to/installer.iso"
              disabled={loading}
              className="w-full px-3 py-2 tahoe-glass-card border border-white/[0.12] rounded-lg text-sm text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
            />
            <p className="text-[10px] text-white/45 mt-1">Leave empty to create a blank VM with disk boot</p>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border border-white/[0.12] text-white/75 rounded-lg text-sm transition-colors hover:bg-white/[0.04]"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex items-center gap-1.5 px-4 py-2 bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-white rounded-lg text-sm font-medium transition-all disabled:opacity-50"
            >
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              Create VM
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function CloneCard({ vmName }: { vmName: string }) {
  const queryClient = useQueryClient();
  const [cloneName, setCloneName] = useState('');
  const [showInput, setShowInput] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleClone = async () => {
    const name = cloneName.trim() || `${vmName}-clone`;
    setLoading(true);
    setError(null);
    try {
      await fetchAPI('/vms/clone', {
        method: 'POST',
        body: JSON.stringify({ source: vmName, name }),
      });
      showToast('success', `VM cloned as "${name}"`);
      queryClient.invalidateQueries({ queryKey: ['libvirt-vms'] });
      setShowInput(false);
      setCloneName('');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
      <div className="flex items-center gap-2 mb-3">
        <Copy className="h-4 w-4 text-blue-400" />
        <span className="text-sm font-semibold text-white">Clone</span>
      </div>
      {showInput ? (
        <div className="space-y-2">
          <input
            type="text"
            value={cloneName}
            onChange={(e) => setCloneName(e.target.value)}
            placeholder={`${vmName}-clone`}
            className="w-full px-3 py-2 tahoe-glass-card border border-white/[0.12] rounded-lg text-sm text-white placeholder-white/40 focus:outline-none focus:ring-1 focus:ring-blue-500"
            autoFocus
          />
          {error && (
            <div className="text-xs text-red-400"><AlertCircle className="h-3 w-3 inline mr-1" />{error}</div>
          )}
          <div className="flex gap-2">
            <button
              onClick={handleClone}
              disabled={loading}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
            >
              {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Copy className="h-3 w-3" />} Clone
            </button>
            <button
              onClick={() => { setShowInput(false); setError(null); }}
              className="px-3 py-1.5 border border-white/[0.12] text-white/75 rounded-lg text-xs hover:bg-white/[0.04] transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setShowInput(true)}
          className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-blue-600/20 to-cyan-600/20 hover:from-blue-600/30 hover:to-cyan-600/30 border border-blue-500/30 text-blue-400 font-medium rounded-lg py-2 px-4 transition-all text-sm"
        >
          <Copy className="h-4 w-4" /> Clone VM
        </button>
      )}
    </div>
  );
}

function ResizeCard({ vmName, vcpus, memory, isRunning }: { vmName: string; vcpus: string; memory: string; isRunning: boolean }) {
  const queryClient = useQueryClient();
  const [editingCPU, setEditingCPU] = useState(false);
  const [editingMem, setEditingMem] = useState(false);
  const [cpuVal, setCpuVal] = useState('');
  const [memVal, setMemVal] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Parse current memory from "XXXX KiB" to MB
  const currentMemMB = memory ? Math.round(parseInt(memory.replace(/[^0-9]/g, '')) / 1024) : 0;
  const currentVCPUs = vcpus || '1';

  const handleResize = async (payload: { vcpus?: number; memory_mb?: number }) => {
    setLoading(true);
    setError(null);
    try {
      await fetchAPI(`/vms/${vmName}/resize`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      showToast('success', 'VM resized successfully');
      queryClient.invalidateQueries({ queryKey: ['libvirt-vms'] });
      setEditingCPU(false);
      setEditingMem(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
      <div className="flex items-center gap-2 mb-3">
        <Cpu className="h-4 w-4 text-cyan-400" />
        <span className="text-sm font-semibold text-white">Resize</span>
        <span className="text-[10px] text-white/45 ml-auto">{isRunning ? 'hot resize' : 'config change'}</span>
      </div>
      {error && (
        <div className="text-xs text-red-400 mb-2"><AlertCircle className="h-3 w-3 inline mr-1" />{error}</div>
      )}
      <div className="space-y-2">
        {/* vCPUs */}
        <div className="flex items-center justify-between p-2 tahoe-glass-card rounded-lg">
          <div className="flex items-center gap-1.5 text-xs text-white/55"><Cpu className="h-3 w-3 text-blue-400" /> vCPUs</div>
          {editingCPU ? (
            <div className="flex items-center gap-1.5">
              <input
                type="number"
                min={1}
                max={64}
                value={cpuVal}
                onChange={(e) => setCpuVal(e.target.value)}
                className="w-16 px-2 py-1 glass border border-white/[0.12] rounded text-xs text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
                autoFocus
              />
              <button
                onClick={() => handleResize({ vcpus: parseInt(cpuVal) || 1 })}
                disabled={loading}
                className="h-6 w-6 rounded hover:bg-green-500/10 text-green-400 flex items-center justify-center transition-colors disabled:opacity-50"
              >
                {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
              </button>
              <button
                onClick={() => setEditingCPU(false)}
                className="h-6 w-6 rounded hover:bg-white/[0.04] text-white/55 flex items-center justify-center transition-colors"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-white/75 font-medium">{currentVCPUs}</span>
              <button
                onClick={() => { setCpuVal(currentVCPUs); setEditingCPU(true); setError(null); }}
                className="h-5 w-5 rounded hover:bg-blue-500/10 text-white/45 hover:text-blue-400 flex items-center justify-center transition-colors"
              >
                <Edit2 className="h-3 w-3" />
              </button>
            </div>
          )}
        </div>

        {/* Memory */}
        <div className="flex items-center justify-between p-2 tahoe-glass-card rounded-lg">
          <div className="flex items-center gap-1.5 text-xs text-white/55"><MemoryStick className="h-3 w-3 text-green-400" /> Memory</div>
          {editingMem ? (
            <div className="flex items-center gap-1.5">
              <input
                type="number"
                min={256}
                step={256}
                value={memVal}
                onChange={(e) => setMemVal(e.target.value)}
                className="w-20 px-2 py-1 glass border border-white/[0.12] rounded text-xs text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
                autoFocus
              />
              <span className="text-[10px] text-white/45">MB</span>
              <button
                onClick={() => handleResize({ memory_mb: parseInt(memVal) || 1024 })}
                disabled={loading}
                className="h-6 w-6 rounded hover:bg-green-500/10 text-green-400 flex items-center justify-center transition-colors disabled:opacity-50"
              >
                {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
              </button>
              <button
                onClick={() => setEditingMem(false)}
                className="h-6 w-6 rounded hover:bg-white/[0.04] text-white/55 flex items-center justify-center transition-colors"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-white/75 font-medium">{currentMemMB > 0 ? `${currentMemMB} MB` : (memory || '-')}</span>
              <button
                onClick={() => { setMemVal(String(currentMemMB || 1024)); setEditingMem(true); setError(null); }}
                className="h-5 w-5 rounded hover:bg-blue-500/10 text-white/45 hover:text-blue-400 flex items-center justify-center transition-colors"
              >
                <Edit2 className="h-3 w-3" />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MigrateToKubeVirtCard({ vmName, vmState: _vmState }: { vmName: string; vmState: string }) {
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ namespace: 'default', targetName: vmName, storageClass: '', autoStop: true, autoStart: true });
  const queryClient = useQueryClient();

  const migrate = useMutation({
    mutationFn: () => fetchAPI<any>(`/vms/${encodeURIComponent(vmName)}/migrate-to-kubevirt`, {
      method: 'POST',
      body: JSON.stringify({ namespace: form.namespace, kubevirt_vm_name: form.targetName, storage_class: form.storageClass, auto_stop: form.autoStop, auto_start: form.autoStart }),
    }),
    onSuccess: () => {
      showToast('success', `VM "${vmName}" migrated to KubeVirt`);
      queryClient.invalidateQueries({ queryKey: ['libvirt-vms'] });
      setShowForm(false);
    },
    onError: (err) => showToast('error', (err as Error).message),
  });

  return (
    <div className="tahoe-glass-card rounded-xl border border-cyan-500/20 p-4">
      <div className="flex items-center gap-2 mb-2">
        <Cloud className="h-4 w-4 text-cyan-400" />
        <span className="text-sm font-semibold text-white">Migrate to KubeVirt</span>
      </div>
      {showForm ? (
        <div className="space-y-2">
          <input type="text" value={form.targetName} onChange={e => setForm(f => ({ ...f, targetName: e.target.value }))}
            placeholder="Target VM name" className="w-full px-2 py-1.5 tahoe-glass-card border border-white/[0.08] rounded text-xs text-white/90 focus:outline-none focus:ring-1 focus:ring-cyan-500" />
          <input type="text" value={form.namespace} onChange={e => setForm(f => ({ ...f, namespace: e.target.value }))}
            placeholder="Namespace" className="w-full px-2 py-1.5 tahoe-glass-card border border-white/[0.08] rounded text-xs text-white/90 focus:outline-none focus:ring-1 focus:ring-cyan-500" />
          <input type="text" value={form.storageClass} onChange={e => setForm(f => ({ ...f, storageClass: e.target.value }))}
            placeholder="Storage class (optional)" className="w-full px-2 py-1.5 tahoe-glass-card border border-white/[0.08] rounded text-xs text-white/90 focus:outline-none focus:ring-1 focus:ring-cyan-500" />
          <label className="flex items-center gap-2 text-xs text-white/55">
            <input type="checkbox" checked={form.autoStop} onChange={e => setForm(f => ({ ...f, autoStop: e.target.checked }))} /> Auto-stop source VM
          </label>
          <label className="flex items-center gap-2 text-xs text-white/55">
            <input type="checkbox" checked={form.autoStart} onChange={e => setForm(f => ({ ...f, autoStart: e.target.checked }))} /> Auto-start on KubeVirt
          </label>
          {migrate.isError && (
            <div className="text-xs text-red-400"><AlertCircle className="h-3 w-3 inline mr-1" />{(migrate.error as Error).message}</div>
          )}
          {migrate.isSuccess && (
            <div className="text-xs text-green-400">Migration complete! VM running on KubeVirt.</div>
          )}
          <div className="flex gap-2">
            <button disabled={migrate.isPending} onClick={() => migrate.mutate()}
              className="flex-1 px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded text-xs font-medium disabled:opacity-50 transition-colors">
              {migrate.isPending ? 'Migrating...' : 'Start Migration'}
            </button>
            <button onClick={() => setShowForm(false)} className="px-3 py-1.5 border border-white/[0.12] text-white/75 rounded text-xs hover:bg-white/[0.04] transition-colors">Cancel</button>
          </div>
        </div>
      ) : (
        <button onClick={() => { setShowForm(true); setForm(f => ({ ...f, targetName: vmName })); }}
          className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-cyan-600/20 to-blue-600/20 hover:from-cyan-600/30 hover:to-blue-600/30 border border-cyan-500/30 text-cyan-400 font-medium rounded-lg py-2 px-4 transition-all text-sm">
          <ArrowRightLeft className="h-4 w-4" /> Migrate to KubeVirt
        </button>
      )}
    </div>
  );
}

function ImportVMModal({ onClose, onImported }: { onClose: () => void; onImported: () => void }) {
  const [form, setForm] = useState({
    name: '',
    disk_path: '',
    vcpus: 2,
    memory_mb: 2048,
    os_variant: 'generic',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) {
      setError('VM name is required');
      return;
    }
    if (!form.disk_path.trim()) {
      setError('Disk path is required');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await fetchAPI('/vms/import', {
        method: 'POST',
        body: JSON.stringify(form),
      });
      showToast('success', `VM "${form.name}" imported successfully`);
      onImported();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="glass border border-white/[0.08] rounded-xl shadow-2xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.06]">
          <div className="flex items-center gap-2">
            <Upload className="h-4 w-4 text-green-400" />
            <h3 className="text-sm font-semibold text-white">Import VM from Disk Image</h3>
          </div>
          <button onClick={onClose} className="text-white/55 hover:text-white transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {error && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-xs text-red-400">
              <AlertCircle className="h-3.5 w-3.5 inline mr-1" /> {error}
            </div>
          )}

          {/* Name */}
          <div>
            <label className="block text-xs text-white/55 mb-1">Name <span className="text-red-400">*</span></label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="imported-vm"
              disabled={loading}
              className="w-full px-3 py-2 tahoe-glass-card border border-white/[0.12] rounded-lg text-sm text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
              autoFocus
            />
          </div>

          {/* Disk Path */}
          <div>
            <label className="block text-xs text-white/55 mb-1">Disk Path <span className="text-red-400">*</span></label>
            <input
              type="text"
              value={form.disk_path}
              onChange={(e) => setForm({ ...form, disk_path: e.target.value })}
              placeholder="/var/lib/libvirt/images/disk.qcow2"
              disabled={loading}
              className="w-full px-3 py-2 tahoe-glass-card border border-white/[0.12] rounded-lg text-sm text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
            />
            <p className="text-[10px] text-white/45 mt-1">Absolute path to an existing disk image (qcow2, vmdk, raw, etc.)</p>
          </div>

          {/* vCPUs and Memory */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-white/55 mb-1">vCPUs</label>
              <input
                type="number"
                min={1}
                max={64}
                value={form.vcpus}
                onChange={(e) => setForm({ ...form, vcpus: parseInt(e.target.value) || 1 })}
                disabled={loading}
                className="w-full px-3 py-2 tahoe-glass-card border border-white/[0.12] rounded-lg text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
              />
            </div>
            <div>
              <label className="block text-xs text-white/55 mb-1">Memory (MB)</label>
              <input
                type="number"
                min={256}
                step={256}
                value={form.memory_mb}
                onChange={(e) => setForm({ ...form, memory_mb: parseInt(e.target.value) || 1024 })}
                disabled={loading}
                className="w-full px-3 py-2 tahoe-glass-card border border-white/[0.12] rounded-lg text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
              />
            </div>
          </div>

          {/* OS Variant */}
          <div>
            <label className="block text-xs text-white/55 mb-1">OS Variant</label>
            <select
              value={form.os_variant}
              onChange={(e) => setForm({ ...form, os_variant: e.target.value })}
              disabled={loading}
              className="w-full px-3 py-2 tahoe-glass-card border border-white/[0.12] rounded-lg text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
            >
              <option value="generic">Generic</option>
              <option value="fedora-unknown">Fedora</option>
              <option value="ubuntu24.04">Ubuntu</option>
              <option value="win10">Windows 10</option>
              <option value="win11">Windows 11</option>
              <option value="rhel9-unknown">RHEL 9</option>
            </select>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border border-white/[0.12] text-white/75 rounded-lg text-sm transition-colors hover:bg-white/[0.04]"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex items-center gap-1.5 px-4 py-2 bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-500 hover:to-emerald-500 text-white rounded-lg text-sm font-medium transition-all disabled:opacity-50"
            >
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
              Import VM
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// --- Disk & CDROM Management ---

interface DiskInfo {
  target: string;
  source: string;
  type?: string;
}

function DiskManagementCard({ vmName }: { vmName: string }) {
  const queryClient = useQueryClient();
  const [showAddForm, setShowAddForm] = useState(false);
  const [addForm, setAddForm] = useState({ size_gb: 10, format: 'qcow2', bus: 'virtio' });
  const [isoPath, setIsoPath] = useState('');
  const [showCdromInput, setShowCdromInput] = useState(false);

  // Fetch current disks from storage-detail.
  const { data: storageDetail } = useQuery({
    queryKey: ['storage-detail', vmName],
    queryFn: () => fetchAPI<{ disks: DiskInfo[] }>(`/vms/${vmName}/storage-detail`),
    refetchInterval: 10000,
    retry: false,
  });

  const attachDisk = useMutation({
    mutationFn: (params: { size_gb: number; format: string; bus: string }) =>
      fetchAPI<{ message: string }>(`/vms/${vmName}/disk/attach`, {
        method: 'POST',
        body: JSON.stringify(params),
      }),
    onSuccess: (data) => {
      showToast('success', data.message);
      queryClient.invalidateQueries({ queryKey: ['storage-detail', vmName] });
      setShowAddForm(false);
    },
    onError: (err) => showToast('error', (err as Error).message),
  });

  const detachDisk = useMutation({
    mutationFn: (target: string) =>
      fetchAPI<{ message: string }>(`/vms/${vmName}/disk/detach`, {
        method: 'POST',
        body: JSON.stringify({ target }),
      }),
    onSuccess: (data) => {
      showToast('success', data.message);
      queryClient.invalidateQueries({ queryKey: ['storage-detail', vmName] });
    },
    onError: (err) => showToast('error', (err as Error).message),
  });

  const cdromChange = useMutation({
    mutationFn: (path: string) =>
      fetchAPI<{ message: string }>(`/vms/${vmName}/cdrom/change`, {
        method: 'POST',
        body: JSON.stringify({ path }),
      }),
    onSuccess: (data) => {
      showToast('success', data.message);
      setShowCdromInput(false);
      setIsoPath('');
    },
    onError: (err) => showToast('error', (err as Error).message),
  });

  const disks = storageDetail?.disks || [];

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <HardDrive className="h-4 w-4 text-yellow-400" />
          <span className="text-sm font-semibold text-white">Disk Management</span>
          <span className="text-[10px] text-white/45">{disks.length} disk(s)</span>
        </div>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors"
        >
          <Plus className="h-3 w-3" /> Add Disk
        </button>
      </div>

      {/* Add Disk Form */}
      {showAddForm && (
        <div className="mb-3 p-3 tahoe-glass-card rounded-lg border border-white/[0.06] space-y-2">
          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="block text-[10px] text-white/45 mb-0.5">Size (GB)</label>
              <input
                type="number"
                min={1}
                max={2048}
                value={addForm.size_gb}
                onChange={(e) => setAddForm({ ...addForm, size_gb: parseInt(e.target.value) || 10 })}
                className="w-full px-2 py-1.5 tahoe-glass-card border border-white/[0.12] rounded text-xs text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-[10px] text-white/45 mb-0.5">Format</label>
              <select
                value={addForm.format}
                onChange={(e) => setAddForm({ ...addForm, format: e.target.value })}
                className="w-full px-2 py-1.5 tahoe-glass-card border border-white/[0.12] rounded text-xs text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                <option value="qcow2">qcow2</option>
                <option value="raw">raw</option>
              </select>
            </div>
            <div>
              <label className="block text-[10px] text-white/45 mb-0.5">Bus</label>
              <select
                value={addForm.bus}
                onChange={(e) => setAddForm({ ...addForm, bus: e.target.value })}
                className="w-full px-2 py-1.5 tahoe-glass-card border border-white/[0.12] rounded text-xs text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                <option value="virtio">virtio</option>
                <option value="sata">sata</option>
                <option value="scsi">scsi</option>
              </select>
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setShowAddForm(false)}
              className="px-2.5 py-1 text-xs text-white/55 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={() => attachDisk.mutate(addForm)}
              disabled={attachDisk.isPending}
              className="flex items-center gap-1 px-3 py-1 bg-blue-600 text-white rounded text-xs hover:bg-blue-500 transition-colors disabled:opacity-50"
            >
              {attachDisk.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />}
              Attach
            </button>
          </div>
        </div>
      )}

      {/* Current Disks */}
      {disks.length > 0 ? (
        <div className="space-y-1.5">
          {disks.map((disk) => {
            const isCdrom = disk.target?.startsWith('hd') && disk.source === '';
            return (
              <div key={disk.target} className="flex items-center gap-2 p-2 tahoe-glass-card rounded-lg text-xs">
                {isCdrom ? (
                  <Disc className="h-3 w-3 text-cyan-400 flex-shrink-0" />
                ) : (
                  <HardDrive className="h-3 w-3 text-yellow-400 flex-shrink-0" />
                )}
                <span className="text-white/75 font-mono w-8 flex-shrink-0">{disk.target}</span>
                <span className="text-white/45 truncate flex-1 min-w-0 font-mono text-[10px]">
                  {disk.source || '(empty)'}
                </span>
                {isCdrom ? (
                  <button
                    onClick={() => setShowCdromInput(!showCdromInput)}
                    className="h-6 w-6 rounded hover:bg-cyan-500/10 text-white/55 hover:text-cyan-400 flex items-center justify-center transition-colors flex-shrink-0"
                    title="Change media"
                  >
                    <Disc className="h-3 w-3" />
                  </button>
                ) : (
                  // Only show detach for non-primary disks (not vda/sda/hda).
                  !/^[a-z]{2}a$/.test(disk.target) && (
                    <button
                      onClick={() => detachDisk.mutate(disk.target)}
                      disabled={detachDisk.isPending}
                      className="h-6 w-6 rounded hover:bg-red-500/10 text-white/55 hover:text-red-400 flex items-center justify-center transition-colors flex-shrink-0"
                      title="Detach disk"
                    >
                      <MinusCircle className="h-3 w-3" />
                    </button>
                  )
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-xs text-white/45 text-center py-2">No disk info available</div>
      )}

      {/* CDROM Insert/Eject */}
      {showCdromInput && (
        <div className="mt-2 p-2.5 tahoe-glass-card rounded-lg border border-white/[0.06] space-y-2">
          <div className="flex items-center gap-2">
            <Disc className="h-3.5 w-3.5 text-cyan-400" />
            <span className="text-xs text-white/75">CDROM Media</span>
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={isoPath}
              onChange={(e) => setIsoPath(e.target.value)}
              placeholder="/path/to/image.iso"
              className="flex-1 px-2.5 py-1.5 tahoe-glass-card border border-white/[0.12] rounded text-xs text-white placeholder-white/40 font-mono focus:outline-none focus:ring-1 focus:ring-cyan-500"
            />
            <button
              onClick={() => cdromChange.mutate(isoPath)}
              disabled={cdromChange.isPending}
              className="px-3 py-1.5 bg-cyan-600 text-white rounded text-xs hover:bg-cyan-500 transition-colors disabled:opacity-50"
            >
              {cdromChange.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : isoPath ? 'Insert' : 'Eject'}
            </button>
          </div>
          <button
            onClick={() => { cdromChange.mutate(''); }}
            disabled={cdromChange.isPending}
            className="flex items-center gap-1 text-[10px] text-yellow-400 hover:text-yellow-300 transition-colors"
          >
            <MinusCircle className="h-3 w-3" /> Eject current media
          </button>
        </div>
      )}
    </div>
  );
}

// --- VM Events ---

interface VMEvent {
  timestamp: string;
  type: string;
  action: string;
  detail: string;
}

function EventsCard({ vmName }: { vmName: string }) {
  const { data } = useQuery({
    queryKey: ['vm-events', vmName],
    queryFn: () => fetchAPI<{ events: VMEvent[] }>(`/vms/${vmName}/events`),
    refetchInterval: 15000,
    retry: false,
  });

  const events = data?.events || [];

  const getEventIcon = (type: string, action: string) => {
    if (type === 'disk_error') return { icon: AlertTriangle, color: 'text-red-400', bg: 'bg-red-500/10' };
    if (action === 'current_state') return { icon: Activity, color: 'text-blue-400', bg: 'bg-blue-500/10' };
    if (action.includes('start')) return { icon: Play, color: 'text-green-400', bg: 'bg-green-500/10' };
    if (action.includes('stop') || action.includes('shutdown') || action.includes('destroy'))
      return { icon: Power, color: 'text-red-400', bg: 'bg-red-500/10' };
    if (action.includes('delete')) return { icon: Trash2, color: 'text-red-400', bg: 'bg-red-500/10' };
    if (action.includes('reboot')) return { icon: RefreshCw, color: 'text-yellow-400', bg: 'bg-yellow-500/10' };
    if (action.includes('snapshot') || action.includes('snap')) return { icon: Camera, color: 'text-purple-400', bg: 'bg-purple-500/10' };
    if (action.includes('disk') || action.includes('cdrom')) return { icon: HardDrive, color: 'text-yellow-400', bg: 'bg-yellow-500/10' };
    if (action.includes('promote')) return { icon: Zap, color: 'text-cyan-400', bg: 'bg-cyan-500/10' };
    return { icon: History, color: 'text-white/55', bg: 'bg-white/[0.06]' };
  };

  const formatEventTime = (ts: string): string => {
    const now = Date.now();
    const then = new Date(ts).getTime();
    if (isNaN(then)) return ts;
    const diffSec = Math.floor((now - then) / 1000);
    if (diffSec < 60) return `${diffSec}s ago`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDay = Math.floor(diffHr / 24);
    return `${diffDay}d ago`;
  };

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
      <div className="flex items-center gap-2 mb-3">
        <Clock className="h-4 w-4 text-indigo-400" />
        <span className="text-sm font-semibold text-white">Events</span>
        <span className="text-[10px] text-white/45">{events.length}</span>
        <span className="text-[10px] text-white/45 ml-auto">auto-refresh 15s</span>
      </div>

      {events.length > 0 ? (
        <div className="space-y-1 max-h-64 overflow-auto">
          {events.map((event, i) => {
            const cfg = getEventIcon(event.type, event.action);
            const Icon = cfg.icon;
            return (
              <div key={i} className="flex items-start gap-2 p-2 rounded-lg hover:tahoe-glass-card transition-colors">
                <div className={`w-5 h-5 rounded flex items-center justify-center flex-shrink-0 mt-0.5 ${cfg.bg}`}>
                  <Icon className={`h-3 w-3 ${cfg.color}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${cfg.bg} ${cfg.color}`}>
                      {event.action}
                    </span>
                    <span className="text-[10px] text-white/45 flex-shrink-0">{formatEventTime(event.timestamp)}</span>
                  </div>
                  <p className="text-xs text-white/55 mt-0.5 truncate">{event.detail}</p>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-xs text-white/45 text-center py-3">No events recorded</div>
      )}
    </div>
  );
}
