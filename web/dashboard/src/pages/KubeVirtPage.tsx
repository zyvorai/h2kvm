// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Cloud, Play, Square, Box, Network, AlertCircle, Cpu, MemoryStick,
  HardDrive, Monitor, Clock, Server, Terminal, Activity, RefreshCw,
  Pause, ArrowRightLeft, Trash2, Copy, ExternalLink,
} from 'lucide-react';
import { fetchAPI } from '../api/client';
import { showToast } from '../components/Toast';
import { KVConsoleModal } from '../components/KVConsole';
import { TahoeHero } from '../components/ui/TahoeHero';

interface KubeVM {
  name: string;
  namespace: string;
  status: string;
  ready: boolean;
  running: boolean;
  created: string;
  cpu: number;
  memory: string;
  node: string;
  ip: string;
  os_type: string;
  labels: Record<string, string>;
  interfaces: { name: string; ipAddress: string; mac: string }[];
  volumes: { name: string; type: string }[];
  conditions: { type: string; status: string }[];
  migrating: boolean;
  migration: { sourceNode: string; targetNode: string; phase: string; startTime: string; endTime: string; completed: boolean } | null;
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

function detectKubeVirtOS(name: string, spec: any): string {
  const lower = name.toLowerCase();
  if (lower.includes('win')) return 'windows';
  if (lower.includes('ubuntu')) return 'ubuntu';
  if (lower.includes('fedora')) return 'fedora';
  if (lower.includes('centos') || lower.includes('rhel') || lower.includes('rocky') || lower.includes('alma')) return 'rhel';
  if (lower.includes('debian')) return 'debian';

  // Check KubeVirt domain spec for Windows hints
  const domain = spec?.domain || spec?.template?.spec?.domain || {};
  const features = domain?.features || {};
  if (features?.hyperv) return 'windows';

  const clock = domain?.clock || {};
  if (clock?.utc === false || clock?.timezone === 'localtime') return 'windows';

  // Check annotations
  const annotations = spec?.metadata?.annotations || {};
  const osAnnotation = (annotations['vm.kubevirt.io/os'] || annotations['kubevirt.io/os'] || '').toLowerCase();
  if (osAnnotation.includes('win')) return 'windows';
  if (osAnnotation) return osAnnotation;

  return 'linux';
}

function parseVMs(items: any[]): KubeVM[] {
  return (items || []).map((item: any) => {
    const meta = item?.metadata || {};
    const spec = item?.spec?.template?.spec || item?.spec || {};
    const status = item?.status || {};
    const domain = spec?.domain || {};
    const resources = domain?.resources?.requests || {};

    return {
      name: meta.name || '',
      namespace: meta.namespace || 'default',
      status: status.printableStatus || status.phase || 'Unknown',
      ready: status.ready === true,
      running: status.printableStatus === 'Running' || status.phase === 'Running',
      created: meta.creationTimestamp || '',
      cpu: domain?.cpu?.cores || 1,
      memory: resources?.memory || domain?.memory?.guest || '?',
      node: status.nodeName || '',
      ip: status.interfaces?.[0]?.ipAddress || '',
      os_type: detectKubeVirtOS(meta.name || '', item?.spec || {}),
      labels: meta.labels || {},
      interfaces: (status.interfaces || []).map((i: any) => ({
        name: i.interfaceName || i.name || '',
        ipAddress: i.ipAddress || '',
        mac: i.mac || '',
      })),
      volumes: (spec?.volumes || []).map((v: any) => ({
        name: v.name || '',
        type: Object.keys(v).filter(k => k !== 'name')[0] || 'unknown',
      })),
      conditions: (status.conditions || []).map((c: any) => ({
        type: c.type || '',
        status: c.status || '',
      })),
      migrating: !!status.migrationState?.targetNode,
      migration: status.migrationState ? {
        sourceNode: status.migrationState.sourceNode || '',
        targetNode: status.migrationState.targetNode || '',
        phase: status.migrationState.migrationPhase || status.migrationState.phase || '',
        startTime: status.migrationState.startTimestamp || '',
        endTime: status.migrationState.endTimestamp || '',
        completed: status.migrationState.completed === true,
      } : null,
    };
  });
}

export function KubeVirtPage() {
  const queryClient = useQueryClient();
  const { data: rawVMs, isLoading: loadingVMs } = useQuery({
    queryKey: ['kubevirt-vms'],
    queryFn: () => fetchAPI<any[]>('/kubevirt/vms'),
    refetchInterval: 5000,
  });
  const { data: rawVMIs } = useQuery({
    queryKey: ['kubevirt-vmis'],
    queryFn: () => fetchAPI<any[]>('/kubevirt/vmis'),
    refetchInterval: 5000,
  });
  const [selectedVM, setSelectedVM] = useState<string | null>(null);
  const [consoleVM, setConsoleVM] = useState<{ name: string; ns: string } | null>(null);
  const [sshUser, setSshUser] = useState('root');

  const action = useMutation({
    mutationFn: ({ ns, name, act }: { ns: string; name: string; act: string }) =>
      fetchAPI<{ message: string }>(`/kubevirt/vms/${ns}/${name}/${act}`, { method: 'POST' }),
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['kubevirt-vms'] });
      queryClient.invalidateQueries({ queryKey: ['kubevirt-vmis'] });
      showToast('success', `${vars.act} ${vars.name} successful`);
    },
    onError: (err, vars) => {
      showToast('error', `${vars.act} ${vars.name} failed: ${(err as Error).message}`);
    },
  });

  const vms = parseVMs(rawVMs || []);
  const vmis = parseVMs(rawVMIs || []);

  // Merge VMI data into VMs
  const mergedVMs = vms.map(vm => {
    const vmi = vmis.find(v => v.name === vm.name && v.namespace === vm.namespace);
    if (vmi) {
      return { ...vm, running: true, status: 'Running', node: vmi.node, ip: vmi.ip, interfaces: vmi.interfaces };
    }
    return vm;
  });

  const selected = mergedVMs.find(v => v.name === selectedVM);
  const runningCount = mergedVMs.filter(v => v.running).length;

  return (
    <div>
      <TahoeHero
        icon={<Cloud className="w-5 h-5 text-purple-300" />}
        title="KubeVirt"
        subtitle={`${runningCount}/${mergedVMs.length} running — manage KubeVirt VMs on Kubernetes`}
      />

      {loadingVMs ? (
        <div className="space-y-2">{[1, 2, 3].map(i => <div key={i} className="skeleton h-16 rounded-xl" />)}</div>
      ) : mergedVMs.length === 0 ? (
        <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-12 text-center">
          <Cloud className="h-12 w-12 text-sky-400/30 mx-auto mb-3" />
          <div className="text-sm text-white/55">No KubeVirt VMs found</div>
          <div className="text-xs text-white/45 mt-1 max-w-md mx-auto">
            To deploy VMs to KubeVirt, run a migration with <code className="bg-white/[0.08] px-1 rounded">deploy_k8s: true</code> in your YAML config.
            Make sure a kubeconfig is configured in the <a href="/kubeconfigs" className="text-blue-400 hover:underline">Kubeconfigs</a> page.
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_400px] gap-6">
          {/* VM List */}
          <div className="tahoe-glass-card rounded-xl border border-white/[0.08] overflow-hidden">
            <div className="px-5 py-3 border-b border-white/[0.06] flex items-center gap-2">
              <Box className="h-4 w-4 text-purple-400" />
              <span className="text-sm font-semibold text-white">Virtual Machines</span>
              <span className="text-xs text-white/45 ml-auto">{mergedVMs.length} total</span>
            </div>

            <div className="divide-y divide-white/[0.06]">
              {mergedVMs.map((vm) => (
                <div
                  key={`${vm.namespace}/${vm.name}`}
                  onClick={() => setSelectedVM(vm.name)}
                  className={`flex items-center gap-4 px-5 py-3 cursor-pointer vm-card ${vm.running ? 'vm-running' : ''} ${
                    selectedVM === vm.name ? 'bg-blue-600/10 border-l-2 border-l-purple-500' : ''
                  }`}
                >
                  <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
                    vm.running ? 'bg-green-400 shadow-green-400/50 shadow-sm' :
                    vm.status === 'Stopped' ? 'bg-white/30' : 'bg-yellow-400'
                  }`} />

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-medium text-white truncate">{vm.name}</span>
                      <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full border ${
                        vm.os_type === 'windows' ? 'bg-blue-500/10 text-blue-400 border-blue-500/30' :
                        vm.os_type === 'ubuntu' ? 'bg-orange-500/10 text-orange-400 border-orange-500/30' :
                        vm.os_type === 'fedora' ? 'bg-blue-500/10 text-blue-400 border-blue-500/30' :
                        vm.os_type === 'rhel' ? 'bg-red-500/10 text-red-400 border-red-500/30' :
                        'bg-green-500/10 text-green-400 border-green-500/30'
                      }`}><OSIcon os={vm.os_type} /> {vm.os_type}</span>
                      {vm.labels?.['hyper2kvm.io/migrated'] && (
                        <span className="text-[10px] px-1.5 py-0.5 bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 rounded-full">migrated</span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-xs text-white/45 mt-0.5">
                      <span>{vm.namespace}</span>
                      <span className="flex items-center gap-1"><Cpu className="h-3 w-3" />{vm.cpu} vCPU</span>
                      <span className="flex items-center gap-1"><MemoryStick className="h-3 w-3" />{vm.memory}</span>
                      {vm.node && <span className="flex items-center gap-1"><Server className="h-3 w-3" />{vm.node}</span>}
                      {vm.ip && <span className="flex items-center gap-1 text-green-400"><Network className="h-3 w-3" />{vm.ip}</span>}
                    </div>
                  </div>

                  <div className="flex items-center gap-1">
                    {vm.running ? (
                      <button onClick={(e) => { e.stopPropagation(); action.mutate({ ns: vm.namespace, name: vm.name, act: 'stop' }); }}
                        className="h-7 w-7 rounded-lg hover:bg-red-500/10 text-white/55 hover:text-red-400 flex items-center justify-center transition-colors" title="Stop">
                        <Square className="h-3.5 w-3.5" />
                      </button>
                    ) : (
                      <button onClick={(e) => { e.stopPropagation(); action.mutate({ ns: vm.namespace, name: vm.name, act: 'start' }); }}
                        className="h-7 w-7 rounded-lg hover:bg-green-500/10 text-white/55 hover:text-green-400 flex items-center justify-center transition-colors" title="Start">
                        <Play className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>

                  <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${
                    vm.running ? 'bg-green-500/10 text-green-400' :
                    vm.status === 'Stopped' ? 'bg-white/[0.06] text-white/55' :
                    'bg-yellow-500/10 text-yellow-400'
                  }`}>{vm.status}</span>
                </div>
              ))}
            </div>
          </div>

          {/* VM Detail Panel */}
          <div className="space-y-4">
            {selected ? (
              <>
                {/* Header + Actions */}
                <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h3 className="text-lg font-semibold text-white">{selected.name}</h3>
                      <div className="text-xs text-white/45 mt-0.5">{selected.namespace}</div>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {selected.running ? (
                        <>
                          <ActionBtn icon={RefreshCw} label="Restart" color="blue" onClick={() => action.mutate({ ns: selected.namespace, name: selected.name, act: 'restart' })} />
                          <ActionBtn icon={Pause} label="Pause" color="yellow" onClick={() => action.mutate({ ns: selected.namespace, name: selected.name, act: 'pause' })} />
                          <ActionBtn icon={ArrowRightLeft} label="Migrate" color="purple" onClick={() => action.mutate({ ns: selected.namespace, name: selected.name, act: 'migrate' })} />
                          <ActionBtn icon={Square} label="Stop" color="red" onClick={() => action.mutate({ ns: selected.namespace, name: selected.name, act: 'stop' })} />
                        </>
                      ) : (
                        <ActionBtn icon={Play} label="Start" color="green" onClick={() => action.mutate({ ns: selected.namespace, name: selected.name, act: 'start' })} />
                      )}
                    </div>
                  </div>

                  {/* Stats Grid */}
                  <div className="grid grid-cols-2 gap-3">
                    <StatBox icon={Activity} label="Status" value={selected.status}
                      color={selected.running ? 'text-green-400' : 'text-white/55'} />
                    <StatBox icon={Cpu} label="CPU" value={`${selected.cpu} cores`} />
                    <StatBox icon={MemoryStick} label="Memory" value={selected.memory} />
                    <StatBox icon={Clock} label="Created" value={selected.created ? new Date(selected.created).toLocaleDateString() : '-'} />
                    <StatBox icon={Server} label="Node" value={selected.node || 'Not scheduled'} />
                    <StatBox icon={Network} label="IP" value={selected.ip || 'N/A'} color={selected.ip ? 'text-green-400' : undefined} />
                  </div>
                </div>

                {/* Live Migration */}
                {selected.migration && (
                  <div className="tahoe-glass-card rounded-xl border border-purple-500/30 p-5">
                    <div className="flex items-center gap-2 mb-3">
                      <ArrowRightLeft className="h-4 w-4 text-purple-400" />
                      <span className="text-sm font-semibold text-white">Live Migration</span>
                      <span className="text-[10px] px-1.5 py-0.5 bg-purple-500/15 text-purple-400 rounded-full">
                        {selected.migration.completed ? 'Completed' : selected.migration.phase || 'In Progress'}
                      </span>
                    </div>
                    <div className="space-y-2">
                      {/* Source → Target */}
                      <div className="flex items-center gap-2 p-2.5 tahoe-glass-card rounded-lg">
                        <Server className="h-3.5 w-3.5 text-blue-400 flex-shrink-0" />
                        <span className="text-xs text-white/75 font-mono">{selected.migration.sourceNode || '?'}</span>
                        <ArrowRightLeft className="h-3 w-3 text-purple-400 flex-shrink-0" />
                        <span className="text-xs text-white/75 font-mono">{selected.migration.targetNode || '?'}</span>
                      </div>
                      {/* Timing */}
                      {selected.migration.startTime && (
                        <div className="flex items-center gap-2 p-2.5 tahoe-glass-card rounded-lg">
                          <Clock className="h-3.5 w-3.5 text-blue-400 flex-shrink-0" />
                          <span className="text-xs text-white/55">Started:</span>
                          <span className="text-xs text-white/75">{new Date(selected.migration.startTime).toLocaleString()}</span>
                        </div>
                      )}
                      {selected.migration.endTime && (
                        <div className="flex items-center gap-2 p-2.5 tahoe-glass-card rounded-lg">
                          <Clock className="h-3.5 w-3.5 text-green-400 flex-shrink-0" />
                          <span className="text-xs text-white/55">Ended:</span>
                          <span className="text-xs text-white/75">{new Date(selected.migration.endTime).toLocaleString()}</span>
                          {selected.migration.startTime && (() => {
                            const durationMs = new Date(selected.migration.endTime).getTime() - new Date(selected.migration.startTime).getTime();
                            const secs = Math.round(durationMs / 1000);
                            return (
                              <span className="text-[10px] text-white/45 ml-auto">
                                {secs >= 60 ? `${Math.floor(secs / 60)}m ${secs % 60}s` : `${secs}s`}
                              </span>
                            );
                          })()}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Network Interfaces */}
                {selected.interfaces.length > 0 && (
                  <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
                    <div className="flex items-center gap-2 mb-3">
                      <Network className="h-4 w-4 text-cyan-400" />
                      <span className="text-sm font-semibold text-white">Network</span>
                    </div>
                    <div className="space-y-2">
                      {selected.interfaces.map((iface, i) => (
                        <div key={i} className="p-3 tahoe-glass-card rounded-lg border border-white/[0.06]">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-medium text-white">{iface.name || `eth${i}`}</span>
                            {iface.ipAddress && (
                              <span className="text-xs font-mono text-green-400">{iface.ipAddress}</span>
                            )}
                          </div>
                          {iface.mac && <div className="text-[10px] text-white/45 mt-1 font-mono">{iface.mac}</div>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Volumes */}
                {selected.volumes.length > 0 && (
                  <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
                    <div className="flex items-center gap-2 mb-3">
                      <HardDrive className="h-4 w-4 text-yellow-400" />
                      <span className="text-sm font-semibold text-white">Volumes</span>
                    </div>
                    <div className="space-y-2">
                      {selected.volumes.map((vol, i) => (
                        <div key={i} className="flex items-center gap-3 p-2.5 tahoe-glass-card rounded-lg border border-white/[0.06]">
                          <HardDrive className="h-3.5 w-3.5 text-yellow-400" />
                          <span className="text-xs text-white">{vol.name}</span>
                          <span className="text-[10px] text-white/45 ml-auto">{vol.type}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Conditions */}
                {selected.conditions.length > 0 && (
                  <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
                    <div className="flex items-center gap-2 mb-3">
                      <Monitor className="h-4 w-4 text-blue-400" />
                      <span className="text-sm font-semibold text-white">Conditions</span>
                    </div>
                    <div className="space-y-1.5">
                      {selected.conditions.map((cond, i) => (
                        <div key={i} className="flex items-center justify-between text-xs py-1">
                          <span className="text-white/55">{cond.type}</span>
                          <span className={cond.status === 'True' ? 'text-green-400' : 'text-white/45'}>{cond.status}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Console & Access */}
                <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
                  <div className="flex items-center gap-2 mb-3">
                    <Terminal className="h-4 w-4 text-green-400" />
                    <span className="text-sm font-semibold text-white">Console & Access</span>
                  </div>

                  {/* Quick access buttons */}
                  <div className="grid grid-cols-3 gap-2 mb-4">
                    <button
                      onClick={() => setConsoleVM({ name: selected.name, ns: selected.namespace })}
                      className="flex flex-col items-center gap-1.5 p-3 tahoe-glass-card rounded-lg border border-white/[0.06] hover:border-cyan-500/30 hover:bg-cyan-500/5 transition-all text-white/55 hover:text-cyan-400">
                      <Monitor className="h-5 w-5" />
                      <span className="text-[10px] font-medium">VNC</span>
                    </button>
                    <button
                      onClick={() => { showToast('info', `Run: virtctl console ${selected.name} -n ${selected.namespace}`); navigator.clipboard.writeText(`virtctl console ${selected.name} -n ${selected.namespace}`); }}
                      className="flex flex-col items-center gap-1.5 p-3 tahoe-glass-card rounded-lg border border-white/[0.06] hover:border-green-500/30 hover:bg-green-500/5 transition-all text-white/55 hover:text-green-400">
                      <Terminal className="h-5 w-5" />
                      <span className="text-[10px] font-medium">Serial</span>
                    </button>
                    <button
                      onClick={() => {
                        const cmd = selected.ip ? `ssh ${sshUser}@${selected.ip}` : `virtctl ssh ${sshUser}@${selected.name} -n ${selected.namespace}`;
                        showToast('info', `Run: ${cmd}`); navigator.clipboard.writeText(cmd);
                      }}
                      className="flex flex-col items-center gap-1.5 p-3 tahoe-glass-card rounded-lg border border-white/[0.06] hover:border-blue-500/30 hover:bg-blue-500/5 transition-all text-white/55 hover:text-blue-400">
                      <ExternalLink className="h-5 w-5" />
                      <span className="text-[10px] font-medium">SSH</span>
                    </button>
                  </div>

                  {/* IP Address */}
                  {selected.ip ? (
                    <div className="flex items-center gap-2 p-3 bg-green-500/5 border border-green-500/20 rounded-lg mb-3">
                      <div className="w-2.5 h-2.5 rounded-full bg-green-400 shadow-green-400/50 shadow-sm" />
                      <span className="text-sm font-mono text-green-400 font-medium flex-1">{selected.ip}</span>
                      <button onClick={() => navigator.clipboard.writeText(selected.ip)} title="Copy IP"
                        className="h-7 w-7 rounded-lg hover:bg-green-500/10 text-green-400 flex items-center justify-center transition-colors">
                        <Copy className="h-3.5 w-3.5" />
                      </button>
                      <button onClick={() => navigator.clipboard.writeText(`ssh ${sshUser}@${selected.ip}`)} title="Copy SSH command"
                        className="h-7 w-7 rounded-lg hover:bg-green-500/10 text-green-400 flex items-center justify-center transition-colors">
                        <ExternalLink className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 p-3 tahoe-glass-card rounded-lg mb-3 text-xs text-white/45">
                      <Network className="h-3.5 w-3.5" />
                      {selected.running ? 'Waiting for IP...' : 'VM not running'}
                    </div>
                  )}

                  {/* SSH User */}
                  <div className="flex items-center gap-2 mb-2">
                    <label className="text-xs text-white/45">SSH User:</label>
                    <input
                      type="text"
                      value={sshUser}
                      onChange={(e) => setSshUser(e.target.value)}
                      placeholder="root"
                      className="px-2 py-1 tahoe-glass-card border border-white/[0.08] rounded text-xs text-white/75 w-28 focus:outline-none focus:border-blue-500/50"
                    />
                  </div>

                  {/* Command reference */}
                  <div className="space-y-1.5">
                    <CmdRow icon={Monitor} label="VNC" cmd={`virtctl vnc ${selected.name} -n ${selected.namespace}`} />
                    <CmdRow icon={Terminal} label="Console" cmd={`virtctl console ${selected.name} -n ${selected.namespace}`} />
                    <CmdRow icon={ExternalLink} label="SSH" cmd={selected.ip ? `ssh ${sshUser}@${selected.ip}` : `virtctl ssh ${sshUser}@${selected.name} -n ${selected.namespace}`} />
                    <CmdRow icon={Network} label="Forward" cmd={`virtctl port-forward vm/${selected.name} 8080:80 -n ${selected.namespace}`} />
                  </div>
                </div>

                {/* Delete */}
                <DeleteCard
                  name={selected.name}
                  onDelete={() => {
                    fetchAPI(`/kubevirt/vms/${selected.namespace}/${selected.name}`, { method: 'DELETE' })
                      .then(() => { queryClient.invalidateQueries({ queryKey: ['kubevirt-vms'] }); setSelectedVM(null); showToast('success', `Deleted ${selected.name}`); })
                      .catch((e: Error) => showToast('error', e.message));
                  }}
                />
              </>
            ) : (
              <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5 text-center py-16 text-sm text-white/45">
                Select a VM to view details
              </div>
            )}

            {action.error && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-3 text-xs text-red-400">
                <AlertCircle className="h-3.5 w-3.5 inline mr-1" />
                {(action.error as Error).message}
              </div>
            )}
          </div>
        </div>
      )}

      {/* KubeVirt VNC Console Modal */}
      {consoleVM && (
        <KVConsoleModal vmName={consoleVM.name} namespace={consoleVM.ns} onClose={() => setConsoleVM(null)} />
      )}
    </div>
  );
}

function ActionBtn({ icon: Icon, label, color, onClick }: { icon: React.ElementType; label: string; color: string; onClick: () => void }) {
  const colors: Record<string, string> = {
    green: 'bg-green-500/10 text-green-400 hover:bg-green-500/20',
    red: 'bg-red-500/10 text-red-400 hover:bg-red-500/20',
    blue: 'bg-blue-500/10 text-blue-400 hover:bg-blue-500/20',
    yellow: 'bg-yellow-500/10 text-yellow-400 hover:bg-yellow-500/20',
    purple: 'bg-purple-500/10 text-purple-400 hover:bg-purple-500/20',
  };
  return (
    <button onClick={onClick} className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs transition-colors ${colors[color]}`}>
      <Icon className="h-3 w-3" /> {label}
    </button>
  );
}

function CmdRow({ icon: Icon, label, cmd }: { icon: React.ElementType; label: string; cmd: string }) {
  return (
    <div className="flex items-center gap-2 p-2 tahoe-glass-card rounded-lg">
      <Icon className="h-3.5 w-3.5 text-cyan-400 flex-shrink-0" />
      <span className="text-xs text-white/55 w-24 flex-shrink-0">{label}</span>
      <code className="text-[10px] text-cyan-400 font-mono flex-1 truncate">{cmd}</code>
      <button onClick={() => navigator.clipboard.writeText(cmd)} title="Copy"
        className="h-5 w-5 rounded hover:bg-white/[0.04] text-white/45 hover:text-white flex items-center justify-center transition-colors flex-shrink-0">
        <Copy className="h-2.5 w-2.5 text-blue-400" />
      </button>
    </div>
  );
}

function DeleteCard({ name, onDelete }: { name: string; onDelete: () => void }) {
  const [confirm, setConfirm] = useState(false);
  return (
    <div className="tahoe-glass-card rounded-xl border border-red-500/20 p-4">
      {confirm ? (
        <div>
          <p className="text-xs text-red-400 mb-3">Delete VM "{name}" permanently?</p>
          <div className="flex gap-2">
            <button onClick={onDelete} className="flex items-center gap-1 px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white rounded-lg text-xs font-medium transition-colors">
              <Trash2 className="h-3 w-3" /> Confirm Delete
            </button>
            <button onClick={() => setConfirm(false)} className="px-3 py-1.5 border border-white/[0.12] text-white/75 rounded-lg text-xs hover:bg-white/[0.04] transition-colors">Cancel</button>
          </div>
        </div>
      ) : (
        <button onClick={() => setConfirm(true)} className="flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300 transition-colors">
          <Trash2 className="h-3.5 w-3.5" /> Delete VM
        </button>
      )}
    </div>
  );
}

function StatBox({ icon: Icon, label, value, color }: { icon: React.ElementType; label: string; value: string; color?: string }) {
  return (
    <div className="p-3 tahoe-glass-card rounded-lg">
      <div className="flex items-center gap-1.5 text-[10px] text-white/45 mb-0.5">
        <Icon className="h-3 w-3 text-sky-400" />{label}
      </div>
      <div className={`text-xs font-medium truncate ${color || 'text-white/75'}`}>{value}</div>
    </div>
  );
}
