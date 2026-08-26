// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useCallback, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowRightLeft, CheckCircle, XCircle, Clock, Server, HardDrive,
  Cpu, Activity, Loader2, AlertCircle, Network, Play, BarChart3,
  Monitor, MemoryStick, Database, Gauge, Box, Shield, Terminal, Cloud, Container, Download,
  TrendingUp, Upload,
} from 'lucide-react';
import { useJobStats, useJobs } from '../hooks/useJobs';
import { useProviders } from '../hooks/useProviders';
import { useWebSocketSubscription, type WSMessage } from '../contexts/WebSocketContext';
import { useAppStore } from '../stores/app';
import { getHostInfo } from '../api/host';
import { fetchAPI } from '../api/client';
import type { Job } from '../types/job';
import { OnboardingChecklist } from '../components/OnboardingChecklist';
import { TahoeHero } from '../components/ui/TahoeHero';

interface ReadinessCheck {
  name: string;
  status: 'ok' | 'warning' | 'error';
  detail: string;
}

interface DiskImageDir {
  path: string;
  files: { name: string; path: string; size_human: string; format: string }[];
}

interface DiskImagesResponse {
  directories: DiskImageDir[];
}

interface CapacityData {
  host: {
    cpus: number;
    memory_total_gb: number;
    memory_used_gb: number;
    storage_total_gb: number;
    storage_used_gb: number;
  };
  vms: {
    total: number;
    running: number;
    vcpus_allocated: number;
    memory_allocated_gb: number;
  };
  utilization: {
    cpu_percent: number;
    memory_percent: number;
    storage_percent: number;
  };
}

interface ActivityEntry {
  timestamp: string;
  user: string;
  action: string;
  target: string;
  result: string;
  remote_ip: string;
}

interface ActivityResponse {
  activities: ActivityEntry[];
  total: number;
}

interface TopVMCPU {
  name: string;
  cpu_time_ns: number;
  cpu_percent: number;
}

interface TopVMMem {
  name: string;
  memory_mb: number;
  memory_percent: number;
}

interface TopVMsData {
  by_cpu: TopVMCPU[];
  by_memory: TopVMMem[];
}

export function DashboardPage() {
  const navigate = useNavigate();
  const { data: stats } = useJobStats();
  const { data: providers } = useProviders();
  const { data: jobs } = useJobs();
  const { data: hostInfo } = useQuery({
    queryKey: ['host-info'],
    queryFn: getHostInfo,
    refetchInterval: 10000,
  });
  const { data: readiness } = useQuery({
    queryKey: ['readiness'],
    queryFn: () => fetchAPI<ReadinessCheck[]>('/readiness'),
    refetchInterval: 30000,
  });
  const { data: diskImages } = useQuery({
    queryKey: ['disk-images'],
    queryFn: () => fetchAPI<DiskImagesResponse>('/disk-images'),
    refetchInterval: 60000,
  });
  const { data: capacity } = useQuery({
    queryKey: ['capacity'],
    queryFn: () => fetchAPI<CapacityData>('/capacity'),
    refetchInterval: 15000,
  });
  const { data: activityData } = useQuery({
    queryKey: ['activity-feed'],
    queryFn: () => fetchAPI<ActivityResponse>('/activity'),
    refetchInterval: 15000,
  });
  const { data: topVMs } = useQuery({
    queryKey: ['top-vms'],
    queryFn: () => fetchAPI<TopVMsData>('/vms/top'),
    refetchInterval: 15000,
  });
  const { setWsConnected } = useAppStore();
  const [recentEvents, setRecentEvents] = useState<{ type: string; message: string; time: string }[]>([]);
  const [lastUpdated, setLastUpdated] = useState<string>('');

  // Update timestamp whenever key data refreshes
  useEffect(() => {
    if (capacity || hostInfo || stats) {
      setLastUpdated(new Date().toLocaleTimeString());
    }
  }, [capacity, hostInfo, stats]);

  const onMessage = useCallback((msg: WSMessage) => {
    setWsConnected(true);
    if (['job_created', 'job_started', 'job_completed', 'job_failed', 'job_cancelled'].includes(msg.type)) {
      const jobId = (msg.data.job_id as string) || '';
      const eventMessages: Record<string, string> = {
        job_created: `Migration ${jobId} queued`,
        job_started: `Migration ${jobId} started`,
        job_completed: `Migration ${jobId} completed successfully`,
        job_failed: `Migration ${jobId} failed`,
        job_cancelled: `Migration ${jobId} cancelled`,
      };
      setRecentEvents((prev) => [
        { type: msg.type, message: eventMessages[msg.type] || msg.type, time: new Date().toLocaleTimeString() },
        ...prev.slice(0, 19),
      ]);
    }
  }, [setWsConnected]);

  useWebSocketSubscription(onMessage);

  const running = jobs?.filter((j) => j.status === 'running') || [];
  const completed = jobs?.filter((j) => j.status === 'completed') || [];
  const connectedProviders = providers?.filter((p) => p.connected) || [];
  const totalMigrations = stats?.total ?? 0;
  const successRate = totalMigrations > 0 ? Math.round(((stats?.completed ?? 0) / totalMigrations) * 100) : 0;

  return (
    <div className="space-y-6">
      <TahoeHero
        icon={<BarChart3 className="w-5 h-5 text-blue-300" />}
        title="Dashboard"
        subtitle={`${hostInfo?.hostname ? `${hostInfo.hostname} · ` : ''}VM Migration Overview`}
        actions={
          <div className="flex items-center gap-2 px-3 py-1.5 tahoe-glass-card rounded-lg border border-white/[0.08]">
            <Activity className="h-3.5 w-3.5 text-green-400 animate-pulse-dot" />
            <span className="text-xs text-white/55">Live</span>
            {hostInfo ? <span className="text-xs text-white/45 hidden lg:inline">· up {hostInfo.uptime_human}</span> : null}
          </div>
        }
      />

      <OnboardingChecklist
        onConnectProvider={() => navigate('/providers')}
        onStartMigration={() => navigate('/migrate')}
        onViewJobs={() => navigate('/jobs')}
      />

      <div className="rounded-xl border border-blue-500/25 bg-gradient-to-r from-blue-500/10 to-blue-950/40 p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <ArrowRightLeft className="w-4 h-4 text-blue-400" />
            Start a migration
          </h3>
          <p className="text-xs text-white/55 mt-1">
            Export → Convert → Fix guest OS → Deploy via h2kvmctl (virsh define, not virt-install).
          </p>
        </div>
        <div className="flex flex-wrap gap-2 shrink-0">
          <button type="button" onClick={() => navigate('/migrate')} className="px-4 py-2 rounded-lg text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white">
            Migrate hub
          </button>
          <button type="button" onClick={() => navigate('/providers')} className="px-4 py-2 rounded-lg text-xs font-medium border border-white/[0.12] text-white/75 hover:bg-white/[0.04]">
            Connect provider
          </button>
          <button type="button" onClick={() => navigate('/jobs')} className="px-4 py-2 rounded-lg text-xs font-medium border border-white/[0.12] text-white/75 hover:bg-white/[0.04]">
            View jobs
          </button>
        </div>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={ArrowRightLeft} label="Total Migrations" value={totalMigrations}
          badge={running.length > 0 ? `${running.length} active` : undefined} badgeColor="blue" gradient="stat-card-blue" iconColor="text-blue-400" />
        <StatCard icon={CheckCircle} label="Completed" value={stats?.completed ?? 0}
          badge={successRate > 0 ? `${successRate}% success` : undefined} badgeColor="green" gradient="stat-card-green" iconColor="text-green-400" />
        <StatCard icon={XCircle} label="Failed" value={stats?.failed ?? 0}
          badgeColor="red" gradient="stat-card-red" iconColor="text-red-400" />
        <StatCard icon={Server} label="Providers" value={connectedProviders.length}
          badge={`${providers?.length ?? 0} configured`} badgeColor="purple" gradient="stat-card-purple" iconColor="text-purple-400" />
      </div>

      {/* Cluster Capacity */}
      {capacity && (
        <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
          <div className="flex items-center gap-2 mb-5">
            <Gauge className="h-4 w-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-white">Cluster Capacity</h3>
            <span className="text-[10px] text-white/45 ml-auto">auto-refresh 15s</span>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Gauges */}
            <div className="flex items-center justify-around">
              <CapacityGauge
                percent={capacity.utilization.cpu_percent}
                label="CPU"
                detail={`${capacity.vms.vcpus_allocated} / ${capacity.host.cpus} cores`}
              />
              <CapacityGauge
                percent={capacity.utilization.memory_percent}
                label="Memory"
                detail={`${capacity.host.memory_used_gb} / ${capacity.host.memory_total_gb} GB`}
              />
              <CapacityGauge
                percent={capacity.utilization.storage_percent}
                label="Storage"
                detail={`${capacity.host.storage_used_gb} / ${capacity.host.storage_total_gb} GB`}
              />
            </div>
            {/* Host Info */}
            <div className="space-y-2">
              <div className="text-xs text-white/45 font-medium mb-1">Host Resources</div>
              <div className="flex items-center justify-between p-2 tahoe-glass-card rounded-lg">
                <div className="flex items-center gap-1.5 text-xs text-white/55"><Cpu className="h-3 w-3 text-blue-400" /> Total CPUs</div>
                <span className="text-xs text-white/75 font-medium">{capacity.host.cpus}</span>
              </div>
              <div className="flex items-center justify-between p-2 tahoe-glass-card rounded-lg">
                <div className="flex items-center gap-1.5 text-xs text-white/55"><MemoryStick className="h-3 w-3 text-green-400" /> Memory</div>
                <span className="text-xs text-white/75 font-medium">{capacity.host.memory_total_gb} GB</span>
              </div>
              <div className="flex items-center justify-between p-2 tahoe-glass-card rounded-lg">
                <div className="flex items-center gap-1.5 text-xs text-white/55"><HardDrive className="h-3 w-3 text-yellow-400" /> Storage</div>
                <span className="text-xs text-white/75 font-medium">{capacity.host.storage_total_gb} GB</span>
              </div>
            </div>
            {/* VM Density */}
            <div className="space-y-2">
              <div className="text-xs text-white/45 font-medium mb-1">VM Density</div>
              <div className="flex items-center justify-between p-2 tahoe-glass-card rounded-lg">
                <div className="flex items-center gap-1.5 text-xs text-white/55"><Box className="h-3 w-3 text-cyan-400" /> VMs</div>
                <span className="text-xs text-white/75 font-medium">{capacity.vms.running} / {capacity.vms.total}</span>
              </div>
              <div className="flex items-center justify-between p-2 tahoe-glass-card rounded-lg">
                <div className="flex items-center gap-1.5 text-xs text-white/55"><Cpu className="h-3 w-3 text-blue-400" /> Allocated vCPUs</div>
                <span className="text-xs text-white/75 font-medium">{capacity.vms.vcpus_allocated}</span>
              </div>
              <div className="flex items-center justify-between p-2 tahoe-glass-card rounded-lg">
                <div className="flex items-center gap-1.5 text-xs text-white/55"><MemoryStick className="h-3 w-3 text-green-400" /> Allocated Memory</div>
                <span className="text-xs text-white/75 font-medium">{capacity.vms.memory_allocated_gb} GB</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Last Updated */}
      {lastUpdated && (
        <div className="flex justify-end">
          <span className="text-[10px] text-white/45">Last updated: {lastUpdated}</span>
        </div>
      )}

      {/* Recent Activity Feed */}
      {activityData && activityData.activities && activityData.activities.length > 0 && (
        <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
          <div className="flex items-center gap-2 mb-4">
            <Activity className="h-4 w-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-white">Recent Activity</h3>
            <span className="text-[10px] text-white/45 ml-auto">auto-refresh 15s</span>
          </div>
          <div className="space-y-1.5 max-h-72 overflow-auto">
            {activityData.activities.map((entry, i) => {
              const cfg = getActivityStyle(entry.action);
              return (
                <div key={i} className="flex items-center gap-3 p-2 rounded-lg table-row-hover">
                  <div className={`w-2 h-2 rounded-full flex-shrink-0 ${cfg.dot}`} />
                  <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${cfg.badge} w-24 text-center truncate`}>{entry.action}</span>
                  <span className="text-xs text-white/75 font-mono truncate flex-1 min-w-0">{entry.target}</span>
                  <span className="text-[10px] text-white/45 flex-shrink-0">{formatRelativeTime(entry.timestamp)}</span>
                  <span className="text-[10px] text-white/40 flex-shrink-0 hidden sm:inline">{entry.user}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Top Consumers */}
      {topVMs && ((topVMs.by_cpu && topVMs.by_cpu.length > 0) || (topVMs.by_memory && topVMs.by_memory.length > 0)) && (
        <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="h-4 w-4 text-orange-400" />
            <h3 className="text-sm font-semibold text-white">Top Consumers</h3>
            <span className="text-[10px] text-white/45 ml-auto">auto-refresh 15s</span>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Top CPU */}
            <div>
              <div className="flex items-center gap-1.5 mb-3">
                <Cpu className="h-3.5 w-3.5 text-blue-400" />
                <span className="text-xs font-medium text-white/75">Top 5 by CPU</span>
              </div>
              <div className="space-y-2">
                {(topVMs.by_cpu || []).map((vm, i) => {
                  const pct = Math.min(100, Math.round(vm.cpu_percent));
                  const barColor = pct > 80 ? 'bg-red-500' : pct > 50 ? 'bg-yellow-500' : 'bg-blue-500';
                  return (
                    <div key={vm.name} className="space-y-1">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5">
                          <span className="text-[10px] text-white/45 w-3">{i + 1}</span>
                          <span className="text-xs text-white/75 font-mono truncate max-w-[140px]">{vm.name}</span>
                        </div>
                        <span className={`text-xs font-medium ${pct > 80 ? 'text-red-400' : pct > 50 ? 'text-yellow-400' : 'text-blue-400'}`}>
                          {vm.cpu_percent.toFixed(1)}%
                        </span>
                      </div>
                      <div className="h-1.5 bg-white/[0.08] rounded-full overflow-hidden">
                        <div className={`h-full ${barColor} rounded-full transition-all duration-500`} style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  );
                })}
                {(!topVMs.by_cpu || topVMs.by_cpu.length === 0) && (
                  <div className="text-xs text-white/45 text-center py-2">No running VMs</div>
                )}
              </div>
            </div>
            {/* Top Memory */}
            <div>
              <div className="flex items-center gap-1.5 mb-3">
                <MemoryStick className="h-3.5 w-3.5 text-green-400" />
                <span className="text-xs font-medium text-white/75">Top 5 by Memory</span>
              </div>
              <div className="space-y-2">
                {(topVMs.by_memory || []).map((vm, i) => {
                  const pct = Math.min(100, Math.round(vm.memory_percent));
                  const barColor = pct > 80 ? 'bg-red-500' : pct > 50 ? 'bg-yellow-500' : 'bg-green-500';
                  return (
                    <div key={vm.name} className="space-y-1">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5">
                          <span className="text-[10px] text-white/45 w-3">{i + 1}</span>
                          <span className="text-xs text-white/75 font-mono truncate max-w-[140px]">{vm.name}</span>
                        </div>
                        <span className={`text-xs font-medium ${pct > 80 ? 'text-red-400' : pct > 50 ? 'text-yellow-400' : 'text-green-400'}`}>
                          {vm.memory_mb} MB ({vm.memory_percent.toFixed(1)}%)
                        </span>
                      </div>
                      <div className="h-1.5 bg-white/[0.08] rounded-full overflow-hidden">
                        <div className={`h-full ${barColor} rounded-full transition-all duration-500`} style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  );
                })}
                {(!topVMs.by_memory || topVMs.by_memory.length === 0) && (
                  <div className="text-xs text-white/45 text-center py-2">No running VMs</div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Host Resources */}
      {hostInfo && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <ResourceCard icon={Cpu} label="CPU" color="blue"
            value={`${hostInfo.cpu_cores} cores`}
            subValue={`Load: ${hostInfo.load_1m} / ${hostInfo.load_5m} / ${hostInfo.load_15m}`}
            percent={Math.min(100, Math.round((parseFloat(hostInfo.load_1m) / hostInfo.cpu_cores) * 100))}
          />
          <ResourceCard icon={MemoryStick} label="Memory" color="green"
            value={`${formatMB(hostInfo.mem_used_mb)} / ${formatMB(hostInfo.mem_total_mb)}`}
            subValue={`${formatMB(hostInfo.mem_available_mb)} available`}
            percent={hostInfo.mem_percent}
          />
          <ResourceCard icon={HardDrive} label="Root Disk (/)" color="yellow"
            value={`${hostInfo.disk_used} / ${hostInfo.disk_total}`}
            subValue={`${hostInfo.disk_avail} free`}
            percent={parseInt(hostInfo.disk_percent) || 0}
          />
          <ResourceCard icon={Box} label="Libvirt VMs" color="cyan"
            value={`${hostInfo.libvirt_running} running`}
            subValue={`${hostInfo.libvirt_vm_count} total defined`}
            percent={hostInfo.libvirt_vm_count > 0 ? Math.round((hostInfo.libvirt_running / hostInfo.libvirt_vm_count) * 100) : 0}
          />
        </div>
      )}

      {/* Main content grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Pipeline + Recent Migrations */}
        <div className="lg:col-span-2 space-y-6">
          {/* Migration Pipeline */}
          <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <BarChart3 className="h-4 w-4 text-blue-400" />
                <h3 className="text-sm font-semibold text-white">Migration Pipeline</h3>
              </div>
              <span className="text-xs text-white/45">{jobs?.length ?? 0} total</span>
            </div>
            <div className="grid grid-cols-3 sm:grid-cols-5 gap-2 sm:gap-3 mb-5">
              <PipelineStage label="Export" count={stats?.pending ?? 0} color="yellow" icon={Upload} />
              <PipelineStage label="Convert" count={running.length} color="blue" icon={Loader2} spinning />
              <PipelineStage label="Fix OS" count={0} color="cyan" icon={Cpu} />
              <PipelineStage label="Deploy" count={0} color="purple" icon={Play} />
              <PipelineStage label="Done" count={stats?.completed ?? 0} color="green" icon={CheckCircle} />
            </div>

            <div className="text-xs text-white/45 mb-2">Recent Migrations</div>
            <div className="space-y-1">
              {(jobs || []).slice(0, 5).map((job) => (
                <MigrationRow key={job.id} job={job} />
              ))}
              {(!jobs || jobs.length === 0) && (
                <div className="text-center py-6 text-sm text-white/40">No migrations yet</div>
              )}
            </div>
          </div>

          {/* System Info */}
          {hostInfo && (
            <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
              <div className="flex items-center gap-2 mb-4">
                <Monitor className="h-4 w-4 text-blue-400" />
                <h3 className="text-sm font-semibold text-white">System Information</h3>
              </div>
              <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
                <InfoItem icon={Monitor} label="Hostname" value={hostInfo.hostname} />
                <InfoItem icon={Terminal} label="OS" value={hostInfo.os_name} />
                <InfoItem icon={Terminal} label="Kernel" value={hostInfo.kernel} />
                <InfoItem icon={Cpu} label="CPU" value={hostInfo.cpu_model} />
                <InfoItem icon={MemoryStick} label="RAM" value={formatMB(hostInfo.mem_total_mb)} />
                <InfoItem icon={Shield} label="KVM" value={hostInfo.kvm_available ? 'Enabled' : 'Disabled'} good={hostInfo.kvm_available} />
                <InfoItem icon={Box} label="QEMU" value={hostInfo.qemu_version?.replace('QEMU emulator version ', '') || 'N/A'} />
                <InfoItem icon={Database} label="Swap" value={`${formatMB(hostInfo.swap_used_mb)} / ${formatMB(hostInfo.swap_total_mb)}`} />
                <InfoItem icon={Clock} label="Uptime" value={hostInfo.uptime_human} />
              </div>

              {/* Disk Partitions */}
              {hostInfo.disks && hostInfo.disks.length > 0 && (
                <div className="mt-4 pt-4 border-t border-white/[0.06]">
                  <div className="flex items-center gap-2 mb-3">
                    <HardDrive className="h-3.5 w-3.5 text-yellow-400" />
                    <span className="text-xs font-semibold text-white/75">Storage ({hostInfo.disks.length} partitions)</span>
                  </div>
                  <div className="space-y-2">
                    {hostInfo.disks.map((disk) => {
                      const pct = parseInt(disk.percent) || 0;
                      return (
                        <div key={disk.mountpoint} className="p-2.5 tahoe-glass-card rounded-lg">
                          <div className="flex items-center justify-between text-xs mb-1">
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="font-mono text-white/75 truncate">{disk.name}</span>
                              <span className="text-white/45 truncate hidden sm:inline">{disk.mountpoint}</span>
                              <span className="text-[10px] text-white/40 hidden sm:inline">{disk.fstype}</span>
                            </div>
                            <span className={`font-medium ${pct > 90 ? 'text-red-400' : pct > 75 ? 'text-yellow-400' : 'text-white/75'}`}>{disk.percent}%</span>
                          </div>
                          <div className="h-1.5 bg-white/[0.08] rounded-full overflow-hidden mb-1">
                            <div className={`h-full rounded-full ${pct > 90 ? 'bg-red-500' : pct > 75 ? 'bg-yellow-500' : 'bg-blue-500'}`} style={{ width: `${pct}%` }} />
                          </div>
                          <div className="flex justify-between text-[10px] text-white/45">
                            <span>{disk.used} used</span>
                            <span>{disk.avail} free</span>
                            <span>{disk.size} total</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Libvirt VMs list */}
              {hostInfo.libvirt_vms && hostInfo.libvirt_vms.length > 0 && (
                <div className="mt-4 pt-4 border-t border-white/[0.06]">
                  <div className="text-xs text-white/45 mb-2">Libvirt Domains ({hostInfo.libvirt_vm_count})</div>
                  <div className="flex flex-wrap gap-2">
                    {hostInfo.libvirt_vms.map((vm) => (
                      <span key={vm} className="text-xs px-2.5 py-1 tahoe-glass-card border border-white/[0.06] rounded-lg text-white/75 font-mono">
                        {vm}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* K8s Cluster Info */}
              {hostInfo.k8s_available && (
                <div className="mt-4 pt-4 border-t border-white/[0.06]">
                  <div className="flex items-center gap-2 mb-3">
                    <Cloud className="h-4 w-4 text-blue-400" />
                    <span className="text-xs font-semibold text-white/75">
                      {hostInfo.k3s ? 'K3s' : 'Kubernetes'} Cluster
                    </span>
                    {hostInfo.kubevirt_available && (
                      <span className="text-[10px] px-1.5 py-0.5 bg-purple-500/10 text-purple-400 border border-purple-500/30 rounded-full">KubeVirt</span>
                    )}
                  </div>
                  <div className="grid grid-cols-2 lg:grid-cols-3 gap-2">
                    {hostInfo.k8s_version && (
                      <div className="p-2 tahoe-glass-card rounded-lg">
                        <div className="text-[10px] text-white/45">Version</div>
                        <div className="text-xs text-white/75 font-mono truncate">{hostInfo.k8s_version.replace(/Client Version: |Server Version: /g, '').split('\n')[0]}</div>
                      </div>
                    )}
                    <div className="p-2 tahoe-glass-card rounded-lg">
                      <div className="text-[10px] text-white/45">Nodes</div>
                      <div className="text-xs text-white/75 font-medium">{hostInfo.k8s_node_count ?? 0}</div>
                    </div>
                    <div className="p-2 tahoe-glass-card rounded-lg">
                      <div className="text-[10px] text-white/45">Pods</div>
                      <div className="text-xs text-white/75 font-medium">{hostInfo.k8s_pod_count ?? 0}</div>
                    </div>
                    {hostInfo.kubevirt_available && (
                      <div className="p-2 tahoe-glass-card rounded-lg">
                        <div className="text-[10px] text-white/45">KubeVirt VMIs</div>
                        <div className="text-xs text-purple-400 font-medium">{hostInfo.kubevirt_vmi_count ?? 0}</div>
                      </div>
                    )}
                  </div>
                  {hostInfo.k8s_nodes && hostInfo.k8s_nodes.length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-2">
                      {hostInfo.k8s_nodes.map((node) => (
                        <span key={node.name} className={`text-xs px-2.5 py-1 border rounded-lg font-mono ${
                          node.status === 'Ready'
                            ? 'bg-green-500/5 border-green-500/30 text-green-400'
                            : 'bg-red-500/5 border-red-500/30 text-red-400'
                        }`}>
                          <Container className="h-3 w-3 inline mr-1" />{node.name} ({node.status})
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Disk Images */}
          {diskImages && diskImages.directories && diskImages.directories.length > 0 && (
            <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
              <div className="flex items-center gap-2 mb-4">
                <HardDrive className="h-4 w-4 text-yellow-400" />
                <h3 className="text-sm font-semibold text-white">Disk Images</h3>
                <span className="text-xs text-white/45 ml-auto">
                  {diskImages.directories.reduce((acc, d) => acc + d.files.length, 0)} files
                </span>
              </div>
              <div className="max-h-[300px] overflow-auto space-y-4">
                {diskImages.directories.map((dir) => (
                  <div key={dir.path}>
                    <div className="text-[10px] font-mono text-white/45 mb-1.5">{dir.path}</div>
                    <div className="space-y-1">
                      {dir.files.map((file) => (
                        <div key={file.path} className="flex items-center gap-3 p-2 tahoe-glass-card rounded-lg text-xs">
                          <HardDrive className="h-3 w-3 text-yellow-400 flex-shrink-0" />
                          <span className="flex-1 min-w-0 text-white/75 font-mono truncate">{file.name}</span>
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                            file.format === 'qcow2' ? 'bg-blue-500/10 text-blue-400' :
                            file.format === 'vmdk' ? 'bg-purple-500/10 text-purple-400' :
                            file.format === 'raw' ? 'bg-green-500/10 text-green-400' :
                            'bg-white/[0.06] text-white/55'
                          }`}>{file.format}</span>
                          <span className="text-white/45 text-[10px] w-16 text-right">{file.size_human}</span>
                          <button
                            onClick={() => window.open(`/api/v1/download?path=${encodeURIComponent(file.path)}`, '_blank')}
                            className="h-6 w-6 rounded hover:bg-blue-500/10 text-green-400 hover:text-green-300 flex items-center justify-center transition-colors flex-shrink-0"
                            title={`Download ${file.name}`}
                          >
                            <Download className="h-3 w-3" />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right sidebar */}
        <div className="space-y-6">
          {/* Providers */}
          <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
            <div className="flex items-center gap-2 mb-4">
              <Network className="h-4 w-4 text-cyan-400" />
              <h3 className="text-sm font-semibold text-white">Providers</h3>
            </div>
            {connectedProviders.length > 0 ? (
              <div className="space-y-2">
                {connectedProviders.map((p) => (
                  <div key={p.id} className="flex items-center gap-3 p-2.5 tahoe-glass-card rounded-lg border border-white/[0.06]">
                    <div className="w-2 h-2 rounded-full bg-green-400 shadow-green-400/50 shadow-sm" />
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium text-white truncate">{p.name}</div>
                      <div className="text-[10px] text-white/45">{p.type.toUpperCase()}</div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-4">
                <Server className="h-8 w-8 text-blue-400/30 mx-auto mb-2" />
                <div className="text-xs text-white/45">No providers connected</div>
              </div>
            )}
            <div className="mt-4 pt-4 border-t border-white/[0.06]">
              <ResourceBar label="Completed" used={completed.length} total={Math.max(totalMigrations, 1)} color="green" />
            </div>
          </div>

          {/* Migration Readiness */}
          {readiness && readiness.length > 0 && (
            <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
              <div className="flex items-center gap-2 mb-4">
                <Shield className="h-4 w-4 text-purple-400" />
                <h3 className="text-sm font-semibold text-white">Migration Readiness</h3>
              </div>
              <div className="space-y-2">
                {readiness.map((check) => (
                  <div key={check.name} className="flex items-center justify-between py-1.5">
                    <div className="flex items-center gap-2 min-w-0">
                      <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                        check.status === 'ok' ? 'bg-green-400' :
                        check.status === 'warning' ? 'bg-yellow-400' : 'bg-red-400'
                      }`} />
                      <span className="text-xs text-white/75">{check.name}</span>
                    </div>
                    <span className="text-[10px] text-white/45 truncate ml-2">{check.detail}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recent Activity */}
          <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
            <div className="flex items-center gap-2 mb-4">
              <Activity className="h-4 w-4 text-green-400" />
              <h3 className="text-sm font-semibold text-white">Recent Activity</h3>
            </div>
            {recentEvents.length > 0 ? (
              <div className="space-y-2.5 max-h-60 overflow-auto">
                {recentEvents.map((event, i) => (
                  <div key={i} className="flex items-start gap-2.5">
                    <div className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${
                      event.type === 'job_completed' ? 'bg-green-400' :
                      event.type === 'job_failed' ? 'bg-red-400' :
                      event.type === 'job_started' ? 'bg-blue-400' : 'bg-white/30'
                    }`} />
                    <div className="min-w-0">
                      <div className="text-xs text-white/75 truncate">{event.message}</div>
                      <div className="text-[10px] text-white/40">{event.time}</div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-4 text-xs text-white/40">
                Events appear as migrations run
              </div>
            )}
          </div>

          {/* Quick health checks */}
          {hostInfo && (
            <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
              <div className="flex items-center gap-2 mb-4">
                <Gauge className="h-4 w-4 text-yellow-400" />
                <h3 className="text-sm font-semibold text-white">Health</h3>
              </div>
              <div className="space-y-2">
                <HealthCheck label="KVM" ok={!!hostInfo.kvm_available} />
                <HealthCheck label="Libvirt" ok={(hostInfo.libvirt_vm_count ?? -1) >= 0} />
                <HealthCheck label="QEMU" ok={!!hostInfo.qemu_version} />
                <HealthCheck label="K8s" ok={!!hostInfo.k8s_available} detail={hostInfo.k3s ? 'K3s' : hostInfo.k8s_available ? 'K8s' : 'N/A'} />
                {hostInfo.kubevirt_available && <HealthCheck label="KubeVirt" ok={true} detail={`${hostInfo.kubevirt_vmi_count ?? 0} VMIs`} />}
                <HealthCheck label="Memory" ok={(hostInfo.mem_percent ?? 0) < 90} warn={(hostInfo.mem_percent ?? 0) > 75} detail={`${hostInfo.mem_percent ?? 0}%`} />
                <HealthCheck label="Disk" ok={(parseInt(hostInfo.disk_percent || '0')) < 90} warn={(parseInt(hostInfo.disk_percent || '0')) > 75} detail={`${hostInfo.disk_percent ?? '0'}%`} />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// --- Components ---

function CapacityGauge({ percent, label, detail }: { percent: number; label: string; detail: string }) {
  const color = percent > 85 ? 'text-red-400' : percent > 60 ? 'text-yellow-400' : 'text-green-400';
  const stroke = percent > 85 ? 'stroke-red-500' : percent > 60 ? 'stroke-yellow-500' : 'stroke-green-500';
  const r = 36, c = 2 * Math.PI * r;
  return (
    <div className="flex flex-col items-center">
      <svg width="88" height="88" className="-rotate-90">
        <circle cx="44" cy="44" r={r} fill="none" stroke="currentColor" strokeWidth="6" className="text-white/20" />
        <circle cx="44" cy="44" r={r} fill="none" strokeWidth="6" strokeDasharray={c} strokeDashoffset={c - (percent/100)*c} strokeLinecap="round" className={stroke} />
      </svg>
      <span className={`text-lg font-bold mt-1 ${color}`}>{percent.toFixed(0)}%</span>
      <span className="text-xs text-white/55">{label}</span>
      <span className="text-[10px] text-white/45">{detail}</span>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, badge, badgeColor, gradient, iconColor }: {
  icon: React.ElementType; label: string; value: number; badge?: string; badgeColor?: string; gradient: string; iconColor: string;
}) {
  const bc: Record<string, string> = {
    blue: 'bg-blue-500/10 text-blue-400', green: 'bg-green-500/10 text-green-400',
    red: 'bg-red-500/10 text-red-400', purple: 'bg-purple-500/10 text-purple-400',
  };
  return (
    <div className={`${gradient} rounded-xl border border-white/[0.08] p-5 card-glow transition-all hover:scale-[1.02]`}>
      <div className="flex items-center justify-between mb-3">
        <div className="w-10 h-10 rounded-lg tahoe-glass-card flex items-center justify-center">
          <Icon className={`h-5 w-5 ${iconColor}`} />
        </div>
        {badge && <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${bc[badgeColor || 'blue']}`}>{badge}</span>}
      </div>
      <div className="text-2xl font-bold text-white">{value}</div>
      <div className="text-xs text-white/55 mt-1">{label}</div>
    </div>
  );
}

function ResourceCard({ icon: Icon, label, value, subValue, percent, color }: {
  icon: React.ElementType; label: string; value: string; subValue: string; percent: number; color: string;
}) {
  const barColors: Record<string, string> = { blue: 'bg-blue-500', green: 'bg-green-500', yellow: 'bg-yellow-500', cyan: 'bg-cyan-500' };
  const textColors: Record<string, string> = { blue: 'text-blue-400', green: 'text-green-400', yellow: 'text-yellow-400', cyan: 'text-cyan-400' };
  const pctColor = percent > 90 ? 'text-red-400' : percent > 75 ? 'text-yellow-400' : textColors[color];

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4 card-glow transition-all hover:scale-[1.01]">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Icon className={`h-4 w-4 ${textColors[color]}`} />
          <span className="text-xs font-medium text-white/75">{label}</span>
        </div>
        <span className={`text-sm font-bold ${pctColor}`}>{percent}%</span>
      </div>
      <div className="h-1.5 bg-white/[0.08] rounded-full overflow-hidden mb-2">
        <div className={`h-full ${percent > 90 ? 'bg-red-500' : percent > 75 ? 'bg-yellow-500' : barColors[color]} rounded-full transition-all`} style={{ width: `${percent}%` }} />
      </div>
      <div className="text-xs text-white/75">{value}</div>
      <div className="text-[10px] text-white/45">{subValue}</div>
    </div>
  );
}

function PipelineStage({ label, count, color, icon: Icon, spinning }: {
  label: string; count: number; color: string; icon: React.ElementType; spinning?: boolean;
}) {
  const c: Record<string, { bg: string; text: string; ring: string }> = {
    yellow: { bg: 'bg-yellow-500/10', text: 'text-yellow-400', ring: 'ring-yellow-500/30' },
    blue: { bg: 'bg-blue-500/10', text: 'text-blue-400', ring: 'ring-blue-500/30' },
    cyan: { bg: 'bg-cyan-500/10', text: 'text-cyan-400', ring: 'ring-cyan-500/30' },
    purple: { bg: 'bg-purple-500/10', text: 'text-purple-400', ring: 'ring-purple-500/30' },
    green: { bg: 'bg-green-500/10', text: 'text-green-400', ring: 'ring-green-500/30' },
  };
  const s = c[color] || c.blue;
  return (
    <div className={`text-center p-3 rounded-lg ${s.bg} ring-1 ${s.ring}`}>
      <Icon className={`h-4 w-4 mx-auto mb-1 ${s.text} ${spinning && count > 0 ? 'animate-spin' : ''}`} />
      <div className={`text-lg font-bold ${s.text}`}>{count}</div>
      <div className="text-[10px] text-white/45">{label}</div>
    </div>
  );
}

function MigrationRow({ job }: { job: Job }) {
  const cfg: Record<string, { icon: React.ElementType; color: string; bg: string }> = {
    pending: { icon: Clock, color: 'text-yellow-400', bg: 'bg-yellow-500/10' },
    running: { icon: Loader2, color: 'text-blue-400', bg: 'bg-blue-500/10' },
    completed: { icon: CheckCircle, color: 'text-green-400', bg: 'bg-green-500/10' },
    failed: { icon: AlertCircle, color: 'text-red-400', bg: 'bg-red-500/10' },
    cancelled: { icon: XCircle, color: 'text-red-400', bg: 'bg-red-500/10' },
  };
  const c = cfg[job.status] || cfg.pending;
  const Icon = c.icon;
  const pct = job.progress?.percent_complete ?? 0;
  return (
    <div className="flex items-center gap-3 p-2.5 rounded-lg table-row-hover">
      <span className={`inline-flex items-center justify-center w-7 h-7 rounded-lg ${c.bg}`}>
        <Icon className={`h-3.5 w-3.5 ${c.color} ${job.status === 'running' ? 'animate-spin' : ''}`} />
      </span>
      <div className="flex-1 min-w-0">
        <div className="text-xs font-medium text-white truncate">{job.config.vm_name || job.config.command}</div>
        <div className="text-[10px] text-white/45">{job.id} &middot; {new Date(job.created_at).toLocaleString()}</div>
      </div>
      {job.status === 'running' && pct > 0 && (
        <div className="w-16">
          <div className="h-1.5 bg-white/[0.08] rounded-full overflow-hidden">
            <div className="h-full bg-blue-500 rounded-full" style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}
      <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${c.bg} ${c.color}`}>{job.status}</span>
    </div>
  );
}

function InfoItem({ icon: Icon, label, value, good }: { icon: React.ElementType; label: string; value: string; good?: boolean }) {
  return (
    <div className="flex items-start gap-2.5 p-2.5 tahoe-glass-card rounded-lg">
      <Icon className="h-3.5 w-3.5 text-blue-400 mt-0.5 flex-shrink-0" />
      <div className="min-w-0">
        <div className="text-[10px] text-white/45">{label}</div>
        <div className={`text-xs font-medium truncate ${good !== undefined ? (good ? 'text-green-400' : 'text-red-400') : 'text-white/75'}`}>{value}</div>
      </div>
    </div>
  );
}

function ResourceBar({ label, used, total, color }: { label: string; used: number; total: number; color: string }) {
  const pct = total > 0 ? Math.min(100, Math.round((used / total) * 100)) : 0;
  const barColor = color === 'green' ? 'bg-green-500' : 'bg-blue-500';
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs text-white/55">{label}</span>
        <span className="text-xs text-white/75 font-medium">{used}/{total}</span>
      </div>
      <div className="h-1.5 bg-white/[0.08] rounded-full overflow-hidden">
        <div className={`h-full ${barColor} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function HealthCheck({ label, ok, warn, detail }: { label: string; ok: boolean; warn?: boolean; detail?: string }) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-xs text-white/55">{label}</span>
      <div className="flex items-center gap-2">
        {detail && <span className="text-[10px] text-white/45">{detail}</span>}
        <div className={`w-2 h-2 rounded-full ${ok ? (warn ? 'bg-yellow-400' : 'bg-green-400') : 'bg-red-400'}`} />
      </div>
    </div>
  );
}

function formatMB(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb} MB`;
}

function getActivityStyle(action: string): { dot: string; badge: string } {
  if (action.includes('start')) return { dot: 'bg-green-400', badge: 'bg-green-500/10 text-green-400' };
  if (action.includes('delete') || action.includes('destroy')) return { dot: 'bg-red-400', badge: 'bg-red-500/10 text-red-400' };
  if (action.includes('create') || action.includes('clone') || action.includes('import')) return { dot: 'bg-blue-400', badge: 'bg-blue-500/10 text-blue-400' };
  if (action.includes('resize') || action.includes('promote')) return { dot: 'bg-yellow-400', badge: 'bg-yellow-500/10 text-yellow-400' };
  if (action.includes('stop') || action.includes('shutdown') || action.includes('reboot')) return { dot: 'bg-orange-400', badge: 'bg-orange-500/10 text-orange-400' };
  return { dot: 'bg-white/40', badge: 'bg-white/[0.06] text-white/55' };
}

function formatRelativeTime(timestamp: string): string {
  const now = Date.now();
  const then = new Date(timestamp).getTime();
  const diffSec = Math.floor((now - then) / 1000);
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}min ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ago`;
}
