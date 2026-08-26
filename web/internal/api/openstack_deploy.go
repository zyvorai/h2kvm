// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package api

import (
	"context"
	"encoding/json"
	"os/exec"
	"strings"
	"time"
)

// openStackServerRow matches `openstack server list -f json` entries.
type openStackServerRow struct {
	ID     string `json:"ID"`
	Name   string `json:"Name"`
	Status string `json:"Status"`
}

func openstackCLIAvailable(ctx context.Context) bool {
	ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	_, err := exec.CommandContext(ctx, "openstack", "--version").Output()
	return err == nil
}

func openstackImageStatus(ctx context.Context, name string) map[string]interface{} {
	out := map[string]interface{}{"defined": false, "running": false}
	if name == "" {
		return out
	}
	ctx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "openstack", "image", "show", name, "-f", "value", "-c", "status", "-c", "id")
	raw, err := cmd.Output()
	if err != nil {
		return out
	}
	lines := strings.Split(strings.TrimSpace(string(raw)), "\n")
	status := ""
	id := ""
	if len(lines) > 0 {
		status = strings.TrimSpace(lines[0])
	}
	if len(lines) > 1 {
		id = strings.TrimSpace(lines[1])
	}
	if status == "" {
		return out
	}
	active := strings.EqualFold(status, "active")
	out["defined"] = true
	out["running"] = active
	out["status"] = status
	if id != "" {
		out["image_id"] = id
	}
	return out
}

func openstackServerStatus(ctx context.Context, names ...string) map[string]interface{} {
	out := map[string]interface{}{"defined": false, "running": false}
	seen := make(map[string]struct{})
	for _, name := range names {
		name = strings.TrimSpace(name)
		if name == "" {
			continue
		}
		if _, ok := seen[name]; ok {
			continue
		}
		seen[name] = struct{}{}

		ctx, cancel := context.WithTimeout(ctx, 15*time.Second)
		cmd := exec.CommandContext(ctx, "openstack", "server", "list", "--name", name, "-f", "json")
		raw, err := cmd.Output()
		cancel()
		if err != nil || len(raw) == 0 {
			continue
		}

		var rows []openStackServerRow
		if err := json.Unmarshal(raw, &rows); err != nil {
			continue
		}
		for _, row := range rows {
			if row.Name != name {
				continue
			}
			status := strings.ToUpper(strings.TrimSpace(row.Status))
			out["defined"] = true
			out["running"] = status == "ACTIVE"
			out["status"] = row.Status
			if row.ID != "" {
				out["server_id"] = row.ID
			}
			out["server_name"] = row.Name
			return out
		}
	}
	return out
}

func openstackServerIPs(ctx context.Context, names ...string) ([]string, string) {
	seen := make(map[string]struct{})
	for _, name := range names {
		name = strings.TrimSpace(name)
		if name == "" {
			continue
		}
		if _, ok := seen[name]; ok {
			continue
		}
		seen[name] = struct{}{}

		ctx, cancel := context.WithTimeout(ctx, 15*time.Second)
		cmd := exec.CommandContext(ctx, "openstack", "server", "show", name, "-f", "json", "-c", "addresses")
		raw, err := cmd.Output()
		cancel()
		if err != nil || len(raw) == 0 {
			continue
		}

		var payload struct {
			Addresses map[string][]struct {
				Addr string `json:"addr"`
			} `json:"addresses"`
		}
		if err := json.Unmarshal(raw, &payload); err != nil {
			continue
		}
		var ips []string
		ipSeen := make(map[string]struct{})
		for _, nets := range payload.Addresses {
			for _, a := range nets {
				addr := strings.TrimSpace(a.Addr)
				if addr == "" {
					continue
				}
				if _, dup := ipSeen[addr]; dup {
					continue
				}
				ipSeen[addr] = struct{}{}
				ips = append(ips, addr)
			}
		}
		if len(ips) > 0 {
			return ips, "openstack"
		}
	}
	return nil, ""
}

func queryOpenStackDeployStatus(ctx context.Context, vmName string) map[string]interface{} {
	image := openstackImageStatus(ctx, vmName)
	server := openstackServerStatus(ctx, vmName, vmName+"-instance")
	if server["defined"] == true {
		return server
	}
	return image
}
