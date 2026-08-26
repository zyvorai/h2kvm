// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Re-exports shared WebSocket provider — use WebSocketProvider at app root.

export {
  useWebSocketSubscription as useWebSocket,
  useWebSocketConnected,
  type WSMessage,
} from '../contexts/WebSocketContext';
