// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';

export interface WSMessage {
  type: string;
  timestamp: string;
  data: Record<string, unknown>;
}

type Listener = (msg: WSMessage) => void;

type WebSocketContextValue = {
  connected: boolean;
  subscribe: (listener: Listener) => () => void;
};

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const listenersRef = useRef(new Set<Listener>());
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);

  const subscribe = useCallback((listener: Listener) => {
    listenersRef.current.add(listener);
    return () => listenersRef.current.delete(listener);
  }, []);

  useEffect(() => {
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let closed = false;

    const connect = () => {
      if (closed) return;
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(`${protocol}//${window.location.host}/api/v1/ws`);

      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!closed) reconnectTimer = setTimeout(connect, 3000);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (event) => {
        try {
          const msg: WSMessage = JSON.parse(event.data);
          listenersRef.current.forEach((listener) => listener(msg));
        } catch {
          /* ignore malformed messages */
        }
      };

      wsRef.current = ws;
    };

    connect();
    return () => {
      closed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, []);

  return (
    <WebSocketContext.Provider value={{ connected, subscribe }}>
      {children}
    </WebSocketContext.Provider>
  );
}

export function useWebSocketSubscription(onMessage: (msg: WSMessage) => void) {
  const ctx = useContext(WebSocketContext);
  if (!ctx) throw new Error('useWebSocketSubscription requires WebSocketProvider');
  const handlerRef = useRef(onMessage);
  handlerRef.current = onMessage;

  useEffect(() => ctx.subscribe((msg) => handlerRef.current(msg)), [ctx]);
}

export function useWebSocketConnected() {
  const ctx = useContext(WebSocketContext);
  return ctx?.connected ?? false;
}
