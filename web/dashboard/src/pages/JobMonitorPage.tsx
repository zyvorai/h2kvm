// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useState, useCallback, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  XCircle, Clock, CheckCircle, AlertCircle, Loader2, Terminal,
  Server, Cloud, Network, Copy, ExternalLink, RefreshCw, FileText,
  FileDown, ArrowDown, Download, HardDrive, ArrowRight, ListChecks,
} from 'lucide-react';
import { useJobs, useCancelJob } from '../hooks/useJobs';
import { useWebSocketSubscription, type WSMessage } from '../contexts/WebSocketContext';
import { ProgressBar } from '../components/ProgressBar';
import { getVMStatus, getVMIP } from '../api/deploy';
import type { Job, JobProgress } from '../types/job';
import { MigrationPipelineBanner } from '../components/MigrationPipelineBanner';
import { EmptyState } from '../components/EmptyState';
import { TahoeHero } from '../components/ui/TahoeHero';
import {
  MIGRATION_PIPELINE_STAGES,
  jobPhaseLabel,
  migrationPipelineStageIndex,
  migrationPipelineStageLabel,
} from '../lib/migrationCopy';

const STATUS_CONFIG: Record<string, { icon: React.ElementType; color: string; bg: string }> = {
  pending:   { icon: Clock,       color: 'text-yellow-400', bg: 'bg-yellow-500/10' },
  running:   { icon: Loader2,     color: 'text-blue-400',   bg: 'bg-blue-500/10' },
  completed: { icon: CheckCircle, color: 'text-green-400',  bg: 'bg-green-500/10' },
  failed:    { icon: AlertCircle, color: 'text-red-400',    bg: 'bg-red-500/10' },
  cancelled: { icon: XCircle,     color: 'text-red-400',    bg: 'bg-red-500/10' },
};

export function JobMonitorPage() {
  const { data: jobs, isLoading } = useJobs();
  const cancelJob = useCancelJob();
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [liveProgress, setLiveProgress] = useState<Record<string, JobProgress>>({});
  const [liveLogs, setLiveLogs] = useState<Record<string, string[]>>({});
  const [jobFilter, setJobFilter] = useState<'all' | 'running' | 'completed' | 'failed'>('all');

  const onMessage = useCallback((msg: WSMessage) => {
    const jobId = msg.data.job_id as string;
    if (!jobId) return;
    if (msg.type === 'job_progress' && msg.data.progress) {
      setLiveProgress((prev) => ({ ...prev, [jobId]: msg.data.progress as JobProgress }));
    }
    if (msg.type === 'job_log' && msg.data.line) {
      setLiveLogs((prev) => ({
        ...prev,
        [jobId]: [...(prev[jobId] || []).slice(-999), msg.data.line as string],
      }));
    }
    // Auto-select newly created jobs
    if (msg.type === 'job_created') {
      setSelectedJobId(jobId);
    }
  }, []);

  useWebSocketSubscription(onMessage);

  const selectedJob = jobs?.find((j) => j.id === selectedJobId);
  const filteredJobs = jobs?.filter((j) => jobFilter === 'all' || j.status === jobFilter);

  // Auto-select first running job if none selected
  useEffect(() => {
    if (!selectedJobId && jobs?.length) {
      const running = jobs.find((j) => j.status === 'running');
      setSelectedJobId(running?.id || jobs[0].id);
    }
  }, [jobs, selectedJobId]);

  return (
    <div>
      <TahoeHero
        icon={<ListChecks className="w-5 h-5 text-blue-300" />}
        title="Job Monitor"
        subtitle="Real-time migration progress and deployment status"
      />
      <MigrationPipelineBanner className="mb-6" compact />

      {/* Job filter buttons */}
      <div className="flex items-center gap-2 mb-4">
        {(['all', 'running', 'completed', 'failed'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setJobFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              jobFilter === f
                ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                : 'tahoe-glass-card text-white/55 border border-white/[0.08] hover:text-white/90 hover:bg-white/[0.04]'
            }`}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-6">
        {/* Job list */}
        <div className="space-y-2 max-h-[calc(100vh-200px)] overflow-auto">
          {isLoading && [1, 2, 3].map((i) => <div key={i} className="skeleton h-20 rounded-xl" />)}
          {filteredJobs?.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              progress={liveProgress[job.id]}
              selected={selectedJobId === job.id}
              onClick={() => setSelectedJobId(job.id)}
            />
          ))}
          {filteredJobs?.length === 0 && !isLoading && (
            <EmptyState
              icon={<ListChecks className="w-10 h-10 text-white/45" />}
              title={jobFilter === 'all' ? 'No migration jobs yet' : `No ${jobFilter} jobs`}
              description="Start from the Migrate hub or export from a connected provider. Track Export → Convert → Fix OS → Deploy here."
            />
          )}
        </div>

        {/* Job detail */}
        <div className="space-y-4">
          {selectedJob ? (
            <>
              {/* Header */}
              <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-3">
                      <h3 className="text-lg font-semibold text-white truncate">Job {selectedJob.id}</h3>
                      <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_CONFIG[selectedJob.status]?.bg} ${STATUS_CONFIG[selectedJob.status]?.color}`}>
                        {selectedJob.status}
                      </span>
                    </div>
                    <div className="text-xs text-white/45 mt-1">
                      {selectedJob.config.command}
                      {selectedJob.config.vm_name && ` — ${selectedJob.config.vm_name}`}
                      {' · '}
                      {new Date(selectedJob.created_at).toLocaleString()}
                      {selectedJob.started_at && selectedJob.completed_at && (
                        <span className="ml-2">
                          Duration: {formatDuration(new Date(selectedJob.started_at), new Date(selectedJob.completed_at))}
                        </span>
                      )}
                    </div>
                    {(() => {
                      const src = selectedJob.config.vmdk || selectedJob.config.ova || selectedJob.config.ovf || selectedJob.config.vhd || selectedJob.config.raw;
                      return src ? (
                        <div className="flex items-center gap-1.5 mt-1 text-xs text-white/45">
                          <FileText className="h-3 w-3 flex-shrink-0" />
                          <span className="font-mono truncate">{src}</span>
                        </div>
                      ) : null;
                    })()}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {selectedJob.status === 'completed' && selectedJob.config.output_dir && selectedJob.config.to_output && (
                      <button
                        onClick={() => {
                          const outputPath = `${selectedJob.config.output_dir}/${selectedJob.config.to_output}`;
                          window.open(`/api/v1/download?path=${encodeURIComponent(outputPath)}`, '_blank');
                        }}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors"
                      >
                        <Download className="h-3.5 w-3.5" /> Download Image
                      </button>
                    )}
                    {(selectedJob.status === 'completed' || selectedJob.status === 'failed') && (
                      <button
                        onClick={() => {
                          const url = `/api/v1/jobs/${selectedJob.id}/report`;
                          fetch(url, { credentials: 'include' })
                            .then((res) => {
                              if (!res.ok) throw new Error('Report not available');
                              return res.blob();
                            })
                            .then((blob) => {
                              const a = document.createElement('a');
                              a.href = URL.createObjectURL(blob);
                              a.download = `migration-report-${selectedJob.id}.txt`;
                              a.click();
                              URL.revokeObjectURL(a.href);
                            })
                            .catch(() => window.open(`/api/v1/jobs/${selectedJob.id}/report`, '_blank'));
                        }}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors"
                      >
                        <FileDown className="h-3.5 w-3.5" /> Download Report
                      </button>
                    )}
                    {(selectedJob.status === 'running' || selectedJob.status === 'pending') && (
                      <button
                        onClick={() => cancelJob.mutate(selectedJob.id)}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors"
                      >
                        <XCircle className="h-3.5 w-3.5" /> Cancel
                      </button>
                    )}
                  </div>
                </div>

                {/* Progress bar for running jobs */}
                {selectedJob.status === 'running' && (
                  <div>
                    <ProgressBar
                      percent={liveProgress[selectedJob.id]?.percent_complete ?? selectedJob.progress?.percent_complete ?? 0}
                      label={liveProgress[selectedJob.id]?.current_step ?? selectedJob.progress?.current_step ?? 'Running...'}
                    />
                    <div className="flex items-center gap-4 text-xs text-white/45 mt-2">
                      {(liveProgress[selectedJob.id]?.phase || selectedJob.progress?.phase) && (
                        <span>
                          Phase:{' '}
                          <span className="text-white/75">
                            {jobPhaseLabel(liveProgress[selectedJob.id]?.phase || selectedJob.progress?.phase || '')}
                          </span>
                        </span>
                      )}
                      {liveProgress[selectedJob.id]?.rate && (
                        <span>Rate: <span className="text-white/75">{liveProgress[selectedJob.id]?.rate}</span></span>
                      )}
                      {liveProgress[selectedJob.id]?.eta && (
                        <span>ETA: <span className="text-white/75">{liveProgress[selectedJob.id]?.eta}</span></span>
                      )}
                    </div>
                  </div>
                )}

                {(selectedJob.status === 'running' || selectedJob.status === 'completed' || selectedJob.status === 'failed') &&
                  (liveProgress[selectedJob.id]?.phase || selectedJob.progress?.phase) && (
                  <BackendPipelineBar
                    phase={liveProgress[selectedJob.id]?.phase || selectedJob.progress?.phase || ''}
                    currentStep={liveProgress[selectedJob.id]?.current_step || selectedJob.progress?.current_step}
                    status={selectedJob.status}
                  />
                )}

                {/* Error */}
                {selectedJob.error && (
                  <div className="mt-3 bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-sm text-red-400">
                    {selectedJob.error}
                  </div>
                )}
              </div>

              {/* Migration Timeline */}
              {(selectedJob.status === 'running' || selectedJob.status === 'completed' || selectedJob.status === 'failed') && (
                <MigrationTimeline
                  logLines={liveLogs[selectedJob.id] || selectedJob.log_lines || []}
                  status={selectedJob.status}
                />
              )}

              {/* Deployment status — shown after completion */}
              {selectedJob.status === 'completed' && selectedJob.config.vm_name && (
                <DeploymentStatus vmName={selectedJob.config.vm_name} config={selectedJob.config} />
              )}

              {/* Migration Summary — shown after completion */}
              {selectedJob.status === 'completed' && (
                <MigrationSummary config={selectedJob.config} />
              )}

              {/* Live logs */}
              <div className="tahoe-glass-card rounded-xl border border-white/[0.08] overflow-hidden">
                <div className="flex items-center gap-2 px-4 py-3 border-b border-white/[0.06]">
                  <Terminal className="h-4 w-4 text-green-400" />
                  <span className="text-sm font-semibold text-white">Live Logs</span>
                  {selectedJob.status === 'running' && (
                    <span className="flex items-center gap-1.5 text-xs text-green-400">
                      <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse-dot" />
                      streaming
                    </span>
                  )}
                  <span className="text-xs text-white/45 ml-auto">
                    {(liveLogs[selectedJob.id] || selectedJob.log_lines || []).length} lines
                  </span>
                </div>
                <LiveLogViewer
                  lines={liveLogs[selectedJob.id] || selectedJob.log_lines || []}
                  isRunning={selectedJob.status === 'running'}
                />
              </div>
            </>
          ) : (
            <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5 text-center py-16 text-sm text-white/45">
              Select a job to view details
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// --- Backend pipeline bar (4-step UI from JobProgress.phase) ---

function BackendPipelineBar({
  phase,
  currentStep,
  status,
}: {
  phase: string;
  currentStep?: string;
  status: string;
}) {
  const currentIdx = migrationPipelineStageIndex(phase);

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
      <div className="flex items-center gap-0">
        {MIGRATION_PIPELINE_STAGES.map((stage, idx) => {
          let classes = 'bg-white/[0.08] text-white/55';
          let lineClass = 'h-0.5 flex-1 bg-white/[0.08]';

          if (idx < currentIdx || (status === 'completed' && idx <= currentIdx)) {
            classes = 'bg-green-500 text-white';
            lineClass = 'h-0.5 flex-1 bg-green-500';
          } else if (idx === currentIdx) {
            classes = status === 'failed' ? 'bg-red-500 text-white' : 'bg-blue-500 text-white animate-pulse';
            lineClass = 'h-0.5 flex-1 bg-blue-500';
          }

          return (
            <div key={stage} className="flex items-center flex-1 min-w-0">
              {idx > 0 && <div className={lineClass} />}
              <div className={`px-2 py-1 text-[10px] font-semibold rounded whitespace-nowrap ${classes}`}>
                {stage}
              </div>
            </div>
          );
        })}
      </div>
      {(currentStep || phase) && (
        <p className="text-[10px] text-white/45 mt-2">
          Step detail: {currentStep || jobPhaseLabel(phase)}
        </p>
      )}
    </div>
  );
}

// --- Migration Timeline ---

interface TimelinePhase {
  name: string;
  status: 'done' | 'active' | 'pending';
  duration?: string;
}

function detectPhases(logLines: string[], jobStatus: string): TimelinePhase[] {
  const phases: { name: string; pattern: RegExp; detectedAt?: number }[] = [
    { name: 'Flatten', pattern: /[Ff]latten|flattening/i },
    { name: 'Offline Fix', pattern: /[Oo]ffline|regen_initramfs|update_grub|fstab|remove_vmware/i },
    { name: 'Convert', pattern: /[Cc]onvert|qemu-img|converting/i },
    { name: 'Deploy', pattern: /emit_domain_xml|virsh define|[Ll]ibvirt smoke test|deploy_k8s|deploy_openstack|OpenStack deployment|Uploaded to Glance|domain.*defined/i },
  ];

  // Scan log lines to detect phase transitions.
  for (let i = 0; i < logLines.length; i++) {
    const line = logLines[i];
    for (let p = 0; p < phases.length; p++) {
      if (phases[p].detectedAt === undefined && phases[p].pattern.test(line)) {
        // Rough timestamp: assume even distribution if no timestamps in lines.
        phases[p].detectedAt = i;
      }
    }
  }

  // Determine statuses.
  const lastDetected = phases.reduce((max, p) => (p.detectedAt !== undefined ? Math.max(max, phases.indexOf(p)) : max), -1);

  return phases.map((p, idx) => {
    let status: 'done' | 'active' | 'pending' = 'pending';
    if (p.detectedAt !== undefined) {
      if (idx < lastDetected || jobStatus === 'completed') {
        status = 'done';
      } else if (idx === lastDetected && jobStatus === 'running') {
        status = 'active';
      } else if (jobStatus === 'completed' || jobStatus === 'failed') {
        status = 'done';
      }
    }
    // If job failed at this phase, mark as done (it ran but failed).
    if (jobStatus === 'failed' && idx === lastDetected && p.detectedAt !== undefined) {
      status = 'done';
    }
    return { name: p.name, status };
  });
}

function MigrationTimeline({ logLines, status }: { logLines: string[]; status: string }) {
  const phases = detectPhases(logLines, status);
  const anyDetected = phases.some((p) => p.status !== 'pending');

  if (!anyDetected && status === 'running' && logLines.length < 3) {
    return null; // Don't show until we have some log lines.
  }

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
      <div className="flex items-center gap-2 mb-4">
        <ArrowRight className="h-4 w-4 text-blue-400" />
        <h4 className="text-sm font-semibold text-white">Migration Timeline</h4>
      </div>

      <div className="flex items-center gap-0">
        {phases.map((phase, idx) => (
          <div key={phase.name} className="flex items-center flex-1">
            {/* Phase block */}
            <div className="flex flex-col items-center flex-1">
              {/* Status indicator */}
              <div className={`w-6 h-6 rounded-full flex items-center justify-center mb-2 ${
                phase.status === 'done'
                  ? 'bg-green-500/20 border-2 border-green-400'
                  : phase.status === 'active'
                  ? 'bg-blue-500/20 border-2 border-blue-400 animate-pulse'
                  : 'bg-white/[0.08]/50 border-2 border-white/[0.12]'
              }`}>
                {phase.status === 'done' ? (
                  <CheckCircle className="h-3.5 w-3.5 text-green-400" />
                ) : phase.status === 'active' ? (
                  <Loader2 className="h-3.5 w-3.5 text-blue-400 animate-spin" />
                ) : (
                  <Clock className="h-3 w-3 text-yellow-400" />
                )}
              </div>
              {/* Phase bar */}
              <div className={`w-full h-1.5 rounded-full ${
                phase.status === 'done'
                  ? 'bg-green-500/40'
                  : phase.status === 'active'
                  ? 'bg-blue-500/40'
                  : 'bg-white/[0.08]/50'
              }`} />
              {/* Phase name */}
              <span className={`text-[10px] font-medium mt-2 ${
                phase.status === 'done'
                  ? 'text-green-400'
                  : phase.status === 'active'
                  ? 'text-blue-400'
                  : 'text-white/45'
              }`}>
                {phase.name}
              </span>
            </div>
            {/* Connector */}
            {idx < phases.length - 1 && (
              <div className={`w-3 h-0.5 mt-[-16px] ${
                phase.status === 'done' ? 'bg-green-500/40' : 'bg-white/[0.08]/50'
              }`} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// --- Deployment Status Panel ---

function DeploymentStatus({ vmName, config }: { vmName: string; config: Job['config'] }) {
  const [sshUser, setSshUser] = useState('root');
  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ['deploy-status', vmName],
    queryFn: () => getVMStatus(vmName),
    refetchInterval: 5000,
  });

  const { data: ipData, refetch: refetchIP } = useQuery({
    queryKey: ['deploy-ip', vmName],
    queryFn: () => getVMIP(vmName),
    refetchInterval: 5000,
  });

  const hasLibvirt = config.emit_domain_xml || config.libvirt_test;
  const hasK8s = config.deploy_k8s;
  const hasOpenStack = config.deploy_openstack;
  const ips = ipData?.ips || [];

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <CheckCircle className="h-5 w-5 text-green-400" />
          <h4 className="text-sm font-semibold text-white">Deployment Status</h4>
        </div>
        <button
          onClick={() => { refetchStatus(); refetchIP(); }}
          className="flex items-center gap-1 text-xs text-white/55 hover:text-white transition-colors"
        >
          <RefreshCw className="h-3 w-3" /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Libvirt status */}
        {hasLibvirt && (
          <div className="tahoe-glass-card rounded-lg border border-white/[0.06] p-4">
            <div className="flex items-center gap-2 mb-3">
              <Server className="h-4 w-4 text-blue-400" />
              <span className="text-sm font-medium text-white">Libvirt</span>
            </div>
            {status?.libvirt?.defined ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-white/55">Domain</span>
                  <span className="text-white font-mono">{vmName}</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-white/55">State</span>
                  <span className={`font-medium ${status.libvirt.running ? 'text-green-400' : 'text-yellow-400'}`}>
                    {status.libvirt.state || (status.libvirt.running ? 'running' : 'defined')}
                  </span>
                </div>
              </div>
            ) : (
              <div className="text-xs text-white/45 flex items-center gap-1.5">
                <Loader2 className="h-3 w-3 animate-spin" /> Waiting for domain...
              </div>
            )}
          </div>
        )}

        {/* KubeVirt status */}
        {hasK8s && (
          <div className="tahoe-glass-card rounded-lg border border-white/[0.06] p-4">
            <div className="flex items-center gap-2 mb-3">
              <Cloud className="h-4 w-4 text-sky-400" />
              <span className="text-sm font-medium text-white">KubeVirt</span>
            </div>
            {status?.kubevirt?.defined ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-white/55">VMI</span>
                  <span className="text-white font-mono">{vmName}</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-white/55">Phase</span>
                  <span className={`font-medium ${status.kubevirt.running ? 'text-green-400' : 'text-yellow-400'}`}>
                    {status.kubevirt.phase || 'pending'}
                  </span>
                </div>
              </div>
            ) : (
              <div className="text-xs text-white/45 flex items-center gap-1.5">
                <Loader2 className="h-3 w-3 animate-spin" /> Waiting for VMI...
              </div>
            )}
          </div>
        )}

        {hasOpenStack && (
          <div className="tahoe-glass-card rounded-lg border border-white/[0.06] p-4">
            <div className="flex items-center gap-2 mb-3">
              <Cloud className="h-4 w-4 text-orange-400" />
              <span className="text-sm font-medium text-white">OpenStack</span>
            </div>
            <div className="space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-white/55">Glance image</span>
                <span className="text-white font-mono">{config.glance_name || vmName}</span>
              </div>
              {config.os_cloud && (
                <div className="flex items-center justify-between">
                  <span className="text-white/55">Cloud</span>
                  <span className="text-white/75">{config.os_cloud}</span>
                </div>
              )}
              {status?.openstack?.defined ? (
                <>
                  <div className="flex items-center justify-between">
                    <span className="text-white/55">
                      {status.openstack.server_id ? 'Nova' : 'Glance'}
                    </span>
                    <span
                      className={`font-medium ${status.openstack.running ? 'text-green-400' : 'text-yellow-400'}`}
                    >
                      {status.openstack.status || (status.openstack.running ? 'active' : 'pending')}
                    </span>
                  </div>
                  {status.openstack.server_id && (
                    <div className="flex items-center justify-between">
                      <span className="text-white/55">Server ID</span>
                      <span className="text-white/75 font-mono truncate max-w-[140px]">
                        {status.openstack.server_id}
                      </span>
                    </div>
                  )}
                  {status.openstack.image_id && !status.openstack.server_id && (
                    <div className="flex items-center justify-between">
                      <span className="text-white/55">Image ID</span>
                      <span className="text-white/75 font-mono truncate max-w-[140px]">
                        {status.openstack.image_id}
                      </span>
                    </div>
                  )}
                </>
              ) : config.openstack_boot_instance ? (
                <div className="text-white/45 flex items-center gap-1.5">
                  <Loader2 className="h-3 w-3 animate-spin" /> Waiting for Glance / Nova...
                </div>
              ) : (
                <div className="text-white/45 flex items-center gap-1.5">
                  <Loader2 className="h-3 w-3 animate-spin" /> Waiting for Glance upload...
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* IP Addresses */}
      <div className="mt-4 tahoe-glass-card rounded-lg border border-white/[0.06] p-4">
        <div className="flex items-center gap-2 mb-3">
          <Network className="h-4 w-4 text-cyan-400" />
          <span className="text-sm font-medium text-white">Network</span>
          {ipData?.source && (
            <span className="text-[10px] text-white/45 glass px-1.5 py-0.5 rounded">{ipData.source}</span>
          )}
          <div className="ml-auto flex items-center gap-1.5">
            <label className="text-[10px] text-white/45">SSH User:</label>
            <input
              type="text"
              value={sshUser}
              onChange={(e) => setSshUser(e.target.value)}
              className="px-1.5 py-0.5 glass border border-white/[0.08] rounded text-[10px] text-white/75 w-20 focus:outline-none focus:border-cyan-500/50"
            />
          </div>
        </div>

        {ips.length > 0 ? (
          <div className="space-y-2">
            {ips.map((ip) => (
              <div key={ip} className="flex items-center justify-between tahoe-glass-card rounded-lg px-3 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-green-400" />
                  <span className="text-sm font-mono text-green-300 font-medium">{ip}</span>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => navigator.clipboard.writeText(ip)}
                    className="h-7 w-7 rounded hover:bg-white/[0.04] flex items-center justify-center transition-colors text-white/55 hover:text-white"
                    title="Copy IP"
                  >
                    <Copy className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => window.open(`ssh://${sshUser}@${ip}`, '_blank')}
                    className="h-7 w-7 rounded hover:bg-white/[0.04] flex items-center justify-center transition-colors text-white/55 hover:text-white"
                    title="SSH"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex items-center gap-2 text-xs text-white/45">
            <Loader2 className="h-3 w-3 animate-spin" />
            Waiting for IP address... (VM is booting)
          </div>
        )}
      </div>
    </div>
  );
}

// --- Migration Summary (Before/After) ---

function MigrationSummary({ config }: { config: Job['config'] }) {
  const sourcePath = config.vmdk || config.ova || config.ovf || config.vhd || config.raw || '';
  const sourceFileName = sourcePath.split('/').pop() || 'Unknown';
  const sourceFormat = (() => {
    const ext = sourcePath.split('.').pop()?.toLowerCase();
    const map: Record<string, string> = { vmdk: 'VMDK', ova: 'OVA', ovf: 'OVF', vhd: 'VHD', vhdx: 'VHDX', raw: 'RAW', qcow2: 'QCOW2' };
    return map[ext || ''] || ext?.toUpperCase() || 'Unknown';
  })();
  const outputFileName = config.to_output || `${config.vm_name || 'output'}.${config.out_format || 'qcow2'}`;
  const outputFormat = (config.out_format || 'qcow2').toUpperCase();
  const outputDir = config.output_dir || '/tmp/h2kweb-output';

  const fixes: string[] = [];
  if (config.flatten) fixes.push('Flatten snapshots');
  if (config.compress) fixes.push('Compress output');
  if (config.fstab_mode && config.fstab_mode !== 'noop' && config.fstab_mode !== 'none') fixes.push(`fstab: ${config.fstab_mode}`);
  if (config.regen_initramfs) fixes.push('Regenerate initramfs');
  if (config.update_grub) fixes.push('Update GRUB');
  if (config.remove_vmware_tools) fixes.push('Remove VMware tools');
  if (config.enable_rdp) fixes.push('Enable RDP (Windows firstboot)');
  if (config.guest_os) fixes.push(`Guest OS: ${config.guest_os}`);

  const deploy: string[] = [];
  if (config.emit_domain_xml) deploy.push('Emit domain XML');
  if (config.virsh_define) deploy.push('virsh define');
  if (config.libvirt_test) deploy.push('Libvirt boot test');
  if (config.deploy_k8s) deploy.push('Deploy to KubeVirt');
  if (config.deploy_openstack) {
    const label = config.glance_name
      ? `OpenStack Glance: ${config.glance_name}`
      : 'Upload to OpenStack Glance';
    deploy.push(label);
    if (config.openstack_boot_instance) deploy.push('Boot Nova instance');
  }

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
      <div className="flex items-center gap-2 mb-4">
        <HardDrive className="h-5 w-5 text-blue-400" />
        <h4 className="text-sm font-semibold text-white">Migration Summary</h4>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Source */}
        <div className="tahoe-glass-card rounded-lg border border-white/[0.06] p-4">
          <div className="flex items-center gap-2 mb-3">
            <ArrowRight className="h-4 w-4 text-orange-400" />
            <span className="text-xs font-semibold text-white/55 uppercase tracking-wider">Source</span>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-white/45">Filename</span>
              <span className="text-white font-mono truncate ml-2 max-w-[200px]" title={sourceFileName}>{sourceFileName}</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-white/45">Format</span>
              <span className="text-blue-400 font-medium">{sourceFormat}</span>
            </div>
          </div>
        </div>

        {/* Output */}
        <div className="tahoe-glass-card rounded-lg border border-white/[0.06] p-4">
          <div className="flex items-center gap-2 mb-3">
            <ArrowRight className="h-4 w-4 text-green-400" />
            <span className="text-xs font-semibold text-white/55 uppercase tracking-wider">Output</span>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-white/45">Filename</span>
              <span className="text-white font-mono truncate ml-2 max-w-[200px]" title={outputFileName}>{outputFileName}</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-white/45">Format</span>
              <span className="text-green-400 font-medium">{outputFormat}</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-white/45">Directory</span>
              <span className="text-white font-mono truncate ml-2 max-w-[200px]" title={outputDir}>{outputDir}</span>
            </div>
          </div>
        </div>

        {/* Fixes Applied */}
        <div className="tahoe-glass-card rounded-lg border border-white/[0.06] p-4">
          <div className="flex items-center gap-2 mb-3">
            <CheckCircle className="h-4 w-4 text-yellow-400" />
            <span className="text-xs font-semibold text-white/55 uppercase tracking-wider">Fixes Applied</span>
          </div>
          {fixes.length > 0 ? (
            <div className="space-y-1.5">
              {fixes.map((fix) => (
                <div key={fix} className="flex items-center gap-2 text-xs">
                  <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 flex-shrink-0" />
                  <span className="text-white/75">{fix}</span>
                </div>
              ))}
            </div>
          ) : (
            <span className="text-xs text-white/45">No fixes applied</span>
          )}
        </div>

        {/* Deploy */}
        <div className="tahoe-glass-card rounded-lg border border-white/[0.06] p-4">
          <div className="flex items-center gap-2 mb-3">
            <Server className="h-4 w-4 text-purple-400" />
            <span className="text-xs font-semibold text-white/55 uppercase tracking-wider">Deploy</span>
          </div>
          {deploy.length > 0 ? (
            <div className="space-y-1.5">
              {deploy.map((d) => (
                <div key={d} className="flex items-center gap-2 text-xs">
                  <span className="w-1.5 h-1.5 rounded-full bg-purple-400 flex-shrink-0" />
                  <span className="text-white/75">{d}</span>
                </div>
              ))}
            </div>
          ) : (
            <span className="text-xs text-white/45">No deployment actions</span>
          )}
        </div>
      </div>
    </div>
  );
}

// --- Full-height live log viewer ---

function LiveLogViewer({ lines, isRunning }: { lines: string[]; isRunning: boolean }) {
  const [autoScroll, setAutoScroll] = useState(true);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (autoScroll && logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [lines, autoScroll]);

  return (
    <div className="relative">
      {/* Auto-scroll toggle bar */}
      <div className="flex items-center justify-between px-4 py-1.5 bg-[#0a0f1a] border-b border-white/[0.08]">
        <div className="flex items-center gap-2">
          {autoScroll && isRunning && (
            <span className="flex items-center gap-1.5 text-[10px] text-green-400 font-medium">
              <ArrowDown className="h-3 w-3" />
              Following
            </span>
          )}
          {!autoScroll && isRunning && (
            <span className="text-[10px] text-white/45 font-medium">Paused — scroll stopped</span>
          )}
        </div>
        <button
          onClick={() => {
            const next = !autoScroll;
            setAutoScroll(next);
            if (next && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
          }}
          className={`flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-medium transition-colors ${
            autoScroll
              ? 'bg-green-500/10 text-green-400 hover:bg-green-500/20'
              : 'bg-white/[0.08]/50 text-white/55 hover:bg-white/[0.04]'
          }`}
        >
          <ArrowDown className="h-3 w-3" />
          {autoScroll ? 'Auto-scroll on' : 'Auto-scroll off'}
        </button>
      </div>

      <div
        ref={logRef}
        className="bg-[#020617] p-4 overflow-auto font-mono text-xs leading-6 max-h-[500px] min-h-[200px]"
        style={{ fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace" }}
        onScroll={() => {
          if (!logRef.current) return;
          const el = logRef.current;
          const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50;
          setAutoScroll(atBottom);
        }}
      >
        {lines.length === 0 ? (
          <div className="text-white/40 flex items-center gap-2">
            {isRunning && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {isRunning ? 'Waiting for output...' : 'No output captured'}
          </div>
        ) : (
          lines.map((line, i) => (
            <div key={i} className={`${getLineClass(line)} hover:tahoe-glass-card rounded px-1 -mx-1`}>
              <span className="text-white/20 select-none mr-3 inline-block w-8 text-right tabular-nums">{i + 1}</span>
              {line}
            </div>
          ))
        )}
      </div>

      {/* Jump to bottom button when scrolled up */}
      {!autoScroll && lines.length > 20 && (
        <button
          onClick={() => { setAutoScroll(true); if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }}
          className="absolute bottom-3 right-3 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600/90 text-white text-xs font-medium shadow-lg hover:bg-blue-500 transition-colors"
        >
          <ArrowDown className="h-3 w-3" /> Scroll to bottom
        </button>
      )}
    </div>
  );
}

function getLineClass(line: string): string {
  if (line.includes('ERROR') || line.includes('error') || line.includes('Traceback')) return 'text-red-400';
  if (line.includes('WARNING') || line.includes('warning')) return 'text-yellow-400';
  if (line.includes('SUCCESS') || line.includes('completed') || line.includes('✓')) return 'text-green-400';
  if (line.includes('[PROGRESS]') || line.includes('progress')) return 'text-blue-400';
  if (line.includes('INFO') || line.includes('>>>')) return 'text-white/75';
  return 'text-white/55';
}

function formatDuration(start: Date, end: Date): string {
  const sec = Math.round((end.getTime() - start.getTime()) / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const s = sec % 60;
  if (min < 60) return `${min}m ${s}s`;
  const hr = Math.floor(min / 60);
  return `${hr}h ${min % 60}m`;
}

// --- Job card ---

function JobCard({ job, progress, selected, onClick }: {
  job: Job; progress?: JobProgress; selected: boolean; onClick: () => void;
}) {
  const cfg = STATUS_CONFIG[job.status] || STATUS_CONFIG.pending;
  const Icon = cfg.icon;
  const pct = progress?.percent_complete ?? job.progress?.percent_complete ?? 0;

  return (
    <div
      onClick={onClick}
      className={`p-3 rounded-xl border cursor-pointer transition-all ${
        selected
          ? 'bg-blue-600/10 border-blue-500/50 shadow-lg shadow-blue-500/5'
          : 'tahoe-glass-card border-white/[0.08] hover:glass hover:border-white/[0.12]'
      }`}
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium text-white font-mono">{job.id}</span>
        <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${cfg.bg} ${cfg.color}`}>
          <Icon className={`h-3 w-3 ${job.status === 'running' ? 'animate-spin' : ''}`} />
          {job.status}
        </span>
      </div>
      <div className="text-xs text-white/45">
        {job.config.command}
        {job.config.vm_name && ` — ${job.config.vm_name}`}
      </div>
      {(() => {
        const src = job.config.vmdk || job.config.ova || job.config.ovf || job.config.vhd || job.config.raw;
        return src ? (
          <div className="flex items-center gap-1 mt-1 text-[10px] text-white/40 truncate">
            <FileText className="h-3 w-3 flex-shrink-0" />
            <span className="font-mono truncate">{src}</span>
          </div>
        ) : null;
      })()}
      {(progress?.phase || job.progress?.phase) && job.status !== 'pending' && (
        <div className="text-[10px] text-white/45 mt-1">
          {migrationPipelineStageLabel(progress?.phase || job.progress?.phase || '')}
          {job.status === 'running' && (progress?.current_step || job.progress?.current_step)
            ? ` · ${progress?.current_step || job.progress?.current_step}`
            : ''}
        </div>
      )}
      {job.status === 'running' && pct > 0 && (
        <div className="mt-2">
          <div className="h-1.5 bg-white/[0.08] rounded-full overflow-hidden">
            <div className="h-full bg-blue-500 rounded-full transition-all duration-500" style={{ width: `${pct}%` }} />
          </div>
          <div className="text-[10px] text-white/40 mt-1">{Math.round(pct)}%</div>
        </div>
      )}
      {job.status === 'completed' && (
        <div className="flex items-center justify-between mt-1">
          <span className="text-[10px] text-green-500">Migration complete</span>
          {job.started_at && job.completed_at && (
            <span className="text-[10px] text-white/45">{formatDuration(new Date(job.started_at), new Date(job.completed_at))}</span>
          )}
        </div>
      )}
      {job.status === 'failed' && (
        <div className="mt-1 text-[10px] text-red-400">Migration failed</div>
      )}
    </div>
  );
}
