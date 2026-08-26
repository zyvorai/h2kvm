// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useState, useRef, useCallback, lazy, Suspense } from 'react';
import { Monitor, Maximize2, Minimize2, RefreshCw, X, Keyboard, Clipboard } from 'lucide-react';

const LazyVncScreen = lazy(() =>
  import('react-vnc').then(mod => ({ default: mod.VncScreen }))
);

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected';

interface VNCConsoleProps {
  vmName: string;
  onClose: () => void;
}

export function VNCConsoleModal({ vmName, onClose }: VNCConsoleProps) {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('connecting');
  const [error, setError] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [key, setKey] = useState(0);
  const vncRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const modalRef = useRef<HTMLDivElement>(null);

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const vncUrl = `${protocol}//${window.location.host}/api/v1/vnc-proxy/${encodeURIComponent(vmName)}`;

  const focusVnc = useCallback(() => {
    const canvas = containerRef.current?.querySelector('canvas');
    if (canvas) {
      canvas.setAttribute('tabindex', '0');
      canvas.focus();
    }
  }, []);

  const sendCtrlAltDel = useCallback(() => {
    const rfb = vncRef.current?.rfb || vncRef.current;
    if (rfb?.sendCtrlAltDel) {
      rfb.sendCtrlAltDel();
    }
  }, []);

  const toggleFullscreen = useCallback(() => {
    if (!modalRef.current) return;

    if (!document.fullscreenElement) {
      modalRef.current.requestFullscreen().then(() => {
        setIsFullscreen(true);
      }).catch(() => {
        // Fallback: use CSS fullscreen
        setIsFullscreen(true);
      });
    } else {
      document.exitFullscreen().then(() => {
        setIsFullscreen(false);
      }).catch(() => {
        setIsFullscreen(false);
      });
    }
  }, []);

  const handleReconnect = useCallback(() => {
    setKey(k => k + 1);
    setError(null);
    setConnectionStatus('connecting');
  }, []);

  const handlePasteFromClipboard = useCallback(async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (!text) return;

      const rfb = vncRef.current?.rfb || vncRef.current;
      if (!rfb) return;

      // Type each character via the RFB connection.
      for (const char of text) {
        const code = char.charCodeAt(0);
        // XK_ keysym for ASCII is the same as the char code for printable ASCII.
        // For unicode, use the Unicode keysym range (0x01000000 + codepoint).
        const keysym = code < 0x100 ? code : 0x01000000 + code;
        rfb.sendKey(keysym, undefined, true);  // key down
        rfb.sendKey(keysym, undefined, false); // key up
      }
    } catch {
      // Clipboard access denied or unavailable.
    }
  }, []);

  const statusDot = connectionStatus === 'connected'
    ? 'bg-green-400'
    : connectionStatus === 'connecting'
      ? 'bg-yellow-400 animate-pulse'
      : 'bg-red-400';

  const statusText = connectionStatus === 'connected'
    ? 'Connected'
    : connectionStatus === 'connecting'
      ? 'Connecting...'
      : 'Disconnected';

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50" onClick={onClose} />

      {/* Console Window */}
      <div
        ref={modalRef}
        className={`fixed z-50 glass border border-white/[0.08] rounded-xl shadow-2xl overflow-hidden transition-all ${
          isFullscreen ? 'inset-0 rounded-none' : 'top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[90vw] max-w-5xl h-[80vh]'
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2.5 glass border-b border-white/[0.08]">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-blue-500/20 flex items-center justify-center">
              <Monitor className="h-4 w-4 text-blue-400" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white">VNC Console: {vmName}</h3>
              <p className="text-[10px] text-white/55">
                <span className="flex items-center gap-1">
                  <span className={`w-1.5 h-1.5 rounded-full ${statusDot}`} />
                  {statusText}
                </span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <button onClick={focusVnc} title="Focus keyboard input"
              className="flex items-center gap-1 px-2 py-1 text-[10px] bg-blue-600 hover:bg-blue-500 text-white rounded transition-colors">
              <Keyboard className="h-3 w-3" /> Focus
            </button>
            <button onClick={sendCtrlAltDel} title="Send Ctrl+Alt+Del"
              className="px-2 py-1 text-[10px] bg-white/[0.08] hover:bg-white/20 text-white rounded transition-colors">
              Ctrl+Alt+Del
            </button>
            <button onClick={handlePasteFromClipboard} title="Paste from clipboard"
              className="flex items-center gap-1 px-2 py-1 text-[10px] bg-white/[0.08] hover:bg-white/20 text-white rounded transition-colors">
              <Clipboard className="h-3 w-3" /> Paste
            </button>
            {connectionStatus === 'disconnected' && (
              <button onClick={handleReconnect} title="Reconnect"
                className="flex items-center gap-1 px-2 py-1 text-[10px] bg-amber-600 hover:bg-amber-500 text-white rounded transition-colors">
                <RefreshCw className="h-3 w-3" /> Reconnect
              </button>
            )}
            <button onClick={handleReconnect} title="Reconnect"
              className="h-7 w-7 rounded hover:bg-white/[0.04] flex items-center justify-center transition-colors text-yellow-400">
              <RefreshCw className={`h-3.5 w-3.5 ${connectionStatus === 'connecting' ? 'animate-spin' : ''}`} />
            </button>
            <button onClick={toggleFullscreen} title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
              className="h-7 w-7 rounded hover:bg-white/[0.04] flex items-center justify-center transition-colors text-blue-400">
              {isFullscreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
            </button>
            <button onClick={onClose} title="Close"
              className="h-7 w-7 rounded hover:bg-red-500/20 hover:text-red-300 flex items-center justify-center transition-colors text-red-400">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="px-4 py-3 bg-red-900/20 border-b border-red-800/50 flex items-center gap-2">
            <span className="text-xs text-red-400">{error}</span>
            <button onClick={handleReconnect}
              className="px-2 py-1 text-[10px] bg-red-800 hover:bg-red-700 text-white rounded">Retry</button>
          </div>
        )}

        {/* VNC Display */}
        <div ref={containerRef} className="h-[calc(100%-3rem)] bg-black" onClick={focusVnc}>
          <Suspense fallback={
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <div className="w-10 h-10 mx-auto border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-3" />
                <p className="text-white/45 text-sm">Loading VNC client...</p>
              </div>
            </div>
          }>
            <LazyVncScreen
              key={key}
              ref={vncRef}
              url={vncUrl}
              scaleViewport
              resizeSession
              focusOnClick
              background="#000000"
              style={{ width: '100%', height: '100%' }}
              onConnect={() => { setConnectionStatus('connected'); setError(null); setTimeout(focusVnc, 500); }}
              onDisconnect={(e: any) => {
                setConnectionStatus('disconnected');
                if (e?.detail && !e.detail.clean) setError('VNC connection closed');
              }}
              onSecurityFailure={(e: any) => { setConnectionStatus('disconnected'); setError(e?.detail?.reason || 'Security failure'); }}
            />
          </Suspense>
        </div>
      </div>
    </>
  );
}
