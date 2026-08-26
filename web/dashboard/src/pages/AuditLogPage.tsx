// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Shield, Search, Filter } from 'lucide-react';
import { fetchAPI } from '../api/client';
import { TahoeHero } from '../components/ui/TahoeHero';

interface AuditEntry {
  time: string;
  user: string;
  action: string;
  target: string;
  result: string;
}

const ACTION_TYPES = ['All', 'login', 'logout', 'create', 'delete', 'update', 'start', 'stop', 'migrate', 'export'];

export function AuditLogPage() {
  const [actionFilter, setActionFilter] = useState('All');
  const [searchQuery, setSearchQuery] = useState('');

  const { data: entries, isLoading } = useQuery({
    queryKey: ['audit'],
    queryFn: () => fetchAPI<AuditEntry[]>('/audit'),
    refetchInterval: 10000,
  });

  const filtered = useMemo(() => {
    if (!entries) return [];
    let result = [...entries];

    // Sort most recent first
    result.sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime());

    if (actionFilter !== 'All') {
      result = result.filter((e) => e.action.toLowerCase().includes(actionFilter.toLowerCase()));
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter((e) => e.target.toLowerCase().includes(q));
    }

    return result;
  }, [entries, actionFilter, searchQuery]);

  return (
    <div className="space-y-6">
      <TahoeHero
        icon={<Shield className="w-5 h-5 text-blue-300" />}
        title="Audit Log"
        subtitle={`${filtered.length} ${filtered.length === 1 ? 'entry' : 'entries'}${actionFilter !== 'All' ? ` matching "${actionFilter}"` : ''}`}
      />

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Search */}
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/45" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by target..."
            className="w-full pl-9 pr-3 py-2 tahoe-glass-card border border-white/[0.08] rounded-lg text-sm text-white/90 placeholder-white/40 focus:outline-none focus:ring-1 focus:ring-blue-500/50 focus:border-blue-500/50"
          />
        </div>

        {/* Action filter */}
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-white/45 flex-shrink-0" />
          <div className="flex flex-wrap gap-1">
            {ACTION_TYPES.map((action) => (
              <button
                key={action}
                onClick={() => setActionFilter(action)}
                className={`px-2.5 py-1 text-xs font-medium rounded-lg transition-colors ${
                  actionFilter === action
                    ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                    : 'text-white/55 hover:text-white/90 hover:tahoe-glass-card border border-transparent'
                }`}
              >
                {action}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="tahoe-glass-card rounded-xl border border-white/[0.08] overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-16">
            <Shield className="h-10 w-10 text-white/20 mx-auto mb-3" />
            <div className="text-sm text-white/45">No audit entries found</div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/[0.08]">
                  <th className="text-left px-4 py-3 text-xs font-semibold text-white/55 uppercase tracking-wider">Time</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-white/55 uppercase tracking-wider">User</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-white/55 uppercase tracking-wider">Action</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-white/55 uppercase tracking-wider">Target</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-white/55 uppercase tracking-wider">Result</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.06]">
                {filtered.map((entry, i) => (
                  <tr key={i} className="table-row-hover transition-colors">
                    <td className="px-4 py-3 text-xs text-white/55 font-mono whitespace-nowrap">
                      {formatTime(entry.time)}
                    </td>
                    <td className="px-4 py-3 text-xs text-white/75">{entry.user}</td>
                    <td className="px-4 py-3">
                      <ActionBadge action={entry.action} />
                    </td>
                    <td className="px-4 py-3 text-xs text-white/75 font-mono max-w-xs truncate">{entry.target}</td>
                    <td className="px-4 py-3">
                      <ResultBadge result={entry.result} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function ActionBadge({ action }: { action: string }) {
  const colors: Record<string, string> = {
    login: 'bg-blue-500/10 text-blue-400',
    logout: 'bg-white/[0.06] text-white/55',
    create: 'bg-green-500/10 text-green-400',
    delete: 'bg-red-500/10 text-red-400',
    update: 'bg-yellow-500/10 text-yellow-400',
    start: 'bg-cyan-500/10 text-cyan-400',
    stop: 'bg-orange-500/10 text-orange-400',
    migrate: 'bg-purple-500/10 text-purple-400',
    export: 'bg-indigo-500/10 text-indigo-400',
  };
  const key = Object.keys(colors).find((k) => action.toLowerCase().includes(k));
  const cls = key ? colors[key] : 'bg-white/[0.06] text-white/55';

  return (
    <span className={`inline-flex text-[10px] font-medium px-2 py-0.5 rounded-full ${cls}`}>
      {action}
    </span>
  );
}

function ResultBadge({ result }: { result: string }) {
  const lower = result.toLowerCase();
  const cls = lower === 'success' || lower === 'ok'
    ? 'bg-green-500/10 text-green-400'
    : lower === 'failure' || lower === 'error' || lower === 'denied'
    ? 'bg-red-500/10 text-red-400'
    : 'bg-white/[0.06] text-white/55';

  return (
    <span className={`inline-flex text-[10px] font-medium px-2 py-0.5 rounded-full ${cls}`}>
      {result}
    </span>
  );
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}
