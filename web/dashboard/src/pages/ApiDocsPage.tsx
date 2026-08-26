// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useQuery } from '@tanstack/react-query';
import { FileText, Loader2 } from 'lucide-react';
import { fetchAPI } from '../api/client';
import { TahoeHero } from '../components/ui/TahoeHero';

interface ApiEndpoint {
  method: string;
  path: string;
  description: string;
  category?: string;
}

interface ApiDocsResponse {
  endpoints: ApiEndpoint[];
}

const METHOD_COLORS: Record<string, { text: string; bg: string }> = {
  GET:    { text: 'text-green-400',  bg: 'bg-green-500/10' },
  POST:   { text: 'text-blue-400',   bg: 'bg-blue-500/10' },
  PUT:    { text: 'text-yellow-400', bg: 'bg-yellow-500/10' },
  PATCH:  { text: 'text-orange-400', bg: 'bg-orange-500/10' },
  DELETE: { text: 'text-red-400',    bg: 'bg-red-500/10' },
};

function groupByCategory(endpoints: ApiEndpoint[]): Record<string, ApiEndpoint[]> {
  const groups: Record<string, ApiEndpoint[]> = {};
  for (const ep of endpoints) {
    const cat = ep.category || inferCategory(ep.path);
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(ep);
  }
  return groups;
}

function inferCategory(path: string): string {
  const parts = path.replace(/^\/api\/v1\//, '').split('/');
  const first = parts[0] || 'General';
  const map: Record<string, string> = {
    vms: 'VMs',
    jobs: 'Jobs',
    upload: 'Upload',
    networks: 'Networks',
    providers: 'Providers',
    settings: 'Settings',
    auth: 'Auth',
    download: 'Download',
    browse: 'Browse',
    docs: 'Docs',
    kubevirt: 'KubeVirt',
  };
  return map[first] || first.charAt(0).toUpperCase() + first.slice(1);
}

export function ApiDocsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['api-docs'],
    queryFn: () => fetchAPI<ApiDocsResponse>('/docs'),
  });

  const grouped = data?.endpoints ? groupByCategory(data.endpoints) : {};
  const categories = Object.keys(grouped).sort();

  return (
    <div>
      <TahoeHero
        icon={<FileText className="w-5 h-5 text-blue-300" />}
        title="API Documentation"
        subtitle="Available REST API endpoints"
      />

      {isLoading && (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-blue-400" />
        </div>
      )}

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-sm text-red-400">
          Failed to load API docs: {(error as Error)?.message || 'Unknown error'}
        </div>
      )}

      {!isLoading && !error && categories.length === 0 && (
        <div className="tahoe-glass-card rounded-xl border border-white/[0.08] p-8 text-center text-sm text-white/45">
          No API documentation available
        </div>
      )}

      <div className="space-y-6">
        {categories.map((cat) => (
          <div key={cat} className="tahoe-glass-card rounded-xl border border-white/[0.08] overflow-hidden">
            <div className="flex items-center gap-2 px-5 py-3 border-b border-white/[0.06]">
              <FileText className="h-4 w-4 text-blue-400" />
              <span className="text-sm font-semibold text-white">{cat}</span>
              <span className="text-xs text-white/45 ml-auto">{grouped[cat].length} endpoints</span>
            </div>

            <div className="divide-y divide-white/[0.06]/20">
              {grouped[cat].map((ep, i) => {
                const colors = METHOD_COLORS[ep.method.toUpperCase()] || METHOD_COLORS.GET;
                return (
                  <div key={`${ep.method}-${ep.path}-${i}`} className="flex items-center gap-4 px-5 py-3 hover:bg-white/[0.04]/20 transition-colors">
                    <span className={`inline-flex items-center justify-center w-16 px-2 py-1 rounded text-xs font-bold ${colors.bg} ${colors.text}`}>
                      {ep.method.toUpperCase()}
                    </span>
                    <span className="text-sm text-white font-mono flex-1">{ep.path}</span>
                    <span className="text-xs text-white/55 text-right max-w-[300px]">{ep.description}</span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
