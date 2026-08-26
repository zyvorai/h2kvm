// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package api

import (
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// MetricsCounters holds atomic counters incremented during normal operation.
type MetricsCounters struct {
	UploadsTotal    atomic.Int64
	UploadBytesTotal atomic.Int64
}

// vmCacheEntry caches virsh list output for a short period.
type vmCacheEntry struct {
	running int
	shutoff int
	other   int
	fetchedAt time.Time
}

var (
	vmCache   vmCacheEntry
	vmCacheMu sync.Mutex
	vmCacheTTL = 10 * time.Second
)

// getVMCounts returns the number of running and shutoff libvirt VMs,
// caching the result for 10 seconds.
func getVMCounts() (running, shutoff, other int) {
	vmCacheMu.Lock()
	defer vmCacheMu.Unlock()

	if time.Since(vmCache.fetchedAt) < vmCacheTTL {
		return vmCache.running, vmCache.shutoff, vmCache.other
	}

	out, err := exec.Command("virsh", "list", "--all").Output()
	if err != nil {
		return 0, 0, 0
	}

	for _, line := range strings.Split(string(out), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "Id") || strings.HasPrefix(line, "---") {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) < 3 {
			continue
		}
		// State is the last field(s): "running", "shut off", "paused", etc.
		state := strings.Join(fields[2:], " ")
		switch state {
		case "running":
			running++
		case "shut off":
			shutoff++
		default:
			other++
		}
	}

	vmCache = vmCacheEntry{
		running:   running,
		shutoff:   shutoff,
		other:     other,
		fetchedAt: time.Now(),
	}
	return running, shutoff, other
}

// getHostCPUCores reads /proc/cpuinfo to count processor entries.
func getHostCPUCores() int {
	data, err := os.ReadFile("/proc/cpuinfo")
	if err != nil {
		return 0
	}
	count := 0
	for _, line := range strings.Split(string(data), "\n") {
		if strings.HasPrefix(line, "processor") {
			count++
		}
	}
	return count
}

// getHostMemoryMB reads /proc/meminfo to get total memory in MB.
func getHostMemoryMB() int64 {
	data, err := os.ReadFile("/proc/meminfo")
	if err != nil {
		return 0
	}
	for _, line := range strings.Split(string(data), "\n") {
		if strings.HasPrefix(line, "MemTotal:") {
			fields := strings.Fields(line)
			if len(fields) >= 2 {
				kB, err := strconv.ParseInt(fields[1], 10, 64)
				if err == nil {
					return kB / 1024
				}
			}
		}
	}
	return 0
}

// handleMetrics writes Prometheus exposition format metrics.
func (s *Server) handleMetrics(w http.ResponseWriter, r *http.Request) {
	var b strings.Builder

	// Job stats from job manager.
	stats := s.manager.Stats()
	b.WriteString("# HELP h2kweb_migrations_total Total migrations submitted\n")
	b.WriteString("# TYPE h2kweb_migrations_total counter\n")
	b.WriteString(fmt.Sprintf("h2kweb_migrations_total{status=\"completed\"} %d\n", stats.Completed))
	b.WriteString(fmt.Sprintf("h2kweb_migrations_total{status=\"failed\"} %d\n", stats.Failed))
	b.WriteString(fmt.Sprintf("h2kweb_migrations_total{status=\"running\"} %d\n", stats.Running))
	b.WriteString(fmt.Sprintf("h2kweb_migrations_total{status=\"pending\"} %d\n", stats.Pending))
	b.WriteString(fmt.Sprintf("h2kweb_migrations_total{status=\"cancelled\"} %d\n", stats.Cancelled))
	b.WriteString("\n")

	// Libvirt VM counts.
	running, shutoff, _ := getVMCounts()
	b.WriteString("# HELP h2kweb_vms_total Total libvirt VMs\n")
	b.WriteString("# TYPE h2kweb_vms_total gauge\n")
	b.WriteString(fmt.Sprintf("h2kweb_vms_total{state=\"running\"} %d\n", running))
	b.WriteString(fmt.Sprintf("h2kweb_vms_total{state=\"shutoff\"} %d\n", shutoff))
	b.WriteString("\n")

	// Upload counters.
	b.WriteString("# HELP h2kweb_uploads_total Total file uploads\n")
	b.WriteString("# TYPE h2kweb_uploads_total counter\n")
	b.WriteString(fmt.Sprintf("h2kweb_uploads_total %d\n", s.metrics.UploadsTotal.Load()))
	b.WriteString("\n")

	b.WriteString("# HELP h2kweb_upload_bytes_total Total bytes uploaded\n")
	b.WriteString("# TYPE h2kweb_upload_bytes_total counter\n")
	b.WriteString(fmt.Sprintf("h2kweb_upload_bytes_total %d\n", s.metrics.UploadBytesTotal.Load()))
	b.WriteString("\n")

	// Webhooks registered.
	s.webhookMu.RLock()
	webhookCount := len(s.webhooks)
	s.webhookMu.RUnlock()
	b.WriteString("# HELP h2kweb_webhooks_registered Number of registered webhooks\n")
	b.WriteString("# TYPE h2kweb_webhooks_registered gauge\n")
	b.WriteString(fmt.Sprintf("h2kweb_webhooks_registered %d\n", webhookCount))
	b.WriteString("\n")

	// Host info.
	cpuCores := getHostCPUCores()
	memMB := getHostMemoryMB()
	b.WriteString("# HELP h2kweb_host_cpu_cores Number of CPU cores\n")
	b.WriteString("# TYPE h2kweb_host_cpu_cores gauge\n")
	b.WriteString(fmt.Sprintf("h2kweb_host_cpu_cores %d\n", cpuCores))
	b.WriteString("\n")

	b.WriteString("# HELP h2kweb_host_memory_total_mb Total memory in MB\n")
	b.WriteString("# TYPE h2kweb_host_memory_total_mb gauge\n")
	b.WriteString(fmt.Sprintf("h2kweb_host_memory_total_mb %d\n", memMB))
	b.WriteString("\n")

	// WebSocket clients.
	wsClients := 0
	if s.wsHub != nil {
		wsClients = s.wsHub.ClientCount()
	}
	b.WriteString("# HELP h2kweb_websocket_clients Current WebSocket connections\n")
	b.WriteString("# TYPE h2kweb_websocket_clients gauge\n")
	b.WriteString(fmt.Sprintf("h2kweb_websocket_clients %d\n", wsClients))
	b.WriteString("\n")

	w.Header().Set("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	w.Write([]byte(b.String()))
}
