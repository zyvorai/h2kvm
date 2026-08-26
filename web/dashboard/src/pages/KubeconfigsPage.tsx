// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Key, Plus, Trash2, CheckCircle, Upload, FolderOpen,
  Server, Clock, RefreshCw, Star,
} from 'lucide-react';
import {
  listKubeconfigs, addKubeconfigByPath, addKubeconfigByUpload,
  activateKubeconfig, deleteKubeconfig,
  type ClusterEntry,
} from '../api/kubeconfigs';
import { showToast } from '../components/Toast';
import { TahoeHero } from '../components/ui/TahoeHero';

export function KubeconfigsPage() {
  const queryClient = useQueryClient();
  const [showAddForm, setShowAddForm] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['kubeconfigs'],
    queryFn: listKubeconfigs,
    refetchInterval: 10000,
  });

  const activateMut = useMutation({
    mutationFn: (id: string) => activateKubeconfig(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['kubeconfigs'] });
      showToast('success', `Cluster "${id}" activated`);
    },
    onError: (err) => showToast('error', (err as Error).message),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteKubeconfig(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['kubeconfigs'] });
      showToast('success', `Cluster "${id}" deleted`);
    },
    onError: (err) => showToast('error', (err as Error).message),
  });

  const clusters = data?.clusters || [];

  return (
    <div>
      <TahoeHero
        icon={<Key className="w-5 h-5 text-blue-300" />}
        title="Kubeconfigs"
        subtitle={`${clusters.length} cluster${clusters.length !== 1 ? 's' : ''} registered`}
        actions={
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-medium transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          Add Cluster
        </button>
        }
      />

      {showAddForm && (
        <AddClusterForm
          onClose={() => setShowAddForm(false)}
          onAdded={() => {
            setShowAddForm(false);
            queryClient.invalidateQueries({ queryKey: ['kubeconfigs'] });
          }}
        />
      )}

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3].map(i => <div key={i} className="skeleton h-20 rounded-xl" />)}
        </div>
      ) : clusters.length === 0 ? (
        <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-12 text-center">
          <Key className="h-12 w-12 text-blue-400/30 mx-auto mb-3" />
          <div className="text-sm text-white/55">No kubeconfigs registered</div>
          <div className="text-xs text-white/45 mt-1 max-w-md mx-auto">
            Connect a Kubernetes cluster to enable KubeVirt VM deployments.
            Common paths: <code className="bg-white/[0.08] px-1 rounded">~/.kube/config</code> or <code className="bg-white/[0.08] px-1 rounded">/etc/rancher/k3s/k3s.yaml</code>
          </div>
          <button
            onClick={() => setShowAddForm(true)}
            className="mt-4 inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-medium transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Cluster
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {clusters.map((cluster) => (
            <ClusterCard
              key={cluster.id}
              cluster={cluster}
              onActivate={() => activateMut.mutate(cluster.id)}
              onDelete={() => deleteMut.mutate(cluster.id)}
              activating={activateMut.isPending}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ClusterCard({
  cluster, onActivate, onDelete, activating,
}: {
  cluster: ClusterEntry;
  onActivate: () => void;
  onDelete: () => void;
  activating: boolean;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <div className={`tahoe-glass-card rounded-xl border p-5 transition-colors ${
      cluster.is_active
        ? 'border-green-500/40 shadow-green-500/5 shadow-lg'
        : 'border-white/[0.08]'
    }`}>
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          {/* Connection status */}
          <div className={`w-3 h-3 rounded-full flex-shrink-0 ${
            cluster.connected
              ? 'bg-green-400 shadow-green-400/50 shadow-sm'
              : 'bg-red-400 shadow-red-400/50 shadow-sm'
          }`} />
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-white">{cluster.name}</span>
              {cluster.is_active && (
                <span className="text-[10px] px-1.5 py-0.5 bg-green-500/15 text-green-400 border border-green-500/30 rounded-full flex items-center gap-1">
                  <Star className="h-2.5 w-2.5" /> Active
                </span>
              )}
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                cluster.connected
                  ? 'bg-green-500/10 text-green-400'
                  : 'bg-red-500/10 text-red-400'
              }`}>
                {cluster.connected ? 'Connected' : 'Unreachable'}
              </span>
            </div>
            <div className="flex items-center gap-4 mt-1.5 text-xs text-white/45">
              <span className="flex items-center gap-1">
                <Key className="h-3 w-3" /> {cluster.id}
              </span>
              <span className="flex items-center gap-1">
                <FolderOpen className="h-3 w-3" /> {cluster.source}
              </span>
              {cluster.server_url && (
                <span className="flex items-center gap-1 text-cyan-400">
                  <Server className="h-3 w-3" /> {cluster.server_url}
                </span>
              )}
              {cluster.version && (
                <span className="flex items-center gap-1">
                  <RefreshCw className="h-3 w-3" /> {cluster.version.split('\n')[0]}
                </span>
              )}
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" /> {new Date(cluster.added_at).toLocaleDateString()}
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          {!cluster.is_active && (
            <button
              onClick={onActivate}
              disabled={activating}
              className="flex items-center gap-1 px-2.5 py-1.5 bg-green-500/10 text-green-400 hover:bg-green-500/20 rounded-lg text-xs transition-colors disabled:opacity-50"
            >
              <CheckCircle className="h-3 w-3" /> Activate
            </button>
          )}
          {confirmDelete ? (
            <div className="flex items-center gap-1">
              <button
                onClick={() => { onDelete(); setConfirmDelete(false); }}
                className="px-2.5 py-1.5 bg-red-600 hover:bg-red-500 text-white rounded-lg text-xs transition-colors"
              >
                Confirm
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="px-2.5 py-1.5 border border-white/[0.12] text-white/75 rounded-lg text-xs hover:bg-white/[0.04] transition-colors"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              className="h-7 w-7 rounded-lg hover:bg-red-500/10 text-white/55 hover:text-red-400 flex items-center justify-center transition-colors"
              title="Delete"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function AddClusterForm({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const [mode, setMode] = useState<'path' | 'upload'>('path');
  const [name, setName] = useState('');
  const [path, setPath] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleSubmit = async () => {
    if (!name.trim()) {
      showToast('error', 'Cluster name is required');
      return;
    }

    setSubmitting(true);
    try {
      if (mode === 'path') {
        if (!path.trim()) {
          showToast('error', 'Path is required');
          setSubmitting(false);
          return;
        }
        await addKubeconfigByPath(name.trim(), path.trim());
      } else {
        if (!file) {
          showToast('error', 'Please select a kubeconfig file');
          setSubmitting(false);
          return;
        }
        await addKubeconfigByUpload(name.trim(), file);
      }
      showToast('success', `Cluster "${name}" added`);
      onAdded();
    } catch (err) {
      showToast('error', (err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="tahoe-glass-card rounded-xl border border-blue-500/30 p-5 mb-6">
      <div className="flex items-center gap-2 mb-4">
        <Plus className="h-4 w-4 text-blue-400" />
        <span className="text-sm font-semibold text-white">Add Kubernetes Cluster</span>
      </div>

      {/* Mode tabs */}
      <div className="flex gap-1 mb-4">
        <button
          onClick={() => setMode('path')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-colors ${
            mode === 'path' ? 'bg-blue-600/20 text-blue-400' : 'text-white/55 hover:text-white/90 hover:bg-white/[0.04]'
          }`}
        >
          <FolderOpen className="h-3 w-3" /> Server Path
        </button>
        <button
          onClick={() => setMode('upload')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-colors ${
            mode === 'upload' ? 'bg-blue-600/20 text-blue-400' : 'text-white/55 hover:text-white/90 hover:bg-white/[0.04]'
          }`}
        >
          <Upload className="h-3 w-3" /> Upload File
        </button>
      </div>

      <div className="space-y-3">
        {/* Cluster name */}
        <div>
          <label className="text-xs text-white/55 mb-1 block">Cluster Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. production, staging, k3s-lab"
            className="w-full px-3 py-2 tahoe-glass-card border border-white/[0.08] rounded-lg text-sm text-white/90 placeholder-slate-600 focus:outline-none focus:border-blue-500/50"
          />
        </div>

        {mode === 'path' ? (
          <div>
            <label className="text-xs text-white/55 mb-1 block">Kubeconfig Path (on server)</label>
            <input
              type="text"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              placeholder="/etc/rancher/k3s/k3s.yaml or ~/.kube/config"
              className="w-full px-3 py-2 tahoe-glass-card border border-white/[0.08] rounded-lg text-sm text-white/90 placeholder-slate-600 focus:outline-none focus:border-blue-500/50 font-mono"
            />
          </div>
        ) : (
          <div>
            <label className="text-xs text-white/55 mb-1 block">Kubeconfig File</label>
            <div
              onClick={() => fileRef.current?.click()}
              className="w-full px-3 py-4 tahoe-glass-card border border-dashed border-white/[0.08] rounded-lg text-center cursor-pointer hover:border-blue-500/50 transition-colors"
            >
              <Upload className="h-5 w-5 text-white/45 mx-auto mb-1" />
              <div className="text-xs text-white/55">
                {file ? file.name : 'Click to select kubeconfig file'}
              </div>
              <input
                ref={fileRef}
                type="file"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 mt-4">
        <button
          onClick={handleSubmit}
          disabled={submitting}
          className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
        >
          {submitting ? (
            <div className="w-3 h-3 border border-white/30 border-t-white rounded-full animate-spin" />
          ) : (
            <Plus className="h-3.5 w-3.5" />
          )}
          Add Cluster
        </button>
        <button
          onClick={onClose}
          className="px-4 py-2 border border-white/[0.12] text-white/75 rounded-lg text-xs hover:bg-white/[0.04] transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
