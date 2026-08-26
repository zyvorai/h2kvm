// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"fmt"
	"os/exec"
	"strings"
	"sync"
	"time"
)

// WebConsole manages a websockify proxy for noVNC access.
type WebConsole struct {
	mu       sync.Mutex
	cmd      *exec.Cmd
	vmName   string
	vncPort  int
	wsPort   int
	url      string
	running  bool
}

// nextWSPort tracks the next websocket port for multiple web consoles.
var nextWSPort = 6080

// StartWebConsole launches websockify to proxy VNC and returns the noVNC URL.
// Auto-installs websockify + noVNC if not present.
func StartWebConsole(vmName string, vncHost string, vncPort int) (*WebConsole, error) {
	wsPort := nextWSPort
	nextWSPort++

	// Ensure websockify + noVNC are installed.
	wsPath, _ := exec.LookPath("websockify")
	novncDir := findNoVNCDir()

	if wsPath == "" || novncDir == "" {
		_, installErr := installNoVNCPackages()
		if installErr != nil {
			return nil, fmt.Errorf("failed to auto-install websockify/noVNC: %w — install manually: sudo dnf install python3-websockify novnc (Fedora/RHEL) or sudo apt install websockify novnc (Debian/Ubuntu)", installErr)
		}
		wsPath, _ = exec.LookPath("websockify")
		novncDir = findNoVNCDir()
		if wsPath == "" {
			return nil, fmt.Errorf("websockify binary not found in PATH after install — try restarting your shell or install manually: pip3 install websockify")
		}
	}

	target := fmt.Sprintf("%s:%d", vncHost, vncPort)

	var args []string
	if novncDir != "" {
		args = []string{"--web=" + novncDir, fmt.Sprintf("%d", wsPort), target}
	} else {
		args = []string{fmt.Sprintf("%d", wsPort), target}
	}

	cmd := exec.Command(wsPath, args...)
	cmd.Stdout = nil
	cmd.Stderr = nil
	cmd.Stdin = nil

	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("failed to start websockify for VM %q (proxying VNC port %d to web port %d): %w — verify websockify is installed and port %d is not already in use", vmName, vncPort, wsPort, err, wsPort)
	}

	url := fmt.Sprintf("http://localhost:%d/vnc.html?host=localhost&port=%d&autoconnect=true", wsPort, wsPort)

	wc := &WebConsole{
		cmd:     cmd,
		vmName:  vmName,
		vncPort: vncPort,
		wsPort:  wsPort,
		url:     url,
		running: true,
	}

	// Try to open the browser automatically.
	openBrowser(url)

	return wc, nil
}

// Stop kills the websockify proxy.
func (wc *WebConsole) Stop() {
	wc.mu.Lock()
	defer wc.mu.Unlock()
	if wc.running && wc.cmd != nil && wc.cmd.Process != nil {
		wc.cmd.Process.Kill()
		// Wait with timeout to avoid blocking forever
		done := make(chan struct{})
		go func() {
			wc.cmd.Wait()
			close(done)
		}()
		select {
		case <-done:
		case <-time.After(2 * time.Second):
			// Timeout waiting for process to exit
		}
		wc.running = false
	}
}

// IsRunning returns whether the proxy is active.
func (wc *WebConsole) IsRunning() bool {
	wc.mu.Lock()
	defer wc.mu.Unlock()
	return wc.running
}

// URL returns the noVNC URL.
func (wc *WebConsole) URL() string {
	return wc.url
}

// VMName returns the connected VM name.
func (wc *WebConsole) VMName() string {
	return wc.vmName
}

// VNCPort returns the VNC port being proxied.
func (wc *WebConsole) VNCPort() int {
	return wc.vncPort
}

// WSPort returns the websocket port.
func (wc *WebConsole) WSPort() int {
	return wc.wsPort
}

// openBrowser tries to open a URL in the default browser.
func openBrowser(url string) {
	// Try common openers in order.
	for _, opener := range []string{"xdg-open", "open", "sensible-browser"} {
		if path, err := exec.LookPath(opener); err == nil {
			cmd := exec.Command(path, url)
			cmd.Stdout = nil
			cmd.Stderr = nil
			cmd.Stdin = nil
			if cmd.Start() == nil {
				// Intentional fire-and-forget: reap the child process to avoid
				// zombies. The goroutine exits when the subprocess does.
				go cmd.Wait()
			}
			return
		}
	}
}

// LaunchViewer launches an external graphical viewer for a VM.
// It tries viewers in order: virt-viewer, remote-viewer, vncviewer.
func LaunchViewer(vmName string, host string, port int, gfxType string) error {
	// 1. Try virt-viewer — best for libvirt VMs, handles VNC/SPICE automatically.
	if path, err := exec.LookPath("virt-viewer"); err == nil {
		cmd := exec.Command(path, vmName)
		cmd.Stdout = nil
		cmd.Stderr = nil
		cmd.Stdin = nil
		if err := cmd.Start(); err != nil {
			return fmt.Errorf("failed to launch virt-viewer for VM %q: %w", vmName, err)
		}
		// Intentional fire-and-forget: reap the child process to avoid
		// zombies. The goroutine exits when the subprocess does.
		go cmd.Wait()
		return nil
	}

	// 2. Try remote-viewer with protocol-specific URI.
	if path, err := exec.LookPath("remote-viewer"); err == nil {
		var uri string
		if gfxType == "spice" {
			uri = fmt.Sprintf("spice://%s:%d", host, port)
		} else {
			uri = fmt.Sprintf("vnc://%s:%d", host, port)
		}
		cmd := exec.Command(path, uri)
		cmd.Stdout = nil
		cmd.Stderr = nil
		cmd.Stdin = nil
		if err := cmd.Start(); err != nil {
			return fmt.Errorf("failed to launch remote-viewer for VM %q at %s: %w", vmName, uri, err)
		}
		// Intentional fire-and-forget: reap the child process to avoid
		// zombies. The goroutine exits when the subprocess does.
		go cmd.Wait()
		return nil
	}

	// 3. Try vncviewer (TigerVNC) — VNC only.
	if gfxType != "spice" {
		if path, err := exec.LookPath("vncviewer"); err == nil {
			target := fmt.Sprintf("%s:%d", host, port)
			cmd := exec.Command(path, target)
			cmd.Stdout = nil
			cmd.Stderr = nil
			cmd.Stdin = nil
			if err := cmd.Start(); err != nil {
				return fmt.Errorf("failed to launch vncviewer for VM %q at %s: %w", vmName, target, err)
			}
			// Intentional fire-and-forget: reap the child process to avoid
			// zombies. The goroutine exits when the subprocess does.
			go cmd.Wait()
			return nil
		}
	}

	return fmt.Errorf("no graphical viewer found — install one of: virt-viewer (recommended, sudo dnf install virt-viewer), remote-viewer (sudo dnf install virt-viewer), or vncviewer (sudo dnf install tigervnc)")
}

// connectionInfo returns a formatted string with connection details.
func connectionInfo(wc *WebConsole) string {
	var b strings.Builder

	b.WriteString(fmt.Sprintf("  VM:           %s\n", wc.VMName()))
	b.WriteString(fmt.Sprintf("  VNC Port:     %d\n", wc.VNCPort()))
	b.WriteString(fmt.Sprintf("  WebSocket:    localhost:%d\n", wc.WSPort()))
	b.WriteString(fmt.Sprintf("\n  noVNC URL:\n"))
	b.WriteString(fmt.Sprintf("  %s\n", wc.URL()))
	b.WriteString(fmt.Sprintf("\n  For SSH tunneling:\n"))
	b.WriteString(fmt.Sprintf("  ssh -L %d:localhost:%d <host>\n", wc.WSPort(), wc.WSPort()))

	return b.String()
}
