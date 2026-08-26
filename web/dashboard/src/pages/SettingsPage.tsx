// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Settings, Terminal, Globe, Key, HardDrive, FolderOpen, AlertCircle, CheckCircle, Loader2, ArrowRight, Shield, Users, UserPlus, Lock, ShieldCheck, Mail, Download, Upload, Send, Trash2, Clock, Zap, ToggleLeft, ToggleRight, LayoutGrid } from 'lucide-react';
import { fetchAPI } from '../api/client';
import { useDesktopTier } from '../hooks/useDesktopTier';
import { DesktopTierPicker } from '../desktop/DesktopTierPicker';
import { TahoeHero } from '../components/ui/TahoeHero';

interface StorageConfig {
  default_path: string;
  actual_path: string;
  is_symlink: boolean;
  symlink_target?: string;
  device: string;
  total: string;
  used: string;
  avail: string;
  percent: string;
  mountpoint: string;
  images?: { name: string; size: number; type: string }[];
  image_count: number;
  selinux: string;
}

export function SettingsPage() {
  const [tier, setTier] = useDesktopTier();

  return (
    <div className="space-y-6">
      <TahoeHero
        icon={<Settings className="w-5 h-5 text-blue-300" />}
        title="Settings"
        subtitle="Storage, users, desktop tier, and system configuration"
      />

      <div className="tahoe-glass-card border border-white/[0.08] rounded-xl p-5">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
          <LayoutGrid className="w-5 h-5 text-blue-400" />
          Desktop tier
        </h3>
        <DesktopTierPicker tier={tier} onChange={setTier} />
      </div>

      {/* Storage Management */}
      <StorageSection />

      {/* Storage Cleanup */}
      <StorageCleanupSection />

      {/* Auto Cleanup */}
      <AutoCleanupSection />

      {/* Email Notifications */}
      <EmailSection />

      {/* Config Backup/Restore */}
      <ConfigBackupSection />

      {/* User Management */}
      <UserSection />

      {/* Server Config */}
      <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
        <div className="flex items-center gap-2 mb-4">
          <Settings className="h-4 w-4 text-purple-400" />
          <h3 className="text-sm font-semibold text-white">Server Configuration</h3>
        </div>
        <p className="text-sm text-white/55 mb-4">
          Configured via command-line flags or <code className="text-cyan-400 glass px-1.5 py-0.5 rounded">/etc/default/h2kweb</code>
        </p>
        <div className="space-y-3">
          {[
            { icon: Terminal, label: 'h2kvmctl Binary', value: '--binary /path/to/h2kvmctl', desc: 'Path to the migration CLI' },
            { icon: Globe, label: 'Listen Address', value: '--addr :5070', desc: 'HTTP server bind address' },
            { icon: Key, label: 'API Key', value: '--api-key YOUR_KEY', desc: 'Authentication (disabled if empty)' },
            { icon: Settings, label: 'Static Dir', value: '--static-dir /path/to/dist', desc: 'Dashboard static files path' },
          ].map(({ icon: Icon, label, value, desc }) => (
            <div key={label} className="flex items-start gap-4 p-3 tahoe-glass-card rounded-lg border border-white/[0.06]">
              <Icon className="h-4 w-4 text-purple-400 mt-0.5 flex-shrink-0" />
              <div>
                <div className="text-sm font-medium text-white">{label}</div>
                <div className="text-xs text-white/45 mt-0.5">{desc}</div>
                <code className="text-xs text-cyan-400 mt-1 block">{value}</code>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-5 pt-4 border-t border-white/[0.06]">
          <h4 className="text-sm font-semibold text-white mb-3">Service Management</h4>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs font-mono">
            {[
              { label: 'Status', cmd: 'systemctl status h2kweb' },
              { label: 'Logs', cmd: 'journalctl -u h2kweb -f' },
              { label: 'Restart', cmd: 'systemctl restart h2kweb' },
            ].map(({ label, cmd }) => (
              <div key={label} className="tahoe-glass-card rounded-lg p-3 border border-white/[0.06]">
                <div className="text-white/45 mb-1">{label}</div>
                <div className="text-cyan-400">{cmd}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function StorageSection() {
  const queryClient = useQueryClient();
  const { data: config, isLoading } = useQuery({
    queryKey: ['storage-config'],
    queryFn: () => fetchAPI<StorageConfig>('/storage/config'),
  });

  const [targetDir, setTargetDir] = useState('');
  const [moveData, setMoveData] = useState(true);
  const [showRelocate, setShowRelocate] = useState(false);

  const relocate = useMutation({
    mutationFn: (params: { target_dir: string; move_data: boolean }) =>
      fetchAPI<{ status: string; message: string; steps: string[] }>('/storage/relocate', {
        method: 'POST',
        body: JSON.stringify(params),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['storage-config'] });
      queryClient.invalidateQueries({ queryKey: ['host-info'] });
      setShowRelocate(false);
    },
  });

  if (isLoading) {
    return (
      <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
        <div className="skeleton h-40 rounded-lg" />
      </div>
    );
  }

  const pct = parseInt(config?.percent || '0');

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <HardDrive className="h-4 w-4 text-yellow-400" />
          <h3 className="text-sm font-semibold text-white">VM Storage</h3>
        </div>
        {!showRelocate && (
          <button
            onClick={() => setShowRelocate(true)}
            className="flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 transition-colors"
          >
            <FolderOpen className="h-3.5 w-3.5" /> Relocate Storage
          </button>
        )}
      </div>

      {/* Current config */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div className="p-4 tahoe-glass-card rounded-lg border border-white/[0.06]">
          <div className="text-xs text-white/45 mb-1">Images Path</div>
          <div className="text-sm font-mono text-white">{config?.default_path}</div>
          {config?.is_symlink && (
            <div className="flex items-center gap-1.5 mt-1.5 text-xs text-blue-400">
              <ArrowRight className="h-3 w-3" />
              <span className="font-mono">{config.symlink_target}</span>
            </div>
          )}
          <div className="text-xs text-white/45 mt-1">Device: {config?.device} ({config?.mountpoint})</div>
        </div>

        <div className="p-4 tahoe-glass-card rounded-lg border border-white/[0.06]">
          <div className="flex justify-between text-xs mb-1">
            <span className="text-white/45">Usage</span>
            <span className={`font-medium ${pct > 90 ? 'text-red-400' : pct > 75 ? 'text-yellow-400' : 'text-white/75'}`}>{config?.percent}%</span>
          </div>
          <div className="h-2 bg-white/[0.08] rounded-full overflow-hidden mb-2">
            <div className={`h-full rounded-full ${pct > 90 ? 'bg-red-500' : pct > 75 ? 'bg-yellow-500' : 'bg-blue-500'}`} style={{ width: `${pct}%` }} />
          </div>
          <div className="flex justify-between text-xs text-white/45">
            <span>{config?.used} used</span>
            <span>{config?.avail} free</span>
            <span>{config?.total} total</span>
          </div>
        </div>
      </div>

      {/* SELinux + Image count */}
      <div className="flex items-center gap-4 text-xs text-white/55 mb-4">
        <span className="flex items-center gap-1.5">
          <Shield className="h-3 w-3 text-purple-400" />
          SELinux: <span className={config?.selinux === 'Enforcing' ? 'text-green-400' : 'text-yellow-400'}>{config?.selinux}</span>
        </span>
        <span>{config?.image_count ?? 0} images stored</span>
      </div>

      {/* Images list */}
      {config?.images && config.images.length > 0 && (
        <div className="mb-4">
          <div className="text-xs text-white/45 mb-2">Stored Images</div>
          <div className="flex flex-wrap gap-2">
            {config.images.map((img) => (
              <span key={img.name} className="text-xs px-2.5 py-1 tahoe-glass-card border border-white/[0.06] rounded-lg text-white/75 font-mono">
                {img.name} <span className="text-white/45">({formatBytes(img.size)})</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Relocate form */}
      {showRelocate && (
        <div className="mt-4 pt-4 border-t border-white/[0.06] animate-fade-in">
          <h4 className="text-sm font-semibold text-white mb-3">Relocate VM Storage</h4>
          <p className="text-xs text-white/55 mb-4">
            Move <code className="text-cyan-400">/var/lib/libvirt/images</code> to another disk.
            Creates a symlink, fixes SELinux contexts, and sets qemu:qemu ownership.
          </p>

          {pct > 75 && (
            <div className="flex items-center gap-2 bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-3 mb-4 text-xs text-yellow-400">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              Current storage is {config?.percent}% full. Consider relocating to a larger disk.
            </div>
          )}

          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-white/55 mb-1.5">Target Directory</label>
              <input
                type="text"
                value={targetDir}
                onChange={(e) => setTargetDir(e.target.value)}
                placeholder="/data/libvirt/images"
                className="w-full px-3 py-2.5 tahoe-glass-card border border-white/[0.12] rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-sm font-mono"
              />
            </div>

            <label className="flex items-center gap-2 cursor-pointer text-sm text-white/75">
              <input type="checkbox" checked={moveData} onChange={(e) => setMoveData(e.target.checked)} className="accent-blue-500 h-4 w-4 rounded" />
              Move existing images to new location
            </label>
          </div>

          <div className="mt-4 p-3 tahoe-glass-card rounded-lg border border-white/[0.06] text-xs text-white/55">
            <div className="font-medium text-white/75 mb-2">What will happen:</div>
            <ol className="list-decimal list-inside space-y-1">
              <li>Stop libvirtd service</li>
              {moveData && <li>Move existing images to <code className="text-cyan-400">{targetDir || '/data/libvirt/images'}</code></li>}
              <li>Create symlink: <code className="text-cyan-400">/var/lib/libvirt/images</code> → <code className="text-cyan-400">{targetDir || '/data/libvirt/images'}</code></li>
              <li>Apply SELinux context (<code className="text-cyan-400">virt_image_t</code>)</li>
              <li>Set ownership to <code className="text-cyan-400">qemu:qemu</code></li>
              <li>Start libvirtd service</li>
            </ol>
          </div>

          {relocate.isSuccess && (
            <div className="mt-3 bg-green-500/10 border border-green-500/20 rounded-lg p-3 text-xs text-green-400">
              <CheckCircle className="h-4 w-4 inline mr-1.5" />
              {relocate.data?.message}
              {relocate.data?.steps && (
                <ul className="mt-2 space-y-0.5 text-green-300/70">
                  {relocate.data.steps.map((s, i) => <li key={i}>- {s}</li>)}
                </ul>
              )}
            </div>
          )}

          {relocate.error && (
            <div className="mt-3 bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-xs text-red-400">
              <AlertCircle className="h-4 w-4 inline mr-1.5" />
              {(relocate.error as Error).message}
            </div>
          )}

          <div className="flex gap-3 mt-4">
            <button
              onClick={() => relocate.mutate({ target_dir: targetDir, move_data: moveData })}
              disabled={!targetDir || relocate.isPending}
              className="flex items-center gap-2 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white font-medium rounded-lg py-2.5 px-5 transition-all hover:scale-[1.02] text-sm disabled:opacity-50 disabled:hover:scale-100"
            >
              {relocate.isPending ? <><Loader2 className="h-4 w-4 animate-spin" /> Relocating...</> : <><FolderOpen className="h-4 w-4" /> Relocate Storage</>}
            </button>
            <button
              onClick={() => setShowRelocate(false)}
              className="px-4 py-2.5 rounded-lg border border-white/[0.12] text-white/75 hover:bg-white/[0.04] transition-colors text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

interface UserInfo {
  name: string;
  uid: string;
  groups: string[];
  shell: string;
  sudo: boolean;
  home: string;
}

function UserSection() {
  const queryClient = useQueryClient();
  const { data: users, isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: () => fetchAPI<UserInfo[]>('/users'),
  });
  const [showCreate, setShowCreate] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [sudo, setSudo] = useState(true);

  const createUser = useMutation({
    mutationFn: (params: { username: string; password: string; sudo: boolean }) =>
      fetchAPI<{ username: string; message: string; steps: string[] }>('/users', {
        method: 'POST',
        body: JSON.stringify(params),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      setShowCreate(false);
      setUsername('');
      setPassword('');
    },
  });

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-purple-400" />
          <h3 className="text-sm font-semibold text-white">Migration Operators</h3>
        </div>
        {!showCreate && (
          <button onClick={() => setShowCreate(true)}
            className="flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 transition-colors">
            <UserPlus className="h-3.5 w-3.5" /> Add User
          </button>
        )}
      </div>

      <p className="text-xs text-white/55 mb-4">
        Users who can login to h2kweb and run VM migrations. Sudo access grants passwordless h2kvmctl, virsh, qemu-img.
      </p>

      {/* User list */}
      {isLoading ? (
        <div className="skeleton h-20 rounded-lg" />
      ) : (
        <div className="space-y-2">
          {users?.map((user) => (
            <div key={user.name} className="flex items-center gap-3 p-3 tahoe-glass-card rounded-lg border border-white/[0.06]">
              <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold ${
                user.name === 'root' ? 'bg-red-500/10 text-red-400' : 'bg-blue-500/10 text-blue-400'
              }`}>
                {user.name[0].toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-white">{user.name}</span>
                  {user.name === 'root' && <span className="text-[10px] px-1.5 py-0.5 bg-red-500/10 text-red-400 border border-red-500/30 rounded-full">root</span>}
                  {user.sudo && <span className="text-[10px] px-1.5 py-0.5 bg-green-500/10 text-green-400 border border-green-500/30 rounded-full flex items-center gap-0.5"><ShieldCheck className="h-2.5 w-2.5" />sudo</span>}
                </div>
                <div className="text-[10px] text-white/45 mt-0.5">
                  UID {user.uid} · {user.shell} · {user.groups?.join(', ') || 'no groups'}
                </div>
              </div>
            </div>
          ))}
          {(!users || users.length === 0) && (
            <div className="text-center py-4 text-xs text-white/45">No users found</div>
          )}
        </div>
      )}

      {/* Create user form */}
      {showCreate && (
        <div className="mt-4 pt-4 border-t border-white/[0.06] animate-fade-in">
          <h4 className="text-sm font-semibold text-white mb-3">Create Migration Operator</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-white/55 mb-1.5">Username</label>
              <input type="text" value={username} onChange={(e) => setUsername(e.target.value.toLowerCase())}
                placeholder="operator1"
                className="w-full px-3 py-2.5 tahoe-glass-card border border-white/[0.12] rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-white/55 mb-1.5">Password</label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                placeholder="Strong password"
                className="w-full px-3 py-2.5 tahoe-glass-card border border-white/[0.12] rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-sm" />
            </div>
          </div>

          <label className="flex items-center gap-2 mt-3 cursor-pointer text-sm text-white/75">
            <input type="checkbox" checked={sudo} onChange={(e) => setSudo(e.target.checked)} className="accent-blue-500 h-4 w-4 rounded" />
            <Lock className="h-3.5 w-3.5 text-purple-400" />
            Grant sudo for h2kvmctl, virsh, qemu-img (passwordless)
          </label>

          <div className="mt-3 p-3 tahoe-glass-card rounded-lg border border-white/[0.06] text-xs text-white/55">
            <div className="font-medium text-white/75 mb-1">Will create:</div>
            <ul className="space-y-0.5">
              <li>· System user with /bin/bash shell</li>
              <li>· Groups: h2kweb, libvirt, kvm, qemu</li>
              {sudo && <li>· Sudoers: NOPASSWD for h2kvmctl, virsh, qemu-img, mount</li>}
              <li>· Can login to h2kweb dashboard via PAM</li>
            </ul>
          </div>

          {createUser.isSuccess && (
            <div className="mt-3 bg-green-500/10 border border-green-500/20 rounded-lg p-3 text-xs text-green-400">
              <CheckCircle className="h-4 w-4 inline mr-1.5" />
              {createUser.data?.message}
            </div>
          )}
          {createUser.error && (
            <div className="mt-3 bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-xs text-red-400">
              <AlertCircle className="h-4 w-4 inline mr-1.5" />
              {(createUser.error as Error).message}
            </div>
          )}

          <div className="flex gap-3 mt-4">
            <button
              onClick={() => createUser.mutate({ username, password, sudo })}
              disabled={!username || !password || createUser.isPending}
              className="flex items-center gap-2 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white font-medium rounded-lg py-2.5 px-5 transition-all hover:scale-[1.02] text-sm disabled:opacity-50 disabled:hover:scale-100">
              {createUser.isPending ? <><Loader2 className="h-4 w-4 animate-spin" /> Creating...</> : <><UserPlus className="h-4 w-4" /> Create User</>}
            </button>
            <button onClick={() => setShowCreate(false)}
              className="px-4 py-2.5 rounded-lg border border-white/[0.12] text-white/75 hover:bg-white/[0.04] transition-colors text-sm">
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

interface EmailConfigData {
  host: string;
  port: number;
  from: string;
  username: string;
  password: string;
  to_addresses: string[];
}

function EmailSection() {
  const queryClient = useQueryClient();
  const { data: emailData, isLoading } = useQuery({
    queryKey: ['email-config'],
    queryFn: () => fetchAPI<{ configured: boolean; config?: EmailConfigData }>('/notifications/email/config'),
  });

  const [host, setHost] = useState('');
  const [port, setPort] = useState('587');
  const [from, setFrom] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [toAddresses, setToAddresses] = useState('');
  const [initialized, setInitialized] = useState(false);

  // Populate form when data loads.
  if (emailData?.config && !initialized) {
    setHost(emailData.config.host || '');
    setPort(String(emailData.config.port || 587));
    setFrom(emailData.config.from || '');
    setUsername(emailData.config.username || '');
    setPassword(emailData.config.password || '');
    setToAddresses((emailData.config.to_addresses || []).join(', '));
    setInitialized(true);
  }

  const saveConfig = useMutation({
    mutationFn: (cfg: EmailConfigData) =>
      fetchAPI<{ message: string }>('/notifications/email/config', {
        method: 'POST',
        body: JSON.stringify(cfg),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['email-config'] }),
  });

  const testEmail = useMutation({
    mutationFn: () => fetchAPI<{ success: boolean; message?: string; error?: string }>('/notifications/email/test', { method: 'POST' }),
  });

  const buildConfig = (): EmailConfigData => ({
    host,
    port: parseInt(port) || 587,
    from,
    username,
    password,
    to_addresses: toAddresses.split(',').map((s) => s.trim()).filter(Boolean),
  });

  if (isLoading) {
    return (
      <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
        <div className="skeleton h-32 rounded-lg" />
      </div>
    );
  }

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Mail className="h-4 w-4 text-blue-400" />
          <h3 className="text-sm font-semibold text-white">Email Notifications</h3>
        </div>
        {emailData?.configured && (
          <span className="text-[10px] px-1.5 py-0.5 bg-green-500/10 text-green-400 border border-green-500/30 rounded-full">Configured</span>
        )}
      </div>

      <p className="text-xs text-white/55 mb-4">
        Receive email notifications when migration jobs complete or fail.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-white/55 mb-1.5">SMTP Host</label>
          <input type="text" value={host} onChange={(e) => setHost(e.target.value)} placeholder="smtp.example.com"
            className="w-full px-3 py-2.5 tahoe-glass-card border border-white/[0.12] rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-sm" />
        </div>
        <div>
          <label className="block text-xs font-medium text-white/55 mb-1.5">Port</label>
          <input type="text" value={port} onChange={(e) => setPort(e.target.value)} placeholder="587"
            className="w-full px-3 py-2.5 tahoe-glass-card border border-white/[0.12] rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-sm" />
        </div>
        <div>
          <label className="block text-xs font-medium text-white/55 mb-1.5">From Address</label>
          <input type="text" value={from} onChange={(e) => setFrom(e.target.value)} placeholder="noreply@example.com"
            className="w-full px-3 py-2.5 tahoe-glass-card border border-white/[0.12] rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-sm" />
        </div>
        <div>
          <label className="block text-xs font-medium text-white/55 mb-1.5">Username</label>
          <input type="text" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="smtp-user"
            className="w-full px-3 py-2.5 tahoe-glass-card border border-white/[0.12] rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-sm" />
        </div>
        <div>
          <label className="block text-xs font-medium text-white/55 mb-1.5">Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="SMTP password"
            className="w-full px-3 py-2.5 tahoe-glass-card border border-white/[0.12] rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-sm" />
        </div>
        <div>
          <label className="block text-xs font-medium text-white/55 mb-1.5">To Addresses (comma-separated)</label>
          <input type="text" value={toAddresses} onChange={(e) => setToAddresses(e.target.value)} placeholder="admin@example.com, ops@example.com"
            className="w-full px-3 py-2.5 tahoe-glass-card border border-white/[0.12] rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-sm" />
        </div>
      </div>

      {saveConfig.isSuccess && (
        <div className="mt-3 bg-green-500/10 border border-green-500/20 rounded-lg p-3 text-xs text-green-400">
          <CheckCircle className="h-4 w-4 inline mr-1.5" /> Email configuration saved.
        </div>
      )}
      {saveConfig.error && (
        <div className="mt-3 bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-xs text-red-400">
          <AlertCircle className="h-4 w-4 inline mr-1.5" /> {(saveConfig.error as Error).message}
        </div>
      )}
      {testEmail.isSuccess && (
        <div className={`mt-3 ${testEmail.data?.success ? 'bg-green-500/10 border-green-500/20 text-green-400' : 'bg-red-500/10 border-red-500/20 text-red-400'} border rounded-lg p-3 text-xs`}>
          {testEmail.data?.success ? (
            <><CheckCircle className="h-4 w-4 inline mr-1.5" /> {testEmail.data.message}</>
          ) : (
            <><AlertCircle className="h-4 w-4 inline mr-1.5" /> {testEmail.data?.error}</>
          )}
        </div>
      )}

      <div className="flex gap-3 mt-4">
        <button
          onClick={() => saveConfig.mutate(buildConfig())}
          disabled={!host || !from || !toAddresses || saveConfig.isPending}
          className="flex items-center gap-2 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white font-medium rounded-lg py-2.5 px-5 transition-all hover:scale-[1.02] text-sm disabled:opacity-50 disabled:hover:scale-100"
        >
          {saveConfig.isPending ? <><Loader2 className="h-4 w-4 animate-spin" /> Saving...</> : 'Save'}
        </button>
        <button
          onClick={() => testEmail.mutate()}
          disabled={!emailData?.configured || testEmail.isPending}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-white/[0.12] text-white/75 hover:bg-white/[0.04] transition-colors text-sm disabled:opacity-50"
        >
          {testEmail.isPending ? <><Loader2 className="h-4 w-4 animate-spin" /> Sending...</> : <><Send className="h-3.5 w-3.5" /> Send Test Email</>}
        </button>
      </div>
    </div>
  );
}

function ConfigBackupSection() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importPreview, setImportPreview] = useState<string | null>(null);
  const [importData, setImportData] = useState<string | null>(null);

  const importConfig = useMutation({
    mutationFn: (data: string) =>
      fetchAPI<{ message: string; applied: string[] }>('/config/import', {
        method: 'POST',
        body: data,
      }),
    onSuccess: () => {
      setImportPreview(null);
      setImportData(null);
    },
  });

  const handleExport = async () => {
    try {
      const res = await fetch('/api/v1/config/export', { credentials: 'include' });
      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'h2kvm-config.json';
      a.click();
      URL.revokeObjectURL(a.href);
    } catch {
      // Ignore errors silently.
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      setImportData(text);
      try {
        const parsed = JSON.parse(text);
        const keys = Object.keys(parsed).filter((k) => k !== 'exported_at');
        setImportPreview(`Found: ${keys.join(', ')} (exported ${parsed.exported_at || 'unknown'})`);
      } catch {
        setImportPreview('Invalid JSON file');
        setImportData(null);
      }
    };
    reader.readAsText(file);
    // Reset file input so same file can be selected again.
    e.target.value = '';
  };

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
      <div className="flex items-center gap-2 mb-4">
        <Settings className="h-4 w-4 text-green-400" />
        <h3 className="text-sm font-semibold text-white">Backup / Restore Config</h3>
      </div>

      <p className="text-xs text-white/55 mb-4">
        Export or import webhooks and email configuration as a JSON file.
      </p>

      <div className="flex gap-3">
        <button
          onClick={handleExport}
          className="flex items-center gap-2 px-4 py-2.5 bg-green-500/10 text-green-400 rounded-lg text-sm font-medium hover:bg-green-500/20 transition-colors"
        >
          <Download className="h-4 w-4" /> Export Config
        </button>
        <button
          onClick={() => fileInputRef.current?.click()}
          className="flex items-center gap-2 px-4 py-2.5 bg-blue-500/10 text-blue-400 rounded-lg text-sm font-medium hover:bg-blue-500/20 transition-colors"
        >
          <Upload className="h-4 w-4" /> Import Config
        </button>
        <input ref={fileInputRef} type="file" accept=".json" className="hidden" onChange={handleFileSelect} />
      </div>

      {importPreview && (
        <div className="mt-4 pt-4 border-t border-white/[0.06] animate-fade-in">
          <div className="text-xs text-white/75 mb-3">{importPreview}</div>
          {importConfig.isSuccess && (
            <div className="mb-3 bg-green-500/10 border border-green-500/20 rounded-lg p-3 text-xs text-green-400">
              <CheckCircle className="h-4 w-4 inline mr-1.5" /> {importConfig.data?.message}
              {importConfig.data?.applied && (
                <ul className="mt-1 text-green-300/70">{importConfig.data.applied.map((s, i) => <li key={i}>- {s}</li>)}</ul>
              )}
            </div>
          )}
          {importConfig.error && (
            <div className="mb-3 bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-xs text-red-400">
              <AlertCircle className="h-4 w-4 inline mr-1.5" /> {(importConfig.error as Error).message}
            </div>
          )}
          <div className="flex gap-3">
            <button
              onClick={() => importData && importConfig.mutate(importData)}
              disabled={!importData || importConfig.isPending}
              className="flex items-center gap-2 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white font-medium rounded-lg py-2.5 px-5 transition-all hover:scale-[1.02] text-sm disabled:opacity-50 disabled:hover:scale-100"
            >
              {importConfig.isPending ? <><Loader2 className="h-4 w-4 animate-spin" /> Importing...</> : 'Confirm Import'}
            </button>
            <button
              onClick={() => { setImportPreview(null); setImportData(null); }}
              className="px-4 py-2.5 rounded-lg border border-white/[0.12] text-white/75 hover:bg-white/[0.04] transition-colors text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

interface ArtifactData {
  artifacts: { name: string; path: string; size_bytes: number; modified: string; dir: string }[];
  total_bytes: number;
  total_human: string;
}

function StorageCleanupSection() {
  const queryClient = useQueryClient();
  const { data: artifactData, isLoading } = useQuery({
    queryKey: ['storage-artifacts'],
    queryFn: () => fetchAPI<ArtifactData>('/storage/artifacts'),
    refetchInterval: 30000,
  });

  const [olderThanHours, setOlderThanHours] = useState('0');
  const [selectedDirs, setSelectedDirs] = useState<string[]>(['output', 'input']);
  const [showConfirm, setShowConfirm] = useState(false);

  const cleanup = useMutation({
    mutationFn: (params: { dirs: string[]; older_than_hours: number }) =>
      fetchAPI<{ deleted: number; freed_bytes: number; freed_human: string }>('/storage/cleanup', {
        method: 'POST',
        body: JSON.stringify(params),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['storage-artifacts'] });
      setShowConfirm(false);
    },
  });

  const toggleDir = (dir: string) => {
    setSelectedDirs((prev) =>
      prev.includes(dir) ? prev.filter((d) => d !== dir) : [...prev, dir]
    );
  };

  const outputArtifacts = artifactData?.artifacts?.filter((a) => a.dir === 'output') || [];
  const inputArtifacts = artifactData?.artifacts?.filter((a) => a.dir === 'input') || [];
  const outputSize = outputArtifacts.reduce((sum, a) => sum + a.size_bytes, 0);
  const inputSize = inputArtifacts.reduce((sum, a) => sum + a.size_bytes, 0);

  if (isLoading) {
    return (
      <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
        <div className="skeleton h-32 rounded-lg" />
      </div>
    );
  }

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Trash2 className="h-4 w-4 text-red-400" />
          <h3 className="text-sm font-semibold text-white">Storage Cleanup</h3>
        </div>
        <span className="text-xs px-2 py-0.5 bg-white/[0.08]/50 text-white/75 rounded-full">
          {artifactData?.total_human || '0 KB'} total
        </span>
      </div>

      <p className="text-xs text-white/55 mb-4">
        Clean up conversion output files and uploaded input images to free disk space.
      </p>

      {/* Dir breakdown */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
        <div className="p-3 tahoe-glass-card rounded-lg border border-white/[0.06]">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-white/55">Output (qcow2, xml, yaml)</span>
            <span className="text-xs font-mono text-white/75">{formatBytes(outputSize)}</span>
          </div>
          <div className="text-xs text-white/45">{outputArtifacts.length} files in /var/lib/h2kvm/output/</div>
        </div>
        <div className="p-3 tahoe-glass-card rounded-lg border border-white/[0.06]">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-white/55">Input (uploaded images)</span>
            <span className="text-xs font-mono text-white/75">{formatBytes(inputSize)}</span>
          </div>
          <div className="text-xs text-white/45">{inputArtifacts.length} files in /var/lib/h2kvm/input/</div>
        </div>
      </div>

      {/* File list */}
      {artifactData?.artifacts && artifactData.artifacts.length > 0 && (
        <div className="mb-4">
          <div className="text-xs text-white/45 mb-2">Files ({artifactData.artifacts.length})</div>
          <div className="max-h-40 overflow-y-auto space-y-1">
            {artifactData.artifacts.map((a) => (
              <div key={a.path} className="flex items-center justify-between text-xs px-2.5 py-1.5 tahoe-glass-card rounded-lg">
                <span className="text-white/75 font-mono truncate flex-1 mr-2">{a.name}</span>
                <span className="text-white/45 flex-shrink-0">{formatBytes(a.size_bytes)}</span>
                <span className={`ml-2 px-1.5 py-0.5 rounded text-[10px] flex-shrink-0 ${a.dir === 'output' ? 'bg-blue-500/10 text-blue-400' : 'bg-green-500/10 text-green-400'}`}>{a.dir}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Cleanup controls */}
      <div className="space-y-3">
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 cursor-pointer text-sm text-white/75">
            <input type="checkbox" checked={selectedDirs.includes('output')} onChange={() => toggleDir('output')} className="accent-blue-500 h-4 w-4 rounded" />
            Output files
          </label>
          <label className="flex items-center gap-2 cursor-pointer text-sm text-white/75">
            <input type="checkbox" checked={selectedDirs.includes('input')} onChange={() => toggleDir('input')} className="accent-blue-500 h-4 w-4 rounded" />
            Input files
          </label>
        </div>

        <div className="flex items-center gap-3">
          <Clock className="h-3.5 w-3.5 text-white/55" />
          <label className="text-xs text-white/55">Only files older than</label>
          <input
            type="number"
            min="0"
            value={olderThanHours}
            onChange={(e) => setOlderThanHours(e.target.value)}
            className="w-20 px-2 py-1.5 tahoe-glass-card border border-white/[0.12] rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <span className="text-xs text-white/55">hours (0 = all files)</span>
        </div>
      </div>

      {/* Result feedback */}
      {cleanup.isSuccess && (
        <div className="mt-3 bg-green-500/10 border border-green-500/20 rounded-lg p-3 text-xs text-green-400">
          <CheckCircle className="h-4 w-4 inline mr-1.5" />
          Deleted {cleanup.data?.deleted} files, freed {cleanup.data?.freed_human}
        </div>
      )}
      {cleanup.error && (
        <div className="mt-3 bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-xs text-red-400">
          <AlertCircle className="h-4 w-4 inline mr-1.5" />
          {(cleanup.error as Error).message}
        </div>
      )}

      {/* Confirm dialog */}
      {showConfirm && (
        <div className="mt-3 bg-red-500/5 border border-red-500/20 rounded-lg p-4 animate-fade-in">
          <div className="text-sm font-medium text-red-400 mb-2">Confirm Cleanup</div>
          <p className="text-xs text-white/55 mb-3">
            This will permanently delete {olderThanHours === '0' ? 'all' : `files older than ${olderThanHours}h in`} files from: {selectedDirs.join(', ')}. This cannot be undone.
          </p>
          <div className="flex gap-3">
            <button
              onClick={() => cleanup.mutate({ dirs: selectedDirs, older_than_hours: parseInt(olderThanHours) || 0 })}
              disabled={cleanup.isPending}
              className="flex items-center gap-2 bg-gradient-to-r from-red-600 to-red-700 hover:from-red-500 hover:to-red-600 text-white font-medium rounded-lg py-2 px-4 transition-all text-sm disabled:opacity-50"
            >
              {cleanup.isPending ? <><Loader2 className="h-4 w-4 animate-spin" /> Deleting...</> : <><Trash2 className="h-4 w-4" /> Delete Files</>}
            </button>
            <button
              onClick={() => setShowConfirm(false)}
              className="px-4 py-2 rounded-lg border border-white/[0.12] text-white/75 hover:bg-white/[0.04] transition-colors text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {!showConfirm && (
        <div className="mt-4">
          <button
            onClick={() => setShowConfirm(true)}
            disabled={selectedDirs.length === 0 || !artifactData?.artifacts?.length}
            className="flex items-center gap-2 bg-gradient-to-r from-red-600 to-red-700 hover:from-red-500 hover:to-red-600 text-white font-medium rounded-lg py-2.5 px-5 transition-all hover:scale-[1.02] text-sm disabled:opacity-50 disabled:hover:scale-100"
          >
            <Trash2 className="h-4 w-4" /> Clean Up Storage
          </button>
        </div>
      )}
    </div>
  );
}

interface CleanupSettings {
  enabled: boolean;
  threshold_percent: number;
  max_age_hours: number;
  dirs: string[];
  last_cleanup: string;
  last_result: string;
  disk_usage_percent: number;
}

function AutoCleanupSection() {
  const queryClient = useQueryClient();
  const { data: settings, isLoading } = useQuery({
    queryKey: ['cleanup-settings'],
    queryFn: () => fetchAPI<CleanupSettings>('/settings/cleanup'),
    refetchInterval: 30000,
  });

  const [enabled, setEnabled] = useState(true);
  const [threshold, setThreshold] = useState(85);
  const [maxAge, setMaxAge] = useState(24);
  const [initialized, setInitialized] = useState(false);

  if (settings && !initialized) {
    setEnabled(settings.enabled);
    setThreshold(settings.threshold_percent);
    setMaxAge(settings.max_age_hours);
    setInitialized(true);
  }

  const updateSettings = useMutation({
    mutationFn: (params: { enabled?: boolean; threshold_percent?: number; max_age_hours?: number; run_now?: boolean }) =>
      fetchAPI<{ message: string }>('/settings/cleanup', {
        method: 'POST',
        body: JSON.stringify(params),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['cleanup-settings'] }),
  });

  const handleSave = () => {
    updateSettings.mutate({ enabled, threshold_percent: threshold, max_age_hours: maxAge });
  };

  const handleRunNow = () => {
    updateSettings.mutate({ run_now: true });
  };

  const diskPct = settings?.disk_usage_percent ?? 0;
  const diskColor = diskPct > 90 ? 'bg-red-500' : diskPct > 75 ? 'bg-yellow-500' : 'bg-blue-500';
  const diskTextColor = diskPct > 90 ? 'text-red-400' : diskPct > 75 ? 'text-yellow-400' : 'text-white/75';

  if (isLoading) {
    return (
      <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
        <div className="skeleton h-40 rounded-lg" />
      </div>
    );
  }

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Zap className="h-4 w-4 text-amber-400" />
          <h3 className="text-sm font-semibold text-white">Auto Cleanup</h3>
        </div>
        <button
          onClick={() => {
            const next = !enabled;
            setEnabled(next);
            updateSettings.mutate({ enabled: next });
          }}
          className="flex items-center gap-1.5 text-xs transition-colors"
        >
          {enabled ? (
            <><ToggleRight className="h-5 w-5 text-green-400" /><span className="text-green-400">Enabled</span></>
          ) : (
            <><ToggleLeft className="h-5 w-5 text-white/45" /><span className="text-white/45">Disabled</span></>
          )}
        </button>
      </div>

      <p className="text-xs text-white/55 mb-4">
        Automatically clean up old conversion artifacts when disk usage exceeds a threshold.
        Runs every 10 minutes in the background.
      </p>

      {/* Disk usage bar */}
      <div className="p-4 tahoe-glass-card rounded-lg border border-white/[0.06] mb-4">
        <div className="flex justify-between text-xs mb-1">
          <span className="text-white/45">Current Disk Usage</span>
          <span className={`font-medium ${diskTextColor}`}>{diskPct.toFixed(1)}%</span>
        </div>
        <div className="h-2 bg-white/[0.08] rounded-full overflow-hidden mb-2">
          <div className={`h-full rounded-full ${diskColor} transition-all duration-500`} style={{ width: `${Math.min(diskPct, 100)}%` }} />
        </div>
        {settings?.last_cleanup && (
          <div className="flex items-center gap-2 text-[10px] text-white/45 mt-2">
            <Clock className="h-3 w-3" />
            Last cleanup: {new Date(settings.last_cleanup).toLocaleString()}
            {settings.last_result && <span className="text-white/55">({settings.last_result})</span>}
          </div>
        )}
      </div>

      {/* Settings */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div>
          <label className="block text-xs font-medium text-white/55 mb-1.5">Threshold (%)</label>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min="50"
              max="95"
              value={threshold}
              onChange={(e) => setThreshold(parseInt(e.target.value))}
              className="flex-1 accent-blue-500"
            />
            <span className="text-sm font-mono text-white w-10 text-right">{threshold}%</span>
          </div>
          <div className="text-[10px] text-white/45 mt-1">Clean when disk exceeds this usage</div>
        </div>
        <div>
          <label className="block text-xs font-medium text-white/55 mb-1.5">Max Age (hours)</label>
          <input
            type="number"
            min="0"
            value={maxAge}
            onChange={(e) => setMaxAge(parseInt(e.target.value) || 0)}
            className="w-full px-3 py-2.5 tahoe-glass-card border border-white/[0.12] rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
          />
          <div className="text-[10px] text-white/45 mt-1">Only delete files older than this</div>
        </div>
      </div>

      {/* Feedback */}
      {updateSettings.isSuccess && (
        <div className="mb-3 bg-green-500/10 border border-green-500/20 rounded-lg p-3 text-xs text-green-400">
          <CheckCircle className="h-4 w-4 inline mr-1.5" /> {updateSettings.data?.message || 'Settings saved'}
        </div>
      )}
      {updateSettings.error && (
        <div className="mb-3 bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-xs text-red-400">
          <AlertCircle className="h-4 w-4 inline mr-1.5" /> {(updateSettings.error as Error).message}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-3">
        <button
          onClick={handleSave}
          disabled={updateSettings.isPending}
          className="flex items-center gap-2 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white font-medium rounded-lg py-2.5 px-5 transition-all hover:scale-[1.02] text-sm disabled:opacity-50 disabled:hover:scale-100"
        >
          {updateSettings.isPending ? <><Loader2 className="h-4 w-4 animate-spin" /> Saving...</> : 'Save Settings'}
        </button>
        <button
          onClick={handleRunNow}
          disabled={updateSettings.isPending}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-white/[0.12] text-white/75 hover:bg-white/[0.04] transition-colors text-sm disabled:opacity-50"
        >
          <Zap className="h-3.5 w-3.5" /> Run Now
        </button>
      </div>
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}
