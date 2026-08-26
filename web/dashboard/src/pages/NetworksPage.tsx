// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Network, Play, Square, Wifi, Share2 } from 'lucide-react';
import { fetchAPI } from '../api/client';
import { TahoeHero } from '../components/ui/TahoeHero';

interface NetInfo {
  name: string;
  state: string;
  autostart: string;
  bridge: string;
}

interface TopologyVM {
  name: string;
  mac: string;
  ip: string;
  state: string;
}

interface TopologyNetwork {
  name: string;
  state: string;
  bridge: string;
  vms: TopologyVM[];
}

interface TopologyResponse {
  networks: TopologyNetwork[];
}

export function NetworksPage() {
  const queryClient = useQueryClient();
  const { data: nets, isLoading } = useQuery({
    queryKey: ['networks'],
    queryFn: () => fetchAPI<NetInfo[]>('/networks'),
    refetchInterval: 10000,
  });

  const { data: topology } = useQuery({
    queryKey: ['network-topology'],
    queryFn: () => fetchAPI<TopologyResponse>('/networks/topology'),
    refetchInterval: 10000,
  });

  const action = useMutation({
    mutationFn: ({ name, act }: { name: string; act: string }) =>
      fetchAPI<{ message: string }>(`/networks/${name}/${act}`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['networks'] }),
  });

  return (
    <div>
      <TahoeHero
        icon={<Network className="w-5 h-5 text-cyan-300" />}
        title="Networks"
        subtitle="Libvirt virtual networks and topology"
      />

      <div className="tahoe-glass-card rounded-xl border border-white/[0.08] overflow-hidden">
        <div className="px-5 py-3 border-b border-white/[0.06] flex items-center gap-2">
          <Network className="h-4 w-4 text-cyan-400" />
          <span className="text-sm font-semibold text-white">Virtual Networks</span>
        </div>

        {isLoading ? (
          <div className="p-4 space-y-2">{[1,2].map(i => <div key={i} className="skeleton h-12 rounded-lg" />)}</div>
        ) : (
          <div className="divide-y divide-white/[0.06]">
            {nets?.map((net) => {
              const active = net.state === 'active';
              return (
                <div key={net.name} className="flex items-center gap-4 px-5 py-3 hover:bg-white/[0.04]/20 transition-colors">
                  <div className={`w-2.5 h-2.5 rounded-full ${active ? 'bg-green-400' : 'bg-white/30'}`} />
                  <Wifi className={`h-4 w-4 ${active ? 'text-cyan-400' : 'text-white/45'}`} />
                  <div className="flex-1">
                    <div className="text-sm font-medium text-white">{net.name}</div>
                    <div className="text-xs text-white/45">
                      Bridge: {net.bridge || 'N/A'} · Autostart: {net.autostart}
                    </div>
                  </div>
                  {active ? (
                    <button onClick={() => action.mutate({ name: net.name, act: 'stop' })}
                      className="flex items-center gap-1 px-2.5 py-1.5 bg-red-500/10 text-red-400 rounded-lg text-xs hover:bg-red-500/20 transition-colors">
                      <Square className="h-3 w-3" /> Stop
                    </button>
                  ) : (
                    <button onClick={() => action.mutate({ name: net.name, act: 'start' })}
                      className="flex items-center gap-1 px-2.5 py-1.5 bg-green-500/10 text-green-400 rounded-lg text-xs hover:bg-green-500/20 transition-colors">
                      <Play className="h-3 w-3" /> Start
                    </button>
                  )}
                  <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${
                    active ? 'bg-green-500/10 text-green-400' : 'bg-white/[0.06] text-white/55'
                  }`}>{net.state}</span>
                </div>
              );
            })}
            {(!nets || nets.length === 0) && <div className="p-8 text-center text-sm text-white/45">No networks defined</div>}
          </div>
        )}
      </div>

      {/* Network Topology */}
      {topology && topology.networks && topology.networks.length > 0 && (
        <div className="mt-6">
          <div className="flex items-center gap-2 mb-4">
            <Share2 className="h-4 w-4 text-purple-400" />
            <h3 className="text-lg font-semibold text-white">Network Topology</h3>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {topology.networks.map((net) => {
              const active = net.state === 'active';
              return (
                <div key={net.name} className="tahoe-glass-card rounded-xl border border-white/[0.08] p-4">
                  <div className="flex items-center gap-3 mb-3">
                    <div className={`w-2.5 h-2.5 rounded-full ${active ? 'bg-green-400 shadow-green-400/50 shadow-sm' : 'bg-white/30'}`} />
                    <div>
                      <div className="text-sm font-medium text-white">{net.name}</div>
                      <div className="text-[10px] text-white/45">Bridge: {net.bridge || 'N/A'} · {net.state}</div>
                    </div>
                  </div>
                  {net.vms && net.vms.length > 0 ? (
                    <div className="space-y-1.5">
                      {net.vms.map((vm) => (
                        <div key={`${vm.name}-${vm.mac}`} className="flex items-center gap-3 p-2 tahoe-glass-card rounded-lg text-xs">
                          <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                            vm.state === 'running' ? 'bg-green-400' :
                            vm.state === 'paused' ? 'bg-yellow-400' : 'bg-white/30'
                          }`} />
                          <div className="flex-1 min-w-0">
                            <div className="text-white/75 font-medium truncate">{vm.name}</div>
                            <div className="flex items-center gap-2 text-[10px] text-white/45">
                              <span className="font-mono">{vm.mac}</span>
                              {vm.ip && <span className="text-green-400">{vm.ip}</span>}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-xs text-white/45 text-center py-2">No VMs connected</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
