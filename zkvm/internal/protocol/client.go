// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package protocol

import (
	"bufio"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// Client manages a Unix socket connection to the Python backend.
type Client struct {
	socketPath string
	conn       net.Conn
	reader     *bufio.Reader
	mu         sync.Mutex
	connected  bool

	// EventCh receives server-pushed events.
	EventCh chan Envelope

	// reconnect settings
	reconnectDelay time.Duration
	maxRetries     int
}

// DefaultSocketPath returns the default socket path based on whether
// the process is running as root or a regular user.
func DefaultSocketPath() string {
	if os.Getuid() == 0 {
		return "/run/hyper2kvm/zkvm.sock"
	}
	xdg := os.Getenv("XDG_RUNTIME_DIR")
	if xdg == "" {
		xdg = fmt.Sprintf("/run/user/%d", os.Getuid())
	}
	return filepath.Join(xdg, "hyper2kvm", "zkvm.sock")
}

// NewClient creates a new socket client.
func NewClient(socketPath string) *Client {
	if socketPath == "" {
		socketPath = DefaultSocketPath()
	}
	return &Client{
		socketPath:     socketPath,
		EventCh:        make(chan Envelope, 64),
		reconnectDelay: 2 * time.Second,
		maxRetries:     5,
	}
}

// Connect establishes a connection to the Unix socket.
func (c *Client) Connect() error {
	c.mu.Lock()
	defer c.mu.Unlock()

	conn, err := net.DialTimeout("unix", c.socketPath, 5*time.Second)
	if err != nil {
		return fmt.Errorf("connect to %s: %w", c.socketPath, err)
	}

	c.conn = conn
	c.reader = bufio.NewReader(conn)
	c.connected = true

	// Start reading events in background
	go c.readLoop()

	return nil
}

// ConnectWithRetry tries to connect with retries.
func (c *Client) ConnectWithRetry() error {
	var lastErr error
	for i := 0; i < c.maxRetries; i++ {
		if err := c.Connect(); err != nil {
			lastErr = err
			time.Sleep(c.reconnectDelay)
			continue
		}
		return nil
	}
	return fmt.Errorf("failed after %d retries: %w", c.maxRetries, lastErr)
}

// Close closes the connection.
func (c *Client) Close() error {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.connected = false
	if c.conn != nil {
		return c.conn.Close()
	}
	return nil
}

// IsConnected returns whether the client is connected.
func (c *Client) IsConnected() bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.connected
}

// SocketPath returns the socket path this client connects to.
func (c *Client) SocketPath() string {
	return c.socketPath
}

// Send sends a request and returns the response.
func (c *Client) Send(req Request) (*Response, error) {
	c.mu.Lock()
	if !c.connected || c.conn == nil {
		c.mu.Unlock()
		return nil, fmt.Errorf("not connected")
	}

	data, err := json.Marshal(req)
	if err != nil {
		c.mu.Unlock()
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	// Append newline delimiter
	data = append(data, '\n')

	_, err = c.conn.Write(data)
	c.mu.Unlock()

	if err != nil {
		return nil, fmt.Errorf("write request: %w", err)
	}

	// Response will come through the readLoop as an envelope with success field.
	// For simplicity, we return nil here and let the caller listen on EventCh.
	return nil, nil
}

// SendFireAndForget sends a request without waiting for response.
func (c *Client) SendFireAndForget(req Request) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	if !c.connected || c.conn == nil {
		return fmt.Errorf("not connected")
	}

	data, err := json.Marshal(req)
	if err != nil {
		return fmt.Errorf("marshal request: %w", err)
	}

	data = append(data, '\n')
	_, err = c.conn.Write(data)
	return err
}

// readLoop continuously reads JSON messages from the socket.
func (c *Client) readLoop() {
	for {
		c.mu.Lock()
		if !c.connected {
			c.mu.Unlock()
			return
		}
		reader := c.reader
		c.mu.Unlock()

		line, err := reader.ReadBytes('\n')
		if err != nil {
			c.mu.Lock()
			c.connected = false
			c.mu.Unlock()
			// Signal disconnect
			c.EventCh <- Envelope{Type: "_disconnected"}
			return
		}

		var env Envelope
		if err := json.Unmarshal(line, &env); err != nil {
			continue // skip malformed messages
		}

		// Non-blocking send to event channel
		select {
		case c.EventCh <- env:
		default:
			// Drop if channel is full
		}
	}
}
