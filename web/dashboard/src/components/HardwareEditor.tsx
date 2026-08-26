// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useState, useEffect, useCallback } from 'react';
import {
  Cpu, MemoryStick, HardDrive, Network, Disc, Shield, PlayCircle,
  ChevronDown, ChevronRight, Loader2, Plus, Trash2, Save, X, Edit2,
  AlertCircle, Zap, RefreshCw,
} from 'lucide-react';
import { fetchAPI } from '../api/client';
import { showToast } from './Toast';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface HardwareEditorProps {
  vmName: string;
  vmState: string;
  onRefresh?: () => void;
}

interface HardwareData {
  cpu?: { vcpus: number; mode?: string; sockets?: number; cores?: number; threads?: number };
  memory?: { memory_mb: number; max_memory_mb?: number };
  disks?: { target: string; bus: string; format: string; source: string }[];
  interfaces?: { mac: string; network: string; model: string }[];
  cdrom?: { path: string; target?: string };
  tpm?: { model?: string; version?: string };
  boot?: { order: string[]; firmware?: string };
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

const hw = {
  get: (vm: string) => fetchAPI<HardwareData>(`/vms/${vm}/hardware`),
  setCPU: (vm: string, data: { vcpus: number; sockets?: number; cores?: number; threads?: number }) =>
    fetchAPI<{ message: string }>(`/vms/${vm}/cpu`, { method: 'PUT', body: JSON.stringify(data) }),
  setMemory: (vm: string, data: { memory_mb: number; max_memory_mb?: number }) =>
    fetchAPI<{ message: string }>(`/vms/${vm}/memory`, { method: 'PUT', body: JSON.stringify(data) }),
  addDisk: (vm: string, data: { size_gb: number; format: string; bus: string; cache?: string }) =>
    fetchAPI<{ message: string }>(`/vms/${vm}/disks`, { method: 'POST', body: JSON.stringify(data) }),
  removeDisk: (vm: string, target: string) =>
    fetchAPI<{ message: string }>(`/vms/${vm}/disks/${target}`, { method: 'DELETE' }),
  addInterface: (vm: string, data: { network: string; model: string; mac?: string }) =>
    fetchAPI<{ message: string }>(`/vms/${vm}/interfaces`, { method: 'POST', body: JSON.stringify(data) }),
  removeInterface: (vm: string, mac: string) =>
    fetchAPI<{ message: string }>(`/vms/${vm}/interfaces/${encodeURIComponent(mac)}`, { method: 'DELETE' }),
  setCDROM: (vm: string, data: { path?: string; eject?: boolean }) =>
    fetchAPI<{ message: string }>(`/vms/${vm}/cdrom`, { method: 'PUT', body: JSON.stringify(data) }),
  addTPM: (vm: string, data: { model?: string; version?: string }) =>
    fetchAPI<{ message: string }>(`/vms/${vm}/tpm`, { method: 'POST', body: JSON.stringify(data) }),
  setBoot: (vm: string, data: { order: string[]; firmware?: string }) =>
    fetchAPI<{ message: string }>(`/vms/${vm}/boot`, { method: 'PUT', body: JSON.stringify(data) }),
};

// ---------------------------------------------------------------------------
// Shared small components
// ---------------------------------------------------------------------------

function SectionHeader({
  icon: Icon,
  color,
  title,
  badge,
  open,
  onToggle,
}: {
  icon: React.ElementType;
  color: string;
  title: string;
  badge?: string;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      aria-label={`${open ? 'Collapse' : 'Expand'} ${title} section`}
      className="w-full flex items-center gap-2 py-2 text-left group"
    >
      {open ? (
        <ChevronDown className="h-3.5 w-3.5 text-white/45 group-hover:text-white/75 transition-colors" />
      ) : (
        <ChevronRight className="h-3.5 w-3.5 text-white/45 group-hover:text-white/75 transition-colors" />
      )}
      <Icon className={`h-4 w-4 ${color}`} />
      <span className="text-sm font-medium text-white">{title}</span>
      {badge && (
        <span className={`ml-auto text-[10px] font-medium px-1.5 py-0.5 rounded-full ${
          badge === 'Live'
            ? 'bg-green-500/10 text-green-400 border border-green-500/30'
            : 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/30'
        }`}>
          {badge}
        </span>
      )}
    </button>
  );
}

function InlineInput({
  label,
  type = 'number',
  value,
  onChange,
  className = '',
  min,
  max,
  step,
  placeholder,
}: {
  label: string;
  type?: string;
  value: string | number;
  onChange: (v: string) => void;
  className?: string;
  min?: number;
  max?: number;
  step?: number;
  placeholder?: string;
}) {
  return (
    <div className={className}>
      <label className="block text-[10px] text-white/45 mb-0.5">{label}</label>
      <input
        type={type}
        min={min}
        max={max}
        step={step}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-2 py-1.5 tahoe-glass-card border border-white/15 rounded text-xs text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
      />
    </div>
  );
}

function InlineSelect({
  label,
  value,
  onChange,
  options,
  className = '',
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  className?: string;
}) {
  return (
    <div className={className}>
      <label className="block text-[10px] text-white/45 mb-0.5">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-2 py-1.5 tahoe-glass-card border border-white/15 rounded text-xs text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CPU Section
// ---------------------------------------------------------------------------

function CPUSection({ data, vmName, onUpdated }: {
  data: HardwareData['cpu'];
  vmName: string;
  onUpdated: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ vcpus: 1, sockets: 1, cores: 1, threads: 1 });

  useEffect(() => {
    if (data) {
      setForm({
        vcpus: data.vcpus || 1,
        sockets: data.sockets || 1,
        cores: data.cores || 1,
        threads: data.threads || 1,
      });
    }
  }, [data]);

  const handleSave = async () => {
    if (form.vcpus < 1 || form.vcpus > 512) {
      showToast('error', 'vCPUs must be between 1 and 512');
      return;
    }
    setLoading(true);
    try {
      const res = await hw.setCPU(vmName, form);
      showToast('success', res.message || 'CPU updated');
      setEditing(false);
      onUpdated();
    } catch (err) {
      showToast('error', (err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      {editing ? (
        <div className="p-3 bg-white/[0.04] rounded-lg border border-white/[0.06] space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <InlineInput label="vCPUs" value={form.vcpus} min={1} max={256} onChange={(v) => setForm({ ...form, vcpus: parseInt(v) || 1 })} />
            <InlineInput label="Sockets" value={form.sockets} min={1} max={16} onChange={(v) => setForm({ ...form, sockets: parseInt(v) || 1 })} />
            <InlineInput label="Cores" value={form.cores} min={1} max={128} onChange={(v) => setForm({ ...form, cores: parseInt(v) || 1 })} />
            <InlineInput label="Threads" value={form.threads} min={1} max={4} onChange={(v) => setForm({ ...form, threads: parseInt(v) || 1 })} />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <button onClick={() => setEditing(false)} className="px-2.5 py-1 text-xs text-white/55 hover:text-white transition-colors">Cancel</button>
            <button onClick={handleSave} disabled={loading}
              className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs transition-colors disabled:opacity-50">
              {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />} Save
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between p-2 bg-white/[0.03] rounded-lg">
            <span className="text-xs text-white/55">vCPUs</span>
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-white/75 font-medium">{data?.vcpus ?? '-'}</span>
              <button onClick={() => setEditing(true)}
                aria-label="Edit CPU"
                className="h-5 w-5 rounded hover:bg-blue-500/10 text-white/45 hover:text-blue-400 flex items-center justify-center transition-colors">
                <Edit2 className="h-3 w-3" />
              </button>
            </div>
          </div>
          {data?.mode && (
            <div className="flex items-center justify-between p-2 bg-white/[0.03] rounded-lg">
              <span className="text-xs text-white/55">Mode</span>
              <span className="text-xs text-white/75">{data.mode}</span>
            </div>
          )}
          <div className="flex items-center justify-between p-2 bg-white/[0.03] rounded-lg">
            <span className="text-xs text-white/55">Topology</span>
            <span className="text-xs text-white/75 font-mono">
              {data?.sockets ?? 1}S / {data?.cores ?? 1}C / {data?.threads ?? 1}T
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Memory Section
// ---------------------------------------------------------------------------

function MemorySection({ data, vmName, onUpdated }: {
  data: HardwareData['memory'];
  vmName: string;
  onUpdated: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ memory_mb: 1024, max_memory_mb: 1024 });

  useEffect(() => {
    if (data) {
      setForm({
        memory_mb: data.memory_mb || 1024,
        max_memory_mb: data.max_memory_mb || data.memory_mb || 1024,
      });
    }
  }, [data]);

  const handleSave = async () => {
    if (form.max_memory_mb > 0 && form.memory_mb > form.max_memory_mb) {
      showToast('error', 'Current memory cannot exceed max memory');
      return;
    }
    if (form.memory_mb < 128) {
      showToast('error', 'Minimum memory is 128 MB');
      return;
    }
    setLoading(true);
    try {
      const res = await hw.setMemory(vmName, form);
      showToast('success', res.message || 'Memory updated');
      setEditing(false);
      onUpdated();
    } catch (err) {
      showToast('error', (err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      {editing ? (
        <div className="p-3 bg-white/[0.04] rounded-lg border border-white/[0.06] space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <InlineInput label="Memory (MB)" value={form.memory_mb} min={128} step={128} onChange={(v) => setForm({ ...form, memory_mb: parseInt(v) || 1024 })} />
            <InlineInput label="Max Memory (MB)" value={form.max_memory_mb} min={128} step={128} onChange={(v) => setForm({ ...form, max_memory_mb: parseInt(v) || 1024 })} />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <button onClick={() => setEditing(false)} className="px-2.5 py-1 text-xs text-white/55 hover:text-white transition-colors">Cancel</button>
            <button onClick={handleSave} disabled={loading}
              className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs transition-colors disabled:opacity-50">
              {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />} Save
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between p-2 bg-white/[0.03] rounded-lg">
            <span className="text-xs text-white/55">Current</span>
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-white/75 font-medium">{data?.memory_mb ?? '-'} MB</span>
              <button onClick={() => setEditing(true)}
                aria-label="Edit Memory"
                className="h-5 w-5 rounded hover:bg-blue-500/10 text-white/45 hover:text-blue-400 flex items-center justify-center transition-colors">
                <Edit2 className="h-3 w-3" />
              </button>
            </div>
          </div>
          {data?.max_memory_mb && (
            <div className="flex items-center justify-between p-2 bg-white/[0.03] rounded-lg">
              <span className="text-xs text-white/55">Maximum</span>
              <span className="text-xs text-white/75">{data.max_memory_mb} MB</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Disks Section
// ---------------------------------------------------------------------------

function DisksSection({ data, vmName, onUpdated }: {
  data: HardwareData['disks'];
  vmName: string;
  onUpdated: () => void;
}) {
  const [showAdd, setShowAdd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);
  const [form, setForm] = useState({ size_gb: 10, format: 'qcow2', bus: 'virtio', cache: 'writeback' });

  const handleAdd = async () => {
    if (form.size_gb < 1 || form.size_gb > 10000) {
      showToast('error', 'Disk size must be between 1 and 10000 GB');
      return;
    }
    setLoading(true);
    try {
      const res = await hw.addDisk(vmName, form);
      showToast('success', res.message || 'Disk added');
      setShowAdd(false);
      onUpdated();
    } catch (err) {
      showToast('error', (err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleRemove = async (target: string) => {
    setLoading(true);
    try {
      const res = await hw.removeDisk(vmName, target);
      showToast('success', res.message || 'Disk removed');
      setConfirmRemove(null);
      onUpdated();
    } catch (err) {
      showToast('error', (err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const disks = data || [];

  return (
    <div>
      {/* Add button */}
      <div className="flex justify-end mb-2">
        <button onClick={() => setShowAdd(!showAdd)}
          className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors">
          <Plus className="h-3 w-3" /> Add Disk
        </button>
      </div>

      {/* Add form */}
      {showAdd && (
        <div className="mb-3 p-3 bg-white/[0.04] rounded-lg border border-white/[0.06] space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <InlineInput label="Size (GB)" value={form.size_gb} min={1} max={4096} onChange={(v) => setForm({ ...form, size_gb: parseInt(v) || 10 })} />
            <InlineSelect label="Format" value={form.format} onChange={(v) => setForm({ ...form, format: v })}
              options={[{ value: 'qcow2', label: 'qcow2' }, { value: 'raw', label: 'raw' }]} />
            <InlineSelect label="Bus" value={form.bus} onChange={(v) => setForm({ ...form, bus: v })}
              options={[{ value: 'virtio', label: 'virtio' }, { value: 'sata', label: 'sata' }, { value: 'ide', label: 'ide' }]} />
            <InlineSelect label="Cache" value={form.cache} onChange={(v) => setForm({ ...form, cache: v })}
              options={[{ value: 'writeback', label: 'writeback' }, { value: 'none', label: 'none' }, { value: 'writethrough', label: 'writethrough' }]} />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <button onClick={() => setShowAdd(false)} className="px-2.5 py-1 text-xs text-white/55 hover:text-white transition-colors">Cancel</button>
            <button onClick={handleAdd} disabled={loading}
              className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs transition-colors disabled:opacity-50">
              {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />} Add
            </button>
          </div>
        </div>
      )}

      {/* Disk list */}
      {disks.length > 0 ? (
        <div className="space-y-1.5">
          {disks.map((disk) => (
            <div key={disk.target} className="flex items-center gap-2 p-2 bg-white/[0.03] rounded-lg text-xs">
              <HardDrive className="h-3 w-3 text-yellow-400 flex-shrink-0" />
              <span className="text-white/75 font-mono w-8 flex-shrink-0">{disk.target}</span>
              <span className="text-white/45 text-[10px]">{disk.bus}</span>
              <span className="text-white/45 text-[10px]">{disk.format}</span>
              <span className="text-white/45 truncate flex-1 min-w-0 font-mono text-[10px]">{disk.source || '(empty)'}</span>
              {confirmRemove === disk.target ? (
                <div className="flex items-center gap-1 flex-shrink-0" onKeyDown={(e) => { if (e.key === 'Escape') setConfirmRemove(null); }}>
                  <button onClick={() => handleRemove(disk.target)} disabled={loading}
                    className="px-2 py-0.5 bg-red-600 text-white rounded text-[10px] hover:bg-red-500 transition-colors disabled:opacity-50">
                    {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Confirm'}
                  </button>
                  <button onClick={() => setConfirmRemove(null)}
                    className="h-5 w-5 rounded hover:bg-white/10 text-white/55 flex items-center justify-center transition-colors">
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ) : (
                <button onClick={() => setConfirmRemove(disk.target)}
                  aria-label={`Remove ${disk.target}`}
                  className="h-6 w-6 rounded hover:bg-red-500/10 text-white/55 hover:text-red-400 flex items-center justify-center transition-colors flex-shrink-0"
                  title="Remove disk">
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="text-xs text-white/45 text-center py-2">No disks configured</div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Network Section
// ---------------------------------------------------------------------------

function NetworkSection({ data, vmName, onUpdated }: {
  data: HardwareData['interfaces'];
  vmName: string;
  onUpdated: () => void;
}) {
  const [showAdd, setShowAdd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);
  const [form, setForm] = useState({ network: 'default', model: 'virtio', mac: '' });

  const handleAdd = async () => {
    setLoading(true);
    try {
      const payload: { network: string; model: string; mac?: string } = { network: form.network, model: form.model };
      if (form.mac.trim()) payload.mac = form.mac.trim();
      const res = await hw.addInterface(vmName, payload);
      showToast('success', res.message || 'Interface added');
      setShowAdd(false);
      setForm({ network: 'default', model: 'virtio', mac: '' });
      onUpdated();
    } catch (err) {
      showToast('error', (err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleRemove = async (mac: string) => {
    setLoading(true);
    try {
      const res = await hw.removeInterface(vmName, mac);
      showToast('success', res.message || 'Interface removed');
      setConfirmRemove(null);
      onUpdated();
    } catch (err) {
      showToast('error', (err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const ifaces = data || [];

  return (
    <div>
      <div className="flex justify-end mb-2">
        <button onClick={() => setShowAdd(!showAdd)}
          className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors">
          <Plus className="h-3 w-3" /> Add NIC
        </button>
      </div>

      {showAdd && (
        <div className="mb-3 p-3 bg-white/[0.04] rounded-lg border border-white/[0.06] space-y-2">
          <div className="grid grid-cols-3 gap-2">
            <InlineInput label="Network" type="text" value={form.network} placeholder="default" onChange={(v) => setForm({ ...form, network: v })} />
            <InlineSelect label="Model" value={form.model} onChange={(v) => setForm({ ...form, model: v })}
              options={[{ value: 'virtio', label: 'virtio' }, { value: 'e1000', label: 'e1000' }, { value: 'rtl8139', label: 'rtl8139' }]} />
            <InlineInput label="MAC (optional)" type="text" value={form.mac} onChange={(v) => setForm({ ...form, mac: v })} />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <button onClick={() => setShowAdd(false)} className="px-2.5 py-1 text-xs text-white/55 hover:text-white transition-colors">Cancel</button>
            <button onClick={handleAdd} disabled={loading}
              className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs transition-colors disabled:opacity-50">
              {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />} Add
            </button>
          </div>
        </div>
      )}

      {ifaces.length > 0 ? (
        <div className="space-y-1.5">
          {ifaces.map((nic) => (
            <div key={nic.mac} className="flex items-center gap-2 p-2 bg-white/[0.03] rounded-lg text-xs">
              <Network className="h-3 w-3 text-blue-400 flex-shrink-0" />
              <span className="text-white/75 font-mono text-[10px] flex-shrink-0">{nic.mac}</span>
              <span className="text-white/45 text-[10px]">{nic.network}</span>
              <span className="text-white/45 text-[10px] ml-auto">{nic.model}</span>
              {confirmRemove === nic.mac ? (
                <div className="flex items-center gap-1 flex-shrink-0" onKeyDown={(e) => { if (e.key === 'Escape') setConfirmRemove(null); }}>
                  <button onClick={() => handleRemove(nic.mac)} disabled={loading}
                    className="px-2 py-0.5 bg-red-600 text-white rounded text-[10px] hover:bg-red-500 transition-colors disabled:opacity-50">
                    {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Confirm'}
                  </button>
                  <button onClick={() => setConfirmRemove(null)}
                    className="h-5 w-5 rounded hover:bg-white/10 text-white/55 flex items-center justify-center transition-colors">
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ) : (
                <button onClick={() => setConfirmRemove(nic.mac)}
                  aria-label={`Remove ${nic.mac}`}
                  className="h-6 w-6 rounded hover:bg-red-500/10 text-white/55 hover:text-red-400 flex items-center justify-center transition-colors flex-shrink-0"
                  title="Remove NIC">
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="text-xs text-white/45 text-center py-2">No network interfaces</div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CDROM Section
// ---------------------------------------------------------------------------

function CDROMSection({ data, vmName, onUpdated }: {
  data: HardwareData['cdrom'];
  vmName: string;
  onUpdated: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [isoPath, setIsoPath] = useState('');

  const handleChange = async () => {
    setLoading(true);
    try {
      const res = await hw.setCDROM(vmName, { path: isoPath || undefined, eject: !isoPath });
      showToast('success', res.message || (isoPath ? 'ISO inserted' : 'CDROM ejected'));
      setEditing(false);
      setIsoPath('');
      onUpdated();
    } catch (err) {
      showToast('error', (err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleEject = async () => {
    setLoading(true);
    try {
      const res = await hw.setCDROM(vmName, { eject: true });
      showToast('success', res.message || 'CDROM ejected');
      onUpdated();
    } catch (err) {
      showToast('error', (err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between p-2 bg-white/[0.03] rounded-lg mb-2">
        <span className="text-xs text-white/55">Current</span>
        <span className="text-xs text-white/75 font-mono truncate max-w-[200px]">
          {data?.path || 'Empty'}
        </span>
      </div>

      {editing ? (
        <div className="p-3 bg-white/[0.04] rounded-lg border border-white/[0.06] space-y-2">
          <input
            type="text"
            value={isoPath}
            onChange={(e) => setIsoPath(e.target.value)}
            placeholder="/path/to/image.iso"
            className="w-full px-2.5 py-1.5 tahoe-glass-card border border-white/15 rounded text-xs text-white placeholder-white/40 font-mono focus:outline-none focus:ring-1 focus:ring-cyan-500"
          />
          <div className="flex justify-end gap-2">
            <button onClick={() => setEditing(false)} className="px-2.5 py-1 text-xs text-white/55 hover:text-white transition-colors">Cancel</button>
            <button onClick={handleChange} disabled={loading}
              className="flex items-center gap-1 px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-xs transition-colors disabled:opacity-50">
              {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Disc className="h-3 w-3" />}
              {isoPath ? 'Insert' : 'Eject'}
            </button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2">
          <button onClick={() => setEditing(true)}
            className="flex items-center gap-1 px-3 py-1.5 bg-blue-600/10 hover:bg-blue-600/20 text-blue-400 rounded-lg text-xs transition-colors">
            <Edit2 className="h-3 w-3" /> Change ISO
          </button>
          {data?.path && (
            <button onClick={handleEject} disabled={loading}
              className="flex items-center gap-1 px-3 py-1.5 bg-red-600/10 hover:bg-red-600/20 text-red-400 rounded-lg text-xs transition-colors disabled:opacity-50">
              {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <X className="h-3 w-3" />} Eject
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// TPM Section
// ---------------------------------------------------------------------------

function TPMSection({ data, vmName, isRunning, onUpdated }: {
  data: HardwareData['tpm'];
  vmName: string;
  isRunning: boolean;
  onUpdated: () => void;
}) {
  const [loading, setLoading] = useState(false);

  const handleAdd = async () => {
    setLoading(true);
    try {
      const res = await hw.addTPM(vmName, { model: 'tpm-crb', version: '2.0' });
      showToast('success', res.message || 'TPM added');
      onUpdated();
    } catch (err) {
      showToast('error', (err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const hasTPM = data?.model || data?.version;

  return (
    <div>
      {hasTPM ? (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between p-2 bg-white/[0.03] rounded-lg">
            <span className="text-xs text-white/55">Model</span>
            <span className="text-xs text-white/75">{data?.model || '-'}</span>
          </div>
          <div className="flex items-center justify-between p-2 bg-white/[0.03] rounded-lg">
            <span className="text-xs text-white/55">Version</span>
            <span className="text-xs text-white/75">{data?.version || '-'}</span>
          </div>
        </div>
      ) : (
        <div>
          <div className="text-xs text-white/45 mb-2">Not configured</div>
          {isRunning ? (
            <div className="flex items-center gap-1.5 text-xs text-yellow-400">
              <AlertCircle className="h-3 w-3" /> VM must be shut off to add TPM
            </div>
          ) : (
            <button onClick={handleAdd} disabled={loading}
              className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs transition-colors disabled:opacity-50">
              {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Shield className="h-3 w-3" />} Add TPM 2.0
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Boot Order Section
// ---------------------------------------------------------------------------

function BootSection({ data, vmName, isRunning, onUpdated }: {
  data: HardwareData['boot'];
  vmName: string;
  isRunning: boolean;
  onUpdated: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [bootDevices, setBootDevices] = useState<Record<string, boolean>>({ hd: true, cdrom: false, network: false });
  const [firmware, setFirmware] = useState('bios');

  useEffect(() => {
    if (data) {
      const devMap: Record<string, boolean> = { hd: false, cdrom: false, network: false };
      (data.order || []).forEach((d) => { devMap[d] = true; });
      setBootDevices(devMap);
      setFirmware(data.firmware || 'bios');
    }
  }, [data]);

  const handleSave = async () => {
    setLoading(true);
    try {
      const order = Object.entries(bootDevices).filter(([, v]) => v).map(([k]) => k);
      const res = await hw.setBoot(vmName, { order, firmware });
      showToast('success', res.message || 'Boot config updated');
      setEditing(false);
      onUpdated();
    } catch (err) {
      showToast('error', (err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  if (isRunning && !editing) {
    return (
      <div>
        <div className="space-y-1.5">
          <div className="flex items-center justify-between p-2 bg-white/[0.03] rounded-lg">
            <span className="text-xs text-white/55">Boot Order</span>
            <span className="text-xs text-white/75">{(data?.order || []).join(', ') || '-'}</span>
          </div>
          <div className="flex items-center justify-between p-2 bg-white/[0.03] rounded-lg">
            <span className="text-xs text-white/55">Firmware</span>
            <span className="text-xs text-white/75 uppercase">{data?.firmware || 'bios'}</span>
          </div>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-yellow-400 mt-2">
          <AlertCircle className="h-3 w-3" /> VM must be shut off to edit boot config
        </div>
      </div>
    );
  }

  return (
    <div>
      {editing ? (
        <div className="p-3 bg-white/[0.04] rounded-lg border border-white/[0.06] space-y-3">
          <div>
            <label className="block text-[10px] text-white/45 mb-1.5">Boot Devices</label>
            <div className="space-y-1">
              {(['hd', 'cdrom', 'network'] as const).map((dev) => (
                <label key={dev} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={bootDevices[dev] || false}
                    onChange={(e) => setBootDevices({ ...bootDevices, [dev]: e.target.checked })}
                    className="rounded border-white/15 tahoe-glass-card text-blue-500 focus:ring-blue-500 focus:ring-offset-0 h-3.5 w-3.5"
                  />
                  <span className="text-xs text-white/75">{dev === 'hd' ? 'Hard Disk' : dev === 'cdrom' ? 'CD-ROM' : 'Network (PXE)'}</span>
                </label>
              ))}
            </div>
          </div>
          <InlineSelect label="Firmware" value={firmware} onChange={setFirmware}
            options={[{ value: 'bios', label: 'BIOS' }, { value: 'uefi', label: 'UEFI' }]} />
          <div className="flex justify-end gap-2 pt-1">
            <button onClick={() => setEditing(false)} className="px-2.5 py-1 text-xs text-white/55 hover:text-white transition-colors">Cancel</button>
            <button onClick={handleSave} disabled={loading}
              className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs transition-colors disabled:opacity-50">
              {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />} Save
            </button>
          </div>
        </div>
      ) : (
        <div>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between p-2 bg-white/[0.03] rounded-lg">
              <span className="text-xs text-white/55">Boot Order</span>
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-white/75">{(data?.order || []).join(', ') || '-'}</span>
                <button onClick={() => setEditing(true)}
                  aria-label="Edit Boot Order"
                  className="h-5 w-5 rounded hover:bg-blue-500/10 text-white/45 hover:text-blue-400 flex items-center justify-center transition-colors">
                  <Edit2 className="h-3 w-3" />
                </button>
              </div>
            </div>
            <div className="flex items-center justify-between p-2 bg-white/[0.03] rounded-lg">
              <span className="text-xs text-white/55">Firmware</span>
              <span className="text-xs text-white/75 uppercase">{data?.firmware || 'bios'}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export function HardwareEditor({ vmName, vmState, onRefresh }: HardwareEditorProps) {
  const [hwData, setHwData] = useState<HardwareData | null>(null);
  const [loadingHW, setLoadingHW] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    cpu: true,
    memory: true,
    disks: false,
    network: false,
    cdrom: false,
    tpm: false,
    boot: false,
  });

  const isRunning = vmState === 'running';

  const loadHardware = useCallback(async () => {
    setLoadingHW(true);
    setError(null);
    try {
      const data = await hw.get(vmName);
      setHwData(data);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoadingHW(false);
    }
  }, [vmName]);

  useEffect(() => {
    loadHardware();
  }, [loadHardware]);

  const handleUpdated = () => {
    loadHardware();
    onRefresh?.();
  };

  const toggleSection = (key: string) => {
    setOpenSections((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const liveBadge = (supportsLive: boolean) => {
    if (!isRunning) return undefined;
    return supportsLive ? 'Live' : 'Requires restart';
  };

  return (
    <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Zap className="h-4 w-4 text-amber-400" />
          <span className="text-sm font-semibold text-white">Hardware Editor</span>
        </div>
        <button onClick={loadHardware} disabled={loadingHW}
          aria-label="Refresh hardware configuration"
          className="flex items-center gap-1 text-xs text-white/55 hover:text-white transition-colors disabled:opacity-50">
          {loadingHW ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />} Refresh
        </button>
      </div>

      {error && (
        <div className="text-xs text-red-400 mb-3 flex items-center gap-1">
          <AlertCircle className="h-3 w-3 flex-shrink-0" /> {error}
        </div>
      )}

      {loadingHW && !hwData ? (
        <div className="flex items-center justify-center py-6">
          <Loader2 className="h-5 w-5 animate-spin text-blue-400" />
        </div>
      ) : (
        <div className="divide-y divide-white/[0.06]">
          {/* CPU */}
          <div>
            <SectionHeader icon={Cpu} color="text-blue-400" title="CPU"
              badge={liveBadge(true)} open={openSections.cpu} onToggle={() => toggleSection('cpu')} />
            {openSections.cpu && (
              <div className="pb-3">
                <CPUSection data={hwData?.cpu} vmName={vmName} onUpdated={handleUpdated} />
              </div>
            )}
          </div>

          {/* Memory */}
          <div>
            <SectionHeader icon={MemoryStick} color="text-green-400" title="Memory"
              badge={liveBadge(true)} open={openSections.memory} onToggle={() => toggleSection('memory')} />
            {openSections.memory && (
              <div className="pb-3">
                <MemorySection data={hwData?.memory} vmName={vmName} onUpdated={handleUpdated} />
              </div>
            )}
          </div>

          {/* Disks */}
          <div>
            <SectionHeader icon={HardDrive} color="text-yellow-400" title="Disks"
              badge={liveBadge(false)} open={openSections.disks} onToggle={() => toggleSection('disks')} />
            {openSections.disks && (
              <div className="pb-3">
                <DisksSection data={hwData?.disks} vmName={vmName} onUpdated={handleUpdated} />
              </div>
            )}
          </div>

          {/* Network */}
          <div>
            <SectionHeader icon={Network} color="text-cyan-400" title="Network Interfaces"
              badge={liveBadge(false)} open={openSections.network} onToggle={() => toggleSection('network')} />
            {openSections.network && (
              <div className="pb-3">
                <NetworkSection data={hwData?.interfaces} vmName={vmName} onUpdated={handleUpdated} />
              </div>
            )}
          </div>

          {/* CDROM */}
          <div>
            <SectionHeader icon={Disc} color="text-purple-400" title="CD-ROM"
              badge={liveBadge(true)} open={openSections.cdrom} onToggle={() => toggleSection('cdrom')} />
            {openSections.cdrom && (
              <div className="pb-3">
                <CDROMSection data={hwData?.cdrom} vmName={vmName} onUpdated={handleUpdated} />
              </div>
            )}
          </div>

          {/* TPM */}
          <div>
            <SectionHeader icon={Shield} color="text-red-400" title="TPM"
              badge={liveBadge(false)} open={openSections.tpm} onToggle={() => toggleSection('tpm')} />
            {openSections.tpm && (
              <div className="pb-3">
                <TPMSection data={hwData?.tpm} vmName={vmName} isRunning={isRunning} onUpdated={handleUpdated} />
              </div>
            )}
          </div>

          {/* Boot Order */}
          <div>
            <SectionHeader icon={PlayCircle} color="text-orange-400" title="Boot Order"
              badge={liveBadge(false)} open={openSections.boot} onToggle={() => toggleSection('boot')} />
            {openSections.boot && (
              <div className="pb-3">
                <BootSection data={hwData?.boot} vmName={vmName} isRunning={isRunning} onUpdated={handleUpdated} />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
