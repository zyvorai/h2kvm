// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package api

import (
	"context"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os/exec"
	"strconv"
	"strings"
	"sync/atomic"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/gorilla/websocket"
)

// handleVNCProxy bridges a browser WebSocket to a libvirt VM's VNC port.
// The browser connects via ws:///api/v1/vnc-proxy/{vmName} and gets
// a raw RFB (VNC) stream that react-vnc / noVNC can render.
func (s *Server) handleVNCProxy(w http.ResponseWriter, r *http.Request) {
	vmName := chi.URLParam(r, "vmName")

	// Get VNC display from virsh
	out, err := exec.CommandContext(r.Context(), "virsh", "vncdisplay", vmName).Output()
	if err != nil {
		log.Printf("[vnc] no display for %s: %v", vmName, err)
		jsonError(w, http.StatusNotFound, fmt.Sprintf("no VNC display for %s", vmName))
		return
	}

	display := strings.TrimSpace(string(out))
	// Parse :N → port 5900+N, or host:N
	host := "127.0.0.1"
	port := 5900
	if strings.Contains(display, ":") {
		parts := strings.Split(display, ":")
		if len(parts) == 2 && parts[0] != "" {
			host = parts[0]
		}
		n, err := strconv.Atoi(parts[len(parts)-1])
		if err != nil {
			log.Printf("[warn] failed to parse VNC display number %s: %v", parts[len(parts)-1], err)
		}
		port = 5900 + n
	}
	vncAddr := fmt.Sprintf("%s:%d", host, port)

	// Upgrade HTTP → WebSocket
	conn, err := wsUpgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("[vnc] websocket upgrade failed for %s: %v", vmName, err)
		return
	}
	defer conn.Close()

	// Connect to VNC server
	vncConn, err := net.Dial("tcp", vncAddr)
	if err != nil {
		log.Printf("[vnc] failed to connect to %s (%s): %v", vmName, vncAddr, err)
		conn.WriteMessage(websocket.CloseMessage,
			websocket.FormatCloseMessage(websocket.CloseInternalServerErr, "VNC connection failed"))
		return
	}
	defer vncConn.Close()

	log.Printf("[vnc] proxy connected: %s → %s", vmName, vncAddr)

	// VNC → WebSocket (binary frames)
	go func() {
		buf := make([]byte, 65536)
		for {
			n, err := vncConn.Read(buf)
			if err != nil {
				if err != io.EOF {
					log.Printf("[vnc] read error from %s: %v", vmName, err)
				}
				conn.WriteMessage(websocket.CloseMessage, websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""))
				return
			}
			if err := conn.WriteMessage(websocket.BinaryMessage, buf[:n]); err != nil {
				return
			}
		}
	}()

	// WebSocket → VNC
	for {
		_, data, err := conn.ReadMessage()
		if err != nil {
			break
		}
		if _, err := vncConn.Write(data); err != nil {
			break
		}
	}

	log.Printf("[vnc] proxy disconnected: %s", vmName)
}

// portCounter for KubeVirt VNC proxy ports.
var kvVNCPort uint32 = 15900

// handleKubeVirtVNCProxy uses virtctl vnc --proxy-only to create a local
// VNC proxy, then bridges the browser WebSocket to it.
func (s *Server) handleKubeVirtVNCProxy(w http.ResponseWriter, r *http.Request) {
	ns := chi.URLParam(r, "ns")
	vmName := chi.URLParam(r, "vmName")

	// Allocate a port
	port := atomic.AddUint32(&kvVNCPort, 1)
	if port > 15999 {
		atomic.StoreUint32(&kvVNCPort, 15900)
		port = 15900
	}
	portStr := strconv.Itoa(int(port))

	// Start virtctl vnc --proxy-only (no context — long-running, killed via defer).
	cmd := s.virtctlCmd(context.Background(), "vnc", vmName, "-n", ns, "--proxy-only", "--port", portStr)
	if err := cmd.Start(); err != nil {
		log.Printf("[vnc-kv] failed to start virtctl: %v", err)
		jsonError(w, http.StatusInternalServerError, fmt.Sprintf("virtctl vnc failed: %v", err))
		return
	}
	defer func() {
		cmd.Process.Kill()
		cmd.Wait()
	}()

	// Wait for virtctl to start listening
	time.Sleep(2 * time.Second)

	// Connect to virtctl proxy
	vncAddr := fmt.Sprintf("127.0.0.1:%s", portStr)
	vncConn, err := net.DialTimeout("tcp", vncAddr, 3*time.Second)
	if err != nil {
		log.Printf("[vnc-kv] failed to connect to virtctl proxy on %s: %v", vncAddr, err)
		jsonError(w, http.StatusInternalServerError, "virtctl VNC proxy not ready")
		return
	}
	defer vncConn.Close()

	// Upgrade HTTP → WebSocket
	conn, err := wsUpgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("[vnc-kv] websocket upgrade failed: %v", err)
		return
	}
	defer conn.Close()

	log.Printf("[vnc-kv] proxy connected: %s/%s → %s", ns, vmName, vncAddr)

	// VNC → WebSocket
	go func() {
		buf := make([]byte, 65536)
		for {
			n, err := vncConn.Read(buf)
			if err != nil {
				if err != io.EOF {
					log.Printf("[vnc-kv] read error: %v", err)
				}
				conn.WriteMessage(websocket.CloseMessage, websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""))
				return
			}
			if err := conn.WriteMessage(websocket.BinaryMessage, buf[:n]); err != nil {
				return
			}
		}
	}()

	// WebSocket → VNC
	for {
		_, data, err := conn.ReadMessage()
		if err != nil {
			break
		}
		if _, err := vncConn.Write(data); err != nil {
			break
		}
	}

	log.Printf("[vnc-kv] proxy disconnected: %s/%s", ns, vmName)
}
