// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package api

import (
	"context"
	"fmt"
	"html"
	"log"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
)

// --- Network CRUD Management ---

// handleCreateNetwork creates a new libvirt network.
//
// POST /api/v1/networks
// Body: {"name": "mynet", "bridge": "virbr1", "forward": "nat", "subnet": "192.168.100.0",
//        "netmask": "255.255.255.0", "dhcp_start": "192.168.100.100", "dhcp_end": "192.168.100.200"}
func (s *Server) handleCreateNetwork(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Name      string `json:"name"`
		Bridge    string `json:"bridge"`
		Forward   string `json:"forward"`
		Subnet    string `json:"subnet"`
		Netmask   string `json:"netmask"`
		DHCPStart string `json:"dhcp_start"`
		DHCPEnd   string `json:"dhcp_end"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	safeName := safeNameRe.ReplaceAllString(req.Name, "")
	if safeName == "" || safeName != req.Name {
		jsonError(w, http.StatusBadRequest, "invalid network name: only alphanumeric, dash, underscore, dot allowed")
		return
	}

	// Validate forward mode.
	forward := req.Forward
	if forward == "" {
		forward = "nat"
	}
	validModes := map[string]bool{"nat": true, "route": true, "bridge": true, "none": true}
	if !validModes[forward] {
		jsonError(w, http.StatusBadRequest, "forward must be one of: nat, route, bridge, none")
		return
	}

	// Build bridge name.
	bridge := req.Bridge
	if bridge == "" {
		bridge = "virbr-" + safeName
	}
	safeBridge := safeNameRe.ReplaceAllString(bridge, "")
	if safeBridge == "" || safeBridge != bridge {
		jsonError(w, http.StatusBadRequest, "invalid bridge name")
		return
	}

	log.Printf("[network] createNetwork name=%s forward=%s bridge=%s subnet=%s from %s",
		safeName, forward, bridge, req.Subnet, r.RemoteAddr)

	// Build network XML. Escape all user-supplied values to prevent XML injection.
	var xmlParts []string
	xmlParts = append(xmlParts, "<network>")
	xmlParts = append(xmlParts, fmt.Sprintf("  <name>%s</name>", html.EscapeString(safeName)))

	if forward != "none" {
		xmlParts = append(xmlParts, fmt.Sprintf("  <forward mode='%s'/>", html.EscapeString(forward)))
	}

	xmlParts = append(xmlParts, fmt.Sprintf("  <bridge name='%s' stp='on' delay='0'/>", html.EscapeString(safeBridge)))

	if req.Subnet != "" && req.Netmask != "" {
		xmlParts = append(xmlParts, fmt.Sprintf("  <ip address='%s' netmask='%s'>", html.EscapeString(req.Subnet), html.EscapeString(req.Netmask)))
		if req.DHCPStart != "" && req.DHCPEnd != "" {
			xmlParts = append(xmlParts, "    <dhcp>")
			xmlParts = append(xmlParts, fmt.Sprintf("      <range start='%s' end='%s'/>", html.EscapeString(req.DHCPStart), html.EscapeString(req.DHCPEnd)))
			xmlParts = append(xmlParts, "    </dhcp>")
		}
		xmlParts = append(xmlParts, "  </ip>")
	}

	xmlParts = append(xmlParts, "</network>")
	netXML := strings.Join(xmlParts, "\n")

	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()

	// Write XML to temp file.
	tmpFile, err := os.CreateTemp("", "h2kweb-net-*.xml")
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to create temp file")
		return
	}
	defer os.Remove(tmpFile.Name())

	if _, err := tmpFile.WriteString(netXML); err != nil {
		tmpFile.Close()
		jsonError(w, http.StatusInternalServerError, "failed to write network XML")
		return
	}
	tmpFile.Close()

	// Define the network.
	defineOut, err := exec.CommandContext(ctx, "virsh", "net-define", tmpFile.Name()).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("virsh net-define failed: %s", strings.TrimSpace(string(defineOut))))
		return
	}

	// Start the network.
	startOut, err := exec.CommandContext(ctx, "virsh", "net-start", safeName).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("virsh net-start failed: %s", strings.TrimSpace(string(startOut))))
		return
	}

	// Enable autostart.
	autostartOut, err := exec.CommandContext(ctx, "virsh", "net-autostart", safeName).CombinedOutput()
	if err != nil {
		log.Printf("[network] net-autostart warning: %s", strings.TrimSpace(string(autostartOut)))
	}

	log.Printf("[network] createNetwork name=%s succeeded", safeName)
	s.auditLog(r, "network_create", safeName, fmt.Sprintf("forward=%s bridge=%s", forward, bridge))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": fmt.Sprintf("Network %s created and started", safeName),
		"name":    safeName,
		"forward": forward,
		"bridge":  bridge,
	})
}

// handleDeleteNetwork destroys and undefines a libvirt network.
//
// DELETE /api/v1/networks/{name}
func (s *Server) handleDeleteNetwork(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "name")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid network name")
		return
	}

	log.Printf("[network] deleteNetwork name=%s from %s", safeName, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()

	// Destroy (stop) the network first.
	destroyOut, err := exec.CommandContext(ctx, "virsh", "net-destroy", safeName).CombinedOutput()
	if err != nil {
		log.Printf("[network] net-destroy warning: %s", strings.TrimSpace(string(destroyOut)))
		// Not fatal -- network might already be stopped.
	}

	// Undefine the network.
	undefOut, err := exec.CommandContext(ctx, "virsh", "net-undefine", safeName).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("virsh net-undefine failed: %s", strings.TrimSpace(string(undefOut))))
		return
	}

	log.Printf("[network] deleteNetwork name=%s succeeded", safeName)
	s.auditLog(r, "network_delete", safeName)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": fmt.Sprintf("Network %s deleted", safeName),
	})
}
