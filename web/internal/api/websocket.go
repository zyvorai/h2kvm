// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package api

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

// WSMessage represents a WebSocket message.
type WSMessage struct {
	Type      string                 `json:"type"`
	Timestamp time.Time              `json:"timestamp"`
	Data      map[string]interface{} `json:"data"`
}

// WSClient represents a connected WebSocket client.
type WSClient struct {
	conn      *websocket.Conn
	send      chan WSMessage
	hub       *WSHub
	closeOnce sync.Once
}

// WSHub manages WebSocket clients and broadcasts.
// Adapted from hypersdk/daemon/api/websocket.go.
type WSHub struct {
	clients    map[*WSClient]bool
	broadcast  chan WSMessage
	register   chan *WSClient
	unregister chan *WSClient
	mu         sync.RWMutex

	// OnBroadcast is an optional hook called on every broadcast (e.g., for webhook firing).
	OnBroadcast func(msgType string, data map[string]interface{})
}

// NewWSHub creates a new WebSocket hub.
func NewWSHub() *WSHub {
	return &WSHub{
		clients:    make(map[*WSClient]bool),
		broadcast:  make(chan WSMessage, 256),
		register:   make(chan *WSClient),
		unregister: make(chan *WSClient),
	}
}

// Run starts the hub event loop. Call in a goroutine.
func (h *WSHub) Run(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			return

		case client := <-h.register:
			h.mu.Lock()
			h.clients[client] = true
			h.mu.Unlock()
			log.Printf("[ws] client connected (total: %d)", len(h.clients))

		case client := <-h.unregister:
			h.mu.Lock()
			if _, ok := h.clients[client]; ok {
				delete(h.clients, client)
				client.closeOnce.Do(func() { close(client.send) })
			}
			h.mu.Unlock()
			log.Printf("[ws] client disconnected (total: %d)", len(h.clients))

		case message := <-h.broadcast:
			h.mu.RLock()
			clientCount := len(h.clients)
			var stale []*WSClient
			for client := range h.clients {
				select {
				case client.send <- message:
				default:
					stale = append(stale, client)
				}
			}
			h.mu.RUnlock()

			if len(stale) > 0 {
				log.Printf("[ws] broadcast type=%s to %d clients, %d dropped (buffer full)", message.Type, clientCount, len(stale))
			}

			for _, client := range stale {
				h.unregister <- client
			}
		}
	}
}

// Broadcast sends a typed message to all connected clients.
// Implements ports.EventBroadcaster.
func (h *WSHub) Broadcast(msgType string, data map[string]interface{}) {
	message := WSMessage{
		Type:      msgType,
		Timestamp: time.Now(),
		Data:      data,
	}
	select {
	case h.broadcast <- message:
	default:
		log.Printf("[ws] broadcast channel full, dropping %s", msgType)
	}

	// Fire the broadcast hook (used for webhooks).
	if h.OnBroadcast != nil {
		h.OnBroadcast(msgType, data)
	}
}

// ClientCount returns the number of connected clients.
func (h *WSHub) ClientCount() int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.clients)
}

// Shutdown closes all client connections.
func (h *WSHub) Shutdown() {
	h.mu.Lock()
	defer h.mu.Unlock()
	for client := range h.clients {
		client.closeOnce.Do(func() { close(client.send) })
		client.conn.Close()
	}
	h.clients = make(map[*WSClient]bool)
}

// readPump reads messages from the WebSocket connection.
func (c *WSClient) readPump(ctx context.Context) {
	defer func() {
		c.hub.unregister <- c
		c.conn.Close()
	}()

	c.conn.SetReadDeadline(time.Now().Add(60 * time.Second))
	c.conn.SetPongHandler(func(string) error {
		c.conn.SetReadDeadline(time.Now().Add(60 * time.Second))
		return nil
	})

	for {
		select {
		case <-ctx.Done():
			return
		default:
			_, _, err := c.conn.ReadMessage()
			if err != nil {
				return
			}
		}
	}
}

// writePump sends messages from the hub to the WebSocket connection.
func (c *WSClient) writePump(ctx context.Context) {
	ticker := time.NewTicker(54 * time.Second)
	defer func() {
		ticker.Stop()
		c.conn.Close()
	}()

	for {
		select {
		case <-ctx.Done():
			return

		case message, ok := <-c.send:
			c.conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if !ok {
				c.conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}

			w, err := c.conn.NextWriter(websocket.TextMessage)
			if err != nil {
				return
			}
			if err := json.NewEncoder(w).Encode(message); err != nil {
				return
			}
			w.Close()

		case <-ticker.C:
			c.conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if err := c.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}

// upgrader for WebSocket connections.
var wsUpgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	CheckOrigin: func(r *http.Request) bool {
		return true // Allow all origins in development; restrict in production.
	},
}
