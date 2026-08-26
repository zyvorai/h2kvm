// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useState, useRef, useCallback, lazy, Suspense } from 'react';
import { Monitor, Maximize2, Minimize2, RefreshCw, X, Keyboard } from 'lucide-react';

const LazyVncScreen = lazy(() =>
  import('react-vnc').then(mod => ({ default: mod.VncScreen }))
);

interface KVConsoleProps {
  vmName: string;
  namespace: string;
  onClose: () => void;
}

export function KVConsoleModal({ vmName, namespace, onClose }: KVConsoleProps) {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [key, setKey] = useState(0);
  const vncRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const vncUrl = `${protocol}//${window.location.host}/api/v1/vnc-proxy-kv/${encodeURIComponent(namespace)}/${encodeURIComponent(vmName)}`;

  const focusVnc = useCallback(() => {
    const canvas = containerRef.current?.querySelector('canvas');
    if (canvas) { canvas.setAttribute('tabindex', '0'); canvas.focus(); }
  }, []);

  return (
    <>
      <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50" onClick={onClose} />
      <div className={`fixed z-50 glass border border-white/[0.08] rounded-xl shadow-2xl overflow-hidden transition-all ${
        isFullscreen ? 'inset-4' : 'top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[90vw] max-w-5xl h-[80vh]'
      }`}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2.5 glass border-b border-white/[0.08]">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-purple-500/20 flex items-center justify-center">
              <Monitor className="h-4 w-4 text-purple-400" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white">KubeVirt Console: {vmName}</h3>
              <p className="text-[10px] text-white/55">
                {namespace} · {isConnected ? <span className="text-green-400">Connected</span> : 'Connecting via virtctl...'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <button onClick={focusVnc} className="flex items-center gap-1 px-2 py-1 text-[10px] bg-purple-600 hover:bg-purple-500 text-white rounded">
              <Keyboard className="h-3 w-3" /> Focus
            </button>
            <button onClick={() => { vncRef.current?.sendCtrlAltDel?.(); }} className="px-2 py-1 text-[10px] bg-white/[0.08] hover:bg-white/20 text-white rounded">Ctrl+Alt+Del</button>
            <button onClick={() => { setKey(k => k + 1); setError(null); setIsConnected(false); }} className="h-7 w-7 rounded hover:bg-white/[0.04] flex items-center justify-center text-white/55">
              <RefreshCw className={`h-3.5 w-3.5 ${!isConnected && !error ? 'animate-spin' : ''}`} />
            </button>
            <button onClick={() => setIsFullscreen(!isFullscreen)} className="h-7 w-7 rounded hover:bg-white/[0.04] flex items-center justify-center text-white/55">
              {isFullscreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
            </button>
            <button onClick={onClose} className="h-7 w-7 rounded hover:bg-red-500/20 hover:text-red-400 flex items-center justify-center text-white/55">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {error && (
          <div className="px-4 py-2 bg-red-900/20 border-b border-red-800/50 text-xs text-red-400 flex items-center gap-2">
            {error}
            <button onClick={() => { setKey(k => k + 1); setError(null); }} className="px-2 py-0.5 bg-red-800 hover:bg-red-700 text-white rounded">Retry</button>
          </div>
        )}

        <div ref={containerRef} className="h-[calc(100%-3rem)] bg-black" onClick={focusVnc}>
          <Suspense fallback={
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <div className="w-10 h-10 mx-auto border-4 border-purple-500 border-t-transparent rounded-full animate-spin mb-3" />
                <p className="text-white/45 text-sm">Connecting via virtctl VNC proxy...</p>
              </div>
            </div>
          }>
            <LazyVncScreen
              key={key}
              ref={vncRef}
              url={vncUrl}
              scaleViewport resizeSession focusOnClick
              background="#000000"
              style={{ width: '100%', height: '100%' }}
              onConnect={() => { setIsConnected(true); setError(null); setTimeout(focusVnc, 500); }}
              onDisconnect={(e: any) => { setIsConnected(false); if (e?.detail && !e.detail.clean) setError('VNC disconnected'); }}
              onSecurityFailure={(e: any) => setError(e?.detail?.reason || 'Security failure')}
            />
          </Suspense>
        </div>
      </div>
    </>
  );
}
