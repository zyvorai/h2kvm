// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package api

import (
	"bufio"
	"bytes"
	"context"
	"crypto/rand"
	"crypto/tls"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math"
	"net"
	"net/http"
	"net/smtp"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"gopkg.in/yaml.v3"

	"github.com/hyper2kvm/web/internal/domain"
	"github.com/hyper2kvm/web/internal/ports"
	"github.com/hyper2kvm/web/internal/registry"
)

// AuditEntry represents a single audit log entry.
type AuditEntry struct {
	Timestamp string `json:"timestamp"`
	User      string `json:"user"`
	Action    string `json:"action"`
	Target    string `json:"target"`
	Result    string `json:"result"`
	RemoteIP  string `json:"remote_ip"`
}

// WebhookRegistration represents a registered webhook.
type WebhookRegistration struct {
	ID     string   `json:"id"`
	URL    string   `json:"url"`
	Events []string `json:"events,omitempty"` // empty means all events
}

// WebhookPayload is sent to registered webhooks.
type WebhookPayload struct {
	Event     string `json:"event"`
	JobID     string `json:"job_id,omitempty"`
	Status    string `json:"status,omitempty"`
	VMName    string `json:"vm_name,omitempty"`
	Timestamp string `json:"timestamp"`
}

// EmailConfig holds SMTP configuration for email notifications.
type EmailConfig struct {
	Host        string   `json:"host"`
	Port        int      `json:"port"`
	From        string   `json:"from"`
	Username    string   `json:"username"`
	Password    string   `json:"password"`
	ToAddresses []string `json:"to_addresses"`
}

// Server is the main HTTP API server.
type Server struct {
	router     chi.Router
	httpServer *http.Server
	wsHub      *WSHub
	manager    ports.JobManager
	registry   *registry.Registry
	sessions   *SessionStore
	apiKey     string
	ctx        context.Context
	cancel     context.CancelFunc
	staticDir  string // absolute path to dashboard/dist
	tlsCert    string // TLS cert file path
	tlsKey     string // TLS key file path

	// Audit log (in-memory, last 500 entries).
	auditMu      sync.RWMutex
	auditEntries []AuditEntry

	// Webhook registrations.
	webhookMu    sync.RWMutex
	webhooks     []WebhookRegistration

	// Email notification config.
	emailMu     sync.RWMutex
	emailConfig *EmailConfig

	// Prometheus metrics counters.
	metrics MetricsCounters

	// Multi-kubeconfig manager.
	kubeconfigMgr *KubeconfigManager

	// Auto-cleanup state.
	cleanup *cleanupState
}

const webhookPersistPath = "/var/lib/hyper2kvm/webhooks.json"
const emailPersistPath = "/var/lib/hyper2kvm/email.json"

// loadWebhooks reads persisted webhooks from disk. Missing or corrupt files
// are handled gracefully (server starts with an empty list).
func (s *Server) loadWebhooks() {
	data, err := os.ReadFile(webhookPersistPath)
	if err != nil {
		// File does not exist yet -- normal on first run.
		return
	}

	var hooks []WebhookRegistration
	if err := json.Unmarshal(data, &hooks); err != nil {
		log.Printf("[webhooks] corrupt %s, starting with empty list: %v", webhookPersistPath, err)
		return
	}

	s.webhookMu.Lock()
	s.webhooks = hooks
	s.webhookMu.Unlock()
	log.Printf("[webhooks] loaded %d webhook(s) from %s", len(hooks), webhookPersistPath)
}

// saveWebhooks persists the current webhook list to disk. Must be called
// while webhookMu is held (at least RLock).
func (s *Server) saveWebhooks() {
	data, err := json.MarshalIndent(s.webhooks, "", "  ")
	if err != nil {
		log.Printf("[webhooks] marshal error: %v", err)
		return
	}

	dir := filepath.Dir(webhookPersistPath)
	if err := os.MkdirAll(dir, 0755); err != nil {
		log.Printf("[webhooks] cannot create %s: %v", dir, err)
		return
	}

	if err := os.WriteFile(webhookPersistPath, data, 0644); err != nil {
		log.Printf("[webhooks] write %s failed: %v", webhookPersistPath, err)
	}
}

// loadEmailConfig reads persisted email config from disk.
func (s *Server) loadEmailConfig() {
	data, err := os.ReadFile(emailPersistPath)
	if err != nil {
		return
	}

	var cfg EmailConfig
	if err := json.Unmarshal(data, &cfg); err != nil {
		log.Printf("[email] corrupt %s, starting without config: %v", emailPersistPath, err)
		return
	}

	s.emailMu.Lock()
	s.emailConfig = &cfg
	s.emailMu.Unlock()
	log.Printf("[email] loaded config from %s (host=%s, to=%d recipients)", emailPersistPath, cfg.Host, len(cfg.ToAddresses))
}

// saveEmailConfig persists the email config to disk. Must be called
// while emailMu is held (at least RLock).
func (s *Server) saveEmailConfig() {
	data, err := json.MarshalIndent(s.emailConfig, "", "  ")
	if err != nil {
		log.Printf("[email] marshal error: %v", err)
		return
	}

	dir := filepath.Dir(emailPersistPath)
	if err := os.MkdirAll(dir, 0755); err != nil {
		log.Printf("[email] cannot create %s: %v", dir, err)
		return
	}

	if err := os.WriteFile(emailPersistPath, data, 0600); err != nil {
		log.Printf("[email] write %s failed: %v", emailPersistPath, err)
	}
}

// sendEmailNotification sends an email notification asynchronously.
func (s *Server) sendEmailNotification(subject, body string) {
	s.emailMu.RLock()
	cfg := s.emailConfig
	s.emailMu.RUnlock()

	if cfg == nil || cfg.Host == "" || len(cfg.ToAddresses) == 0 {
		return
	}

	log.Printf("[email] sending notification: subject=%q to=%d recipients", subject, len(cfg.ToAddresses))

	go func() {
		if err := sendEmail(cfg, subject, body); err != nil {
			log.Printf("[email] send FAILED: subject=%q error=%v", subject, err)
		} else {
			log.Printf("[email] send SUCCESS: subject=%q to=%v", subject, cfg.ToAddresses)
		}
	}()
}

// sendEmail sends an email using the provided SMTP configuration.
func sendEmail(cfg *EmailConfig, subject, body string) error {
	addr := fmt.Sprintf("%s:%d", cfg.Host, cfg.Port)

	msg := fmt.Sprintf("From: %s\r\nTo: %s\r\nSubject: %s\r\nMIME-Version: 1.0\r\nContent-Type: text/plain; charset=UTF-8\r\n\r\n%s",
		cfg.From,
		strings.Join(cfg.ToAddresses, ", "),
		subject,
		body,
	)

	var auth smtp.Auth
	if cfg.Username != "" {
		auth = smtp.PlainAuth("", cfg.Username, cfg.Password, cfg.Host)
	}

	// Use TLS for port 465, STARTTLS for others.
	if cfg.Port == 465 {
		tlsConfig := &tls.Config{ServerName: cfg.Host}
		conn, err := tls.Dial("tcp", addr, tlsConfig)
		if err != nil {
			return fmt.Errorf("TLS dial: %w", err)
		}
		defer conn.Close()

		client, err := smtp.NewClient(conn, cfg.Host)
		if err != nil {
			return fmt.Errorf("SMTP client: %w", err)
		}
		defer client.Close()

		if auth != nil {
			if err := client.Auth(auth); err != nil {
				return fmt.Errorf("auth: %w", err)
			}
		}

		if err := client.Mail(cfg.From); err != nil {
			return fmt.Errorf("MAIL FROM: %w", err)
		}
		for _, to := range cfg.ToAddresses {
			if err := client.Rcpt(to); err != nil {
				return fmt.Errorf("RCPT TO %s: %w", to, err)
			}
		}
		w, err := client.Data()
		if err != nil {
			return fmt.Errorf("DATA: %w", err)
		}
		w.Write([]byte(msg))
		w.Close()
		return client.Quit()
	}

	return smtp.SendMail(addr, auth, cfg.From, cfg.ToAddresses, []byte(msg))
}

// ServerConfig holds configuration for the API server.
type ServerConfig struct {
	Addr      string
	APIKey    string
	StaticDir string // path to dashboard/dist (default: auto-detect)
	TLSCert   string // path to TLS cert file (empty = HTTP, "auto" = self-signed)
	TLSKey    string // path to TLS key file
}

// NewServer creates a new API server with all dependencies wired.
func NewServer(cfg ServerConfig, manager ports.JobManager, reg *registry.Registry, wsHub *WSHub) *Server {
	ctx, cancel := context.WithCancel(context.Background())

	// Resolve static dir.
	staticDir := cfg.StaticDir
	if staticDir == "" {
		// Auto-detect: look relative to the binary, then CWD.
		exe, _ := os.Executable()
		exeDir := filepath.Dir(exe)
		candidates := []string{
			filepath.Join(exeDir, "dashboard", "dist"),
			"dashboard/dist",
		}
		for _, c := range candidates {
			if info, err := os.Stat(c); err == nil && info.IsDir() {
				staticDir, _ = filepath.Abs(c)
				break
			}
		}
	}

	// Log resolved configuration (mask sensitive values).
	maskedKey := "(not set)"
	if cfg.APIKey != "" {
		maskedKey = cfg.APIKey[:min(3, len(cfg.APIKey))] + "***"
	}
	log.Printf("[api] NewServer config: addr=%s staticDir=%s tlsCert=%s apiKey=%s", cfg.Addr, staticDir, cfg.TLSCert, maskedKey)

	s := &Server{
		wsHub:     wsHub,
		manager:   manager,
		registry:  reg,
		sessions:  NewSessionStore(),
		apiKey:    cfg.APIKey,
		ctx:       ctx,
		cancel:    cancel,
		staticDir: staticDir,
		tlsCert:   cfg.TLSCert,
		tlsKey:    cfg.TLSKey,
	}

	// Load persisted webhooks and email config from disk.
	s.loadWebhooks()
	s.loadEmailConfig()

	// Enable provider credential persistence and auto-reconnect saved providers.
	reg.SetPersistPath("/var/lib/hyper2kvm/providers.json")
	for _, saved := range reg.LoadSaved() {
		if err := reg.Connect(context.Background(), saved); err != nil {
			log.Printf("[providers] auto-reconnect %s failed: %v", saved.Name, err)
		} else {
			log.Printf("[providers] auto-reconnected %s (%s)", saved.Name, saved.Type)
		}
	}

	// Initialize multi-kubeconfig manager.
	if kcMgr, err := NewKubeconfigManager(""); err != nil {
		log.Printf("[kubeconfig] failed to initialize manager: %v", err)
	} else {
		s.kubeconfigMgr = kcMgr
		log.Printf("[kubeconfig] manager initialized (dir=%s)", kcMgr.configDir)
	}

	// Initialize auto-cleanup background goroutine.
	s.initAutoCleanup()

	// Wire webhook firing into the WSHub broadcast hook.
	// When jobs complete or fail, webhooks are fired asynchronously.
	if wsHub != nil {
		wsHub.OnBroadcast = func(msgType string, data map[string]interface{}) {
			// Only fire webhooks for job lifecycle events.
			switch msgType {
			case "job_completed", "job_failed", "job_cancelled":
				jobID, _ := data["job_id"].(string)
				vmName := ""
				if job, err := manager.Get(jobID); err == nil {
					vmName = job.Config.VMName
					if vmName == "" {
						vmName = job.Config.VMDK
					}
				}
				status := strings.TrimPrefix(msgType, "job_")
				s.FireWebhooks(msgType, jobID, status, vmName)

				// Send email notification.
				subject := fmt.Sprintf("[hyper2kvm] Job %s: %s", status, jobID)
				body := fmt.Sprintf("Migration job %s has %s.\n\nJob ID: %s\nVM: %s\nTime: %s\n",
					jobID, status, jobID, vmName, time.Now().Format(time.RFC3339))
				s.sendEmailNotification(subject, body)
			}
		}
	}

	r := chi.NewRouter()

	// Middleware chain.
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(loggingMiddleware)
	r.Use(corsMiddleware)
	r.Use(middleware.Recoverer)
	r.Use(s.authRequired)

	// Prometheus metrics endpoint (unauthenticated for scraping).
	r.Get("/metrics", s.handleMetrics)

	// API routes.
	r.Route("/api/v1", func(r chi.Router) {
		// Auth (public — no session required).
		r.Post("/auth/login", s.handleLogin)
		r.Post("/auth/logout", s.handleLogout)
		r.Get("/auth/session", s.handleSession)

		// Health.
		r.Get("/health", s.handleHealth)
		r.Get("/status", s.handleStatus)

		// Providers.
		r.Route("/providers", func(r chi.Router) {
			r.Get("/", s.handleListProviders)
			r.Post("/", s.handleAddProvider)
			r.Post("/test", s.handleTestProvider)
			r.Get("/{providerID}", s.handleGetProvider)
			r.Delete("/{providerID}", s.handleDeleteProvider)
			r.Get("/{providerID}/vms", s.handleListVMs)
			r.Get("/{providerID}/vms/{vmID}", s.handleGetVM)
		})

		// Migrations.
		r.Route("/migrations", func(r chi.Router) {
			r.Post("/preview", s.handlePreviewConfig)
			r.Post("/submit", s.handleSubmitMigration)
			r.Post("/batch", s.handleBatchMigration)
		})

		// Jobs.
		r.Route("/jobs", func(r chi.Router) {
			r.Get("/", s.handleListJobs)
			r.Get("/stats", s.handleJobStats)
			r.Get("/{jobID}", s.handleGetJob)
			r.Post("/{jobID}/cancel", s.handleCancelJob)
			r.Get("/{jobID}/logs", s.handleGetJobLogs)
			r.Get("/{jobID}/report", s.handleJobReport)
		})

		// VNC WebSocket proxy (for react-vnc / noVNC in browser).
		r.Get("/vnc-proxy/{vmName}", s.handleVNCProxy)
		r.Get("/vnc-proxy-kv/{ns}/{vmName}", s.handleKubeVirtVNCProxy)

		// noVNC standalone console (opens in new tab).
		r.Get("/console/{vmName}", s.handleConsoleProxy)

		// Libvirt VM management.
		r.Route("/vms", func(r chi.Router) {
			r.Get("/", s.handleListLibvirtVMs)
			r.Get("/top", s.handleTopVMs)
			r.Post("/bulk-action", s.handleBulkVMAction)
			r.Get("/{vmName}/stats", s.handleVMStats)
			r.Get("/{vmName}/stats/live", s.handleVMLiveStats)
			r.Get("/{vmName}/vnc", s.handleVMVnc)
			r.Get("/{vmName}/screenshot", s.handleVMScreenshot)
			r.Post("/{vmName}/enable-rdp", s.handleEnableRDP)
			r.Post("/{vmName}/start", s.handleVMAction("start"))
			r.Post("/{vmName}/stop", s.handleVMAction("shutdown"))
			r.Post("/{vmName}/reboot", s.handleVMAction("reboot"))
			r.Post("/{vmName}/destroy", s.handleVMAction("destroy"))
			r.Post("/{vmName}/delete", s.handleVMDelete)
			// Snapshots
			r.Get("/{vmName}/snapshots", s.handleListSnapshots)
			r.Post("/{vmName}/snapshots", s.handleCreateSnapshot)
			r.Post("/{vmName}/snapshots/{snapName}/revert", s.handleRevertSnapshot)
			r.Delete("/{vmName}/snapshots/{snapName}", s.handleDeleteSnapshot)
			// Autostart
			r.Post("/{vmName}/autostart", s.handleVMAutostart)
			// Promote disk bus (SATA ↔ VirtIO)
			r.Post("/{vmName}/promote", s.handlePromoteVirtIO)
			// Guest agent insights
			r.Get("/{vmName}/guest-info", s.handleVMGuestInfo)
			// Smart status with root cause
			r.Get("/{vmName}/status-detail", s.handleVMStatusDetail)
			// Domain XML viewer
			r.Get("/{vmName}/xml", s.handleVMXML)
			// Network connectivity test
			r.Get("/{vmName}/connectivity-test", s.handleVMConnectivityTest)
			// Smart recommendations
			r.Get("/{vmName}/recommendations", s.handleVMRecommendations)
			// Security exposure analysis
			r.Get("/{vmName}/security", s.handleVMSecurity)
			// Storage detail (block stats, disk sizes, snapshots, pool)
			r.Get("/{vmName}/storage-detail", s.handleVMStorageDetail)
			// Process viewer via guest agent
			r.Get("/{vmName}/processes", s.handleVMProcesses)
			// Network detail (domiflist + domifstat)
			r.Get("/{vmName}/network-detail", s.handleVMNetworkDetail)
			// Create a new VM via virt-install
			r.Post("/create", s.handleVMCreate)
			// Clone an existing VM
			r.Post("/clone", s.handleVMClone)
			// Import a disk image as a new VM
			r.Post("/import", s.handleVMImport)
			// Resize VM resources (vCPUs, memory)
			r.Post("/{vmName}/resize", s.handleVMResize)
			// Disk management
			r.Post("/{vmName}/disk/attach", s.handleVMDiskAttach)
			r.Post("/{vmName}/disk/detach", s.handleVMDiskDetach)
			// CDROM management
			r.Post("/{vmName}/cdrom/change", s.handleVMCDROMChange)
			// VM events
			r.Get("/{vmName}/events", s.handleVMEvents)
			// Libvirt-to-KubeVirt migration
			r.Post("/{vmName}/migrate-to-kubevirt", s.handleVMMigrateToKubeVirt)

			// VM Hardware Management
			r.Get("/{vmName}/hardware", s.handleGetHardware)
			r.Put("/{vmName}/cpu", s.handleSetCPU)
			r.Put("/{vmName}/memory", s.handleSetMemory)
			r.Post("/{vmName}/disks", s.handleHWAddDisk)
			r.Delete("/{vmName}/disks/{target}", s.handleHWRemoveDisk)
			r.Post("/{vmName}/interfaces", s.handleHWAddInterface)
			r.Delete("/{vmName}/interfaces/{mac}", s.handleHWRemoveInterface)
			r.Put("/{vmName}/cdrom", s.handleHWCDROM)
			r.Post("/{vmName}/tpm", s.handleHWAddTPM)
			r.Put("/{vmName}/boot", s.handleSetBoot)

			// GPU/PCI passthrough
			r.Post("/{vmName}/gpu", s.handleAttachGPU)
			r.Delete("/{vmName}/gpu/{address}", s.handleDetachGPU)

			// CPU pinning
			r.Get("/{vmName}/cpu-pinning", s.handleGetCPUPinning)
			r.Put("/{vmName}/cpu-pinning", s.handleSetCPUPinning)
			r.Put("/{vmName}/numa", s.handleSetNUMAPlacement)

			// Memory ballooning
			r.Get("/{vmName}/balloon", s.handleGetBalloonInfo)
			r.Put("/{vmName}/balloon", s.handleSetBalloon)

			// Live migration
			r.Post("/{vmName}/live-migrate", s.handleLiveMigrate)
			r.Get("/{vmName}/migration-status", s.handleGetMigrationStatus)

			// SR-IOV
			r.Post("/{vmName}/sriov-interface", s.handleAttachSRIOV)

			// Batch VM operations
			r.Post("/batch", s.handleBatchOperation)
		})

		// Cluster capacity overview.
		r.Get("/capacity", s.handleCapacity)

		// Migration readiness check.
		r.Get("/readiness", s.handleReadiness)

		// Disk image discovery.
		r.Get("/disk-images", s.handleDiskImages)

		// Network topology.
		r.Get("/networks/topology", s.handleNetworkTopology)

		// KubeVirt VM management.
		r.Route("/kubevirt", func(r chi.Router) {
			r.Get("/vms", s.handleKubeVirtVMs)
			r.Get("/vmis", s.handleKubeVirtVMIs)
			r.Get("/vms/{ns}/{name}", s.handleKubeVirtVMDetail)
			r.Post("/vms/{ns}/{name}/start", s.handleKubeVirtAction("start"))
			r.Post("/vms/{ns}/{name}/stop", s.handleKubeVirtAction("stop"))
			r.Post("/vms/{ns}/{name}/restart", s.handleKubeVirtAction("restart"))
			r.Post("/vms/{ns}/{name}/pause", s.handleKubeVirtAction("pause"))
			r.Post("/vms/{ns}/{name}/unpause", s.handleKubeVirtAction("unpause"))
			r.Post("/vms/{ns}/{name}/migrate", s.handleKubeVirtAction("migrate"))
			r.Delete("/vms/{ns}/{name}", s.handleKubeVirtDelete)
			r.Get("/vms/{ns}/{name}/vnc", s.handleKubeVirtVNC)
			r.Get("/vms/{ns}/{name}/guestosinfo", s.handleKubeVirtGuestOS)
		})

		// Multi-kubeconfig management.
		r.Route("/kubeconfigs", func(r chi.Router) {
			r.Get("/", s.handleListKubeconfigs)
			r.Post("/add", s.handleAddKubeconfig)
			r.Put("/{id}/activate", s.handleActivateKubeconfig)
			r.Delete("/{id}", s.handleDeleteKubeconfig)
		})

		// Network management.
		r.Route("/networks", func(r chi.Router) {
			r.Get("/", s.handleListNetworks)
			r.Post("/", s.handleCreateNetwork)
			r.Delete("/{name}", s.handleDeleteNetwork)
			r.Post("/{name}/start", s.handleNetworkAction("net-start"))
			r.Post("/{name}/stop", s.handleNetworkAction("net-destroy"))
		})

		// Storage pools.
		r.Route("/pools", func(r chi.Router) {
			r.Get("/", s.handleListPools)
			r.Post("/", s.handleCreatePool)
			r.Get("/{poolName}", s.handleGetPool)
			r.Delete("/{poolName}", s.handleDeletePool)
			r.Post("/{poolName}/start", s.handleStartPool)
			r.Post("/{poolName}/stop", s.handleStopPool)
			r.Get("/{poolName}/volumes", s.handleListPoolVolumes)
			r.Post("/{poolName}/volumes", s.handleCreateVolume)
			r.Delete("/{poolName}/volumes/{volName}", s.handleDeleteVolume)
			r.Post("/{poolName}/volumes/{volName}/resize", s.handleResizeVolume)
		})

		// Templates.
		r.Route("/templates", func(r chi.Router) {
			r.Get("/", s.handleListTemplates)
			r.Post("/", s.handleCreateTemplate)
			r.Post("/{name}/deploy", s.handleDeployTemplate)
			r.Delete("/{name}", s.handleDeleteTemplate)
		})

		// Backups.
		r.Route("/backups", func(r chi.Router) {
			r.Get("/", s.handleListBackups)
			r.Post("/", s.handleCreateBackup)
			r.Post("/{id}/restore", s.handleRestoreBackup)
			r.Post("/{id}/verify", s.handleVerifyBackup)
			r.Delete("/{id}", s.handleDeleteBackup)
		})

		// ISOs.
		r.Route("/isos", func(r chi.Router) {
			r.Get("/", s.handleListISOs)
			r.Post("/upload", s.handleUploadISO)
			r.Delete("/{name}", s.handleDeleteISO)
		})

		// Audit log.
		r.Get("/audit", s.handleAuditLog)

		// Activity feed (last 20 audit entries, newest first).
		r.Get("/activity", s.handleActivity)

		// Webhooks.
		r.Route("/webhooks", func(r chi.Router) {
			r.Get("/", s.handleListWebhooks)
			r.Post("/", s.handleRegisterWebhook)
			r.Delete("/{webhookID}", s.handleDeleteWebhook)
		})

		// Email notifications.
		r.Route("/notifications/email", func(r chi.Router) {
			r.Get("/config", s.handleGetEmailConfig)
			r.Post("/config", s.handleSaveEmailConfig)
			r.Post("/test", s.handleTestEmail)
		})

		// Config backup/restore.
		r.Get("/config/export", s.handleConfigExport)
		r.Post("/config/import", s.handleConfigImport)

		// VM health check.
		r.Get("/vms/{vmName}/health", s.handleVMHealthCheck)

		// API documentation.
		r.Get("/docs", s.handleAPIDocs)

		// Host info.
		r.Get("/host/info", s.handleHostInfo)
		r.Get("/host/pci-devices", s.handleListPCIDevices)
		r.Get("/host/numa", s.handleGetNUMATopology)
		r.Get("/host/sriov-devices", s.handleListSRIOVDevices)

		// Storage management.
		r.Get("/storage/config", s.handleStorageConfig)
		r.Post("/storage/relocate", s.handleStorageRelocate)
		r.Get("/storage/artifacts", s.handleListArtifacts)
		r.Post("/storage/cleanup", s.handleStorageCleanup)

		// Auto-cleanup settings.
		r.Get("/settings/cleanup", s.handleGetCleanupSettings)
		r.Post("/settings/cleanup", s.handleSetCleanupSettings)

		// User management.
		r.Get("/users", s.handleListUsers)
		r.Post("/users", s.handleCreateUser)

		// Browse server filesystem.
		r.Get("/browse", s.handleBrowse)

		// File download.
		r.Get("/download", s.handleDownload)

		// File upload.
		r.Post("/upload", s.handleUpload)

		// Chunked / resumable upload.
		r.Post("/upload/init", s.handleUploadInit)
		r.Post("/upload/chunk", s.handleUploadChunk)
		r.Post("/upload/complete", s.handleUploadComplete)
		r.Get("/upload/status/{uploadId}", s.handleUploadStatus)

		// Deployed VM status (libvirt + kubevirt).
		r.Get("/deploy/{vmName}/ip", s.handleGetVMIP)
		r.Get("/deploy/{vmName}/status", s.handleGetVMStatus)

		// WebSocket.
		r.Get("/ws", s.handleWebSocket)
	})

	// Serve React dashboard (SPA with static assets).
	r.HandleFunc("/*", s.handleStatic)

	s.router = r
	s.httpServer = &http.Server{
		Addr:    cfg.Addr,
		Handler: r,
		// No global read/write timeouts — large file uploads (up to 50GB)
		// need unbounded time. Per-handler timeouts are used where needed.
	}

	return s
}

// Start starts the HTTP or HTTPS server.
func (s *Server) Start() error {
	if s.tlsCert != "" && s.tlsKey != "" {
		log.Printf("[api] starting HTTPS server on %s", s.httpServer.Addr)

		cert, err := tls.LoadX509KeyPair(s.tlsCert, s.tlsKey)
		if err != nil {
			return fmt.Errorf("failed to load TLS certificate: %w", err)
		}
		tlsCfg := &tls.Config{
			Certificates: []tls.Certificate{cert},
			MinVersion:   tls.VersionTLS12,
		}

		ln, err := net.Listen("tcp", s.httpServer.Addr)
		if err != nil {
			return fmt.Errorf("failed to listen on %s: %w", s.httpServer.Addr, err)
		}
		defer ln.Close()

		log.Printf("[api] HTTP requests on this port will be redirected to HTTPS")
		s.httpServer.TLSConfig = tlsCfg
		return s.httpServer.Serve(&httpRedirectListener{
			Listener:  ln,
			tlsConfig: tlsCfg,
			addr:      s.httpServer.Addr,
		})
	}
	log.Printf("[api] starting HTTP server on %s", s.httpServer.Addr)
	return s.httpServer.ListenAndServe()
}

// httpRedirectListener detects plain HTTP on a TLS port and redirects to HTTPS.
type httpRedirectListener struct {
	net.Listener
	tlsConfig *tls.Config
	addr      string
}

func (l *httpRedirectListener) Accept() (net.Conn, error) {
	for {
		conn, err := l.Listener.Accept()
		if err != nil {
			return nil, err
		}
		buf := make([]byte, 1)
		conn.SetReadDeadline(time.Now().Add(5 * time.Second))
		_, err = io.ReadFull(conn, buf)
		conn.SetReadDeadline(time.Time{})
		if err != nil {
			conn.Close()
			continue
		}
		peeked := &prefixConn{Conn: conn, prefix: buf}
		if buf[0] == 0x16 { // TLS ClientHello
			return tls.Server(peeked, l.tlsConfig), nil
		}
		go l.redirectHTTP(peeked)
	}
}

func (l *httpRedirectListener) redirectHTTP(conn net.Conn) {
	defer conn.Close()
	req, err := http.ReadRequest(bufio.NewReader(conn))
	if err != nil {
		return
	}
	host := req.Host
	if host == "" {
		host = conn.LocalAddr().String()
	}
	if h, _, err := net.SplitHostPort(host); err == nil {
		host = h
	}
	_, port, _ := net.SplitHostPort(l.addr)
	target := fmt.Sprintf("https://%s%s", net.JoinHostPort(host, port), req.URL.RequestURI())
	resp := fmt.Sprintf("HTTP/1.1 301 Moved Permanently\r\nLocation: %s\r\nContent-Length: 0\r\nConnection: close\r\n\r\n", target)
	conn.Write([]byte(resp))
}

// prefixConn prepends previously-read bytes back onto a net.Conn.
type prefixConn struct {
	net.Conn
	prefix []byte
	done   bool
}

func (c *prefixConn) Read(b []byte) (int, error) {
	if !c.done && len(c.prefix) > 0 {
		n := copy(b, c.prefix)
		c.prefix = c.prefix[n:]
		if len(c.prefix) == 0 {
			c.done = true
		}
		return n, nil
	}
	return c.Conn.Read(b)
}

// Shutdown gracefully shuts down the server.
func (s *Server) Shutdown(ctx context.Context) error {
	s.cancel()
	if s.cleanup != nil && s.cleanup.ticker != nil {
		s.cleanup.ticker.Stop()
	}
	if s.wsHub != nil {
		s.wsHub.Shutdown()
	}
	return s.httpServer.Shutdown(ctx)
}

// --- Health ---

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"status":    "healthy",
		"timestamp": time.Now().Format(time.RFC3339),
	})
}

func (s *Server) handleStatus(w http.ResponseWriter, r *http.Request) {
	stats := s.manager.Stats()
	providers := s.registry.List()
	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"jobs":      stats,
		"providers": providers,
		"ws_clients": s.wsHub.ClientCount(),
	})
}

// --- Providers ---

func (s *Server) handleListProviders(w http.ResponseWriter, r *http.Request) {
	statuses := s.registry.List()
	// Mark persisted providers with a "(saved)" suffix in name.
	for i := range statuses {
		if _, ok := s.registry.GetConfig(statuses[i].ID); ok {
			// Provider config exists — it will be persisted.
		}
	}
	jsonResponse(w, http.StatusOK, statuses)
}

func (s *Server) handleAddProvider(w http.ResponseWriter, r *http.Request) {
	var config domain.ProviderConfig
	if err := readJSON(r, &config); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if config.ID == "" {
		config.ID = fmt.Sprintf("%s-%d", config.Type, time.Now().UnixMilli())
	}

	if err := s.registry.Connect(r.Context(), config); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	jsonResponse(w, http.StatusCreated, map[string]string{
		"id":      config.ID,
		"message": "provider connected",
	})
}

func (s *Server) handleTestProvider(w http.ResponseWriter, r *http.Request) {
	var config domain.ProviderConfig
	if err := readJSON(r, &config); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if config.ID == "" {
		config.ID = "test-" + string(config.Type)
	}

	// Try to connect, then immediately disconnect.
	if err := s.registry.Connect(r.Context(), config); err != nil {
		jsonResponse(w, http.StatusOK, map[string]interface{}{
			"success": false,
			"error":   err.Error(),
		})
		return
	}
	_ = s.registry.Disconnect(r.Context(), config.ID)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"success": true,
		"message": "connection successful",
	})
}

func (s *Server) handleGetProvider(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "providerID")
	config, ok := s.registry.GetConfig(id)
	if !ok {
		jsonError(w, http.StatusNotFound, "provider not found")
		return
	}
	// Mask password in API response.
	masked := config
	if masked.Password != "" {
		masked.Password = "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
	}
	jsonResponse(w, http.StatusOK, masked)
}

func (s *Server) handleDeleteProvider(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "providerID")
	if err := s.registry.Disconnect(r.Context(), id); err != nil {
		jsonError(w, http.StatusNotFound, err.Error())
		return
	}
	jsonResponse(w, http.StatusOK, map[string]string{"message": "provider disconnected"})
}

// --- VMs ---

func (s *Server) handleListVMs(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "providerID")
	provider, err := s.registry.Get(id)
	if err != nil {
		jsonError(w, http.StatusNotFound, err.Error())
		return
	}

	filter := domain.VMFilter{
		NamePattern: r.URL.Query().Get("name"),
		State:       r.URL.Query().Get("state"),
	}

	vms, err := provider.ListVMs(r.Context(), filter)
	if err != nil {
		jsonError(w, http.StatusInternalServerError, err.Error())
		return
	}

	jsonResponse(w, http.StatusOK, vms)
}

func (s *Server) handleGetVM(w http.ResponseWriter, r *http.Request) {
	providerID := chi.URLParam(r, "providerID")
	vmID := chi.URLParam(r, "vmID")

	provider, err := s.registry.Get(providerID)
	if err != nil {
		jsonError(w, http.StatusNotFound, err.Error())
		return
	}

	vm, err := provider.GetVM(r.Context(), vmID)
	if err != nil {
		jsonError(w, http.StatusNotFound, err.Error())
		return
	}

	jsonResponse(w, http.StatusOK, vm)
}

// --- Migrations ---

func (s *Server) handlePreviewConfig(w http.ResponseWriter, r *http.Request) {
	var config domain.MigrationConfig
	if err := readJSON(r, &config); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	// Marshal to YAML for preview.
	yamlBytes, err := yaml.Marshal(&config)
	if err != nil {
		jsonError(w, http.StatusInternalServerError, err.Error())
		return
	}

	jsonResponse(w, http.StatusOK, map[string]string{
		"yaml": string(yamlBytes),
	})
}

func (s *Server) handleSubmitMigration(w http.ResponseWriter, r *http.Request) {
	var config domain.MigrationConfig
	if err := readJSON(r, &config); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := config.ValidateDeployExclusive(); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	id, err := s.manager.Submit(config)
	if err != nil {
		jsonError(w, http.StatusInternalServerError, err.Error())
		return
	}

	jsonResponse(w, http.StatusAccepted, map[string]string{
		"job_id":  id,
		"message": "migration submitted",
	})
}

// --- Jobs ---

func (s *Server) handleListJobs(w http.ResponseWriter, r *http.Request) {
	jobs := s.manager.List(domain.JobFilter{})
	jsonResponse(w, http.StatusOK, jobs)
}

func (s *Server) handleJobStats(w http.ResponseWriter, r *http.Request) {
	jsonResponse(w, http.StatusOK, s.manager.Stats())
}

func (s *Server) handleGetJob(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "jobID")
	job, err := s.manager.Get(id)
	if err != nil {
		jsonError(w, http.StatusNotFound, err.Error())
		return
	}
	jsonResponse(w, http.StatusOK, job)
}

func (s *Server) handleCancelJob(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "jobID")
	if err := s.manager.Cancel(id); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}
	jsonResponse(w, http.StatusOK, map[string]string{"message": "job cancelled"})
}

func (s *Server) handleGetJobLogs(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "jobID")
	job, err := s.manager.Get(id)
	if err != nil {
		jsonError(w, http.StatusNotFound, err.Error())
		return
	}
	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"job_id": id,
		"lines":  job.LogLines,
	})
}

func (s *Server) handleJobReport(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "jobID")

	// Sanitize job ID: only allow alphanumeric, dash, underscore.
	for _, c := range id {
		if !((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_') {
			jsonError(w, http.StatusBadRequest, "invalid job ID")
			return
		}
	}

	job, err := s.manager.Get(id)
	if err != nil {
		jsonError(w, http.StatusNotFound, err.Error())
		return
	}

	// Build the report.
	var b strings.Builder
	b.WriteString("# Migration Report\n\n")
	b.WriteString(fmt.Sprintf("**Job ID:** %s\n", job.ID))
	b.WriteString(fmt.Sprintf("**Status:** %s\n", job.Status))

	// Source file.
	source := job.Config.VMDK
	if source == "" {
		source = job.Config.OVA
	}
	if source == "" {
		source = job.Config.OVF
	}
	if source == "" {
		source = job.Config.VHD
	}
	if source == "" {
		source = job.Config.Raw
	}
	if source == "" {
		source = "(not set)"
	}
	b.WriteString(fmt.Sprintf("**Source:** %s\n", source))

	// Output.
	outputDir := job.Config.OutputDir
	if outputDir == "" {
		outputDir = "(default)"
	}
	b.WriteString(fmt.Sprintf("**Output Directory:** %s\n", outputDir))
	if job.Config.OutFormat != "" {
		b.WriteString(fmt.Sprintf("**Output Format:** %s\n", job.Config.OutFormat))
	}
	if job.Config.ToOutput != "" {
		b.WriteString(fmt.Sprintf("**Output File:** %s\n", job.Config.ToOutput))
	}

	// Timing.
	b.WriteString(fmt.Sprintf("\n## Timing\n\n"))
	b.WriteString(fmt.Sprintf("**Created:** %s\n", job.CreatedAt.Format(time.RFC3339)))
	if job.StartedAt != nil {
		b.WriteString(fmt.Sprintf("**Started:** %s\n", job.StartedAt.Format(time.RFC3339)))
	}
	if job.CompletedAt != nil {
		b.WriteString(fmt.Sprintf("**Completed:** %s\n", job.CompletedAt.Format(time.RFC3339)))
	}
	if job.StartedAt != nil && job.CompletedAt != nil {
		duration := job.CompletedAt.Sub(*job.StartedAt)
		b.WriteString(fmt.Sprintf("**Duration:** %s\n", duration.Round(time.Second)))
	} else if job.StartedAt != nil {
		elapsed := time.Since(*job.StartedAt)
		b.WriteString(fmt.Sprintf("**Elapsed:** %s (still running)\n", elapsed.Round(time.Second)))
	}

	// Config summary.
	b.WriteString(fmt.Sprintf("\n## Configuration\n\n"))
	b.WriteString(fmt.Sprintf("**Command:** %s\n", job.Config.Command))
	b.WriteString(fmt.Sprintf("**Flatten:** %v\n", job.Config.Flatten))
	b.WriteString(fmt.Sprintf("**Compress:** %v\n", job.Config.Compress))

	var fixes []string
	if job.Config.RegenInitramfs {
		fixes = append(fixes, "regen_initramfs")
	}
	if job.Config.UpdateGrub {
		fixes = append(fixes, "update_grub")
	}
	if job.Config.RemoveVMwareTools {
		fixes = append(fixes, "remove_vmware_tools")
	}
	if job.Config.FstabMode != "" {
		fixes = append(fixes, "fstab_mode="+job.Config.FstabMode)
	}
	if len(fixes) > 0 {
		b.WriteString(fmt.Sprintf("**Fixes Applied:** %s\n", strings.Join(fixes, ", ")))
	} else {
		b.WriteString("**Fixes Applied:** none\n")
	}

	if job.Config.EmitDomainXML {
		b.WriteString("**Emit Domain XML:** yes\n")
	}
	if job.Config.VirshDefine {
		b.WriteString("**Virsh Define:** yes\n")
	}
	if job.Config.DeployK8s {
		b.WriteString(fmt.Sprintf("**Deploy to K8s:** yes (namespace: %s)\n", job.Config.Namespace))
	}
	if job.Config.DeployOpenStack {
		glance := job.Config.GlanceName
		if glance == "" {
			glance = job.Config.VMName
		}
		b.WriteString(fmt.Sprintf("**Deploy to OpenStack:** Glance image %q", glance))
		if job.Config.OSCloud != "" {
			b.WriteString(fmt.Sprintf(" (cloud: %s)", job.Config.OSCloud))
		}
		b.WriteString("\n")
		if job.Config.OpenStackBootInstance {
			b.WriteString("**Nova boot:** yes\n")
		}
	}

	// Error.
	if job.Error != "" {
		b.WriteString(fmt.Sprintf("\n## Error\n\n```\n%s\n```\n", job.Error))
	}

	// Last 50 log lines.
	b.WriteString(fmt.Sprintf("\n## Log (last 50 lines)\n\n```\n"))
	logLines := job.LogLines
	if len(logLines) > 50 {
		logLines = logLines[len(logLines)-50:]
	}
	for _, line := range logLines {
		b.WriteString(line)
		b.WriteString("\n")
	}
	b.WriteString("```\n")

	report := b.String()
	log.Printf("[api] job report generated: job=%s size=%d bytes", id, len(report))

	// Return as text/plain with download header.
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.Header().Set("Content-Disposition", fmt.Sprintf("attachment; filename=migration-report-%s.txt", id))
	w.WriteHeader(http.StatusOK)
	w.Write([]byte(report))
}

// --- WebSocket ---

func (s *Server) handleWebSocket(w http.ResponseWriter, r *http.Request) {
	conn, err := wsUpgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("[ws] upgrade failed: %v", err)
		return
	}

	client := &WSClient{
		conn: conn,
		send: make(chan WSMessage, 256),
		hub:  s.wsHub,
	}

	s.wsHub.register <- client

	// Send initial status.
	go func() {
		stats := s.manager.Stats()
		client.send <- WSMessage{
			Type:      "status",
			Timestamp: time.Now(),
			Data: map[string]interface{}{
				"jobs": stats,
			},
		}
	}()

	go client.writePump(s.ctx)
	go client.readPump(s.ctx)
}

// --- User management ---

func (s *Server) handleListUsers(w http.ResponseWriter, r *http.Request) {
	// List users in the h2kweb group (migration operators)
	type userInfo struct {
		Name   string   `json:"name"`
		UID    string   `json:"uid"`
		Groups []string `json:"groups"`
		Shell  string   `json:"shell"`
		Sudo   bool     `json:"sudo"`
		Home   string   `json:"home"`
	}

	var users []userInfo

	// Read /etc/passwd for human users (UID >= 1000) + root
	if data, err := os.ReadFile("/etc/passwd"); err == nil {
		for _, line := range strings.Split(string(data), "\n") {
			fields := strings.Split(line, ":")
			if len(fields) < 7 {
				continue
			}
			uid := fields[2]
			name := fields[0]
			shell := fields[6]

			// Skip system users (except root) and nologin shells
			uidInt, err := strconv.Atoi(uid)
			if err != nil {
				log.Printf("[warn] failed to parse uid %s: %v", uid, err)
			}
			if uidInt != 0 && uidInt < 1000 {
				continue
			}
			if strings.Contains(shell, "nologin") || strings.Contains(shell, "false") {
				continue
			}

			u := userInfo{
				Name:  name,
				UID:   uid,
				Shell: shell,
				Home:  fields[5],
			}

			// Get groups
			if out, err := exec.CommandContext(r.Context(), "groups", name).Output(); err == nil {
				parts := strings.SplitN(strings.TrimSpace(string(out)), ":", 2)
				if len(parts) == 2 {
					u.Groups = strings.Fields(strings.TrimSpace(parts[1]))
				}
			}

			// Check sudo access for h2kvmctl
			sudoFile := "/etc/sudoers.d/h2kweb-" + name
			if _, err := os.Stat(sudoFile); err == nil {
				u.Sudo = true
			}
			// Root always has sudo
			if name == "root" {
				u.Sudo = true
			}

			users = append(users, u)
		}
	}

	jsonResponse(w, http.StatusOK, users)
}

func (s *Server) handleCreateUser(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Username string `json:"username"`
		Password string `json:"password"`
		Sudo     bool   `json:"sudo"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.Username == "" || req.Password == "" {
		jsonError(w, http.StatusBadRequest, "username and password required")
		return
	}

	// Validate username
	for _, c := range req.Username {
		if !((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_' || c == '-') {
			jsonError(w, http.StatusBadRequest, "username must be lowercase alphanumeric, _ or -")
			return
		}
	}

	steps := []string{}

	// Create h2kweb group if it doesn't exist
	exec.CommandContext(r.Context(), "groupadd", "-f", "h2kweb").Run()

	// Create user
	out, err := exec.CommandContext(r.Context(),
		"useradd", "-m", "-G", "h2kweb,libvirt,kvm,qemu",
		"-s", "/bin/bash",
		"-c", "h2kweb migration operator",
		req.Username,
	).CombinedOutput()
	if err != nil {
		outStr := strings.TrimSpace(string(out))
		if !strings.Contains(outStr, "already exists") {
			jsonError(w, http.StatusInternalServerError, fmt.Sprintf("useradd failed: %s", outStr))
			return
		}
		steps = append(steps, fmt.Sprintf("User %s already exists", req.Username))
	} else {
		steps = append(steps, fmt.Sprintf("Created user %s", req.Username))
	}

	// Set password
	cmd := exec.CommandContext(r.Context(), "chpasswd")
	cmd.Stdin = strings.NewReader(fmt.Sprintf("%s:%s", req.Username, req.Password))
	if out, err := cmd.CombinedOutput(); err != nil {
		jsonError(w, http.StatusInternalServerError, fmt.Sprintf("set password failed: %s", string(out)))
		return
	}
	steps = append(steps, "Password set")

	// Add to groups
	exec.CommandContext(r.Context(), "usermod", "-aG", "h2kweb,libvirt,kvm,qemu", req.Username).Run()
	steps = append(steps, "Added to groups: h2kweb, libvirt, kvm, qemu")

	// Setup sudo for h2kvmctl and related tools
	if req.Sudo {
		sudoContent := fmt.Sprintf(
			"# h2kweb migration operator - %s\n"+
				"%s ALL=(root) NOPASSWD: /usr/local/bin/h2kvmctl, /usr/bin/h2kvmctl, /usr/local/sbin/h2kvmctl\n"+
				"%s ALL=(root) NOPASSWD: /usr/bin/virsh, /usr/bin/qemu-img, /usr/sbin/qemu-nbd\n"+
				"%s ALL=(root) NOPASSWD: /usr/bin/mount, /usr/bin/umount, /usr/sbin/modprobe\n",
			req.Username, req.Username, req.Username, req.Username,
		)
		sudoFile := fmt.Sprintf("/etc/sudoers.d/h2kweb-%s", req.Username)
		if err := os.WriteFile(sudoFile, []byte(sudoContent), 0440); err != nil {
			jsonError(w, http.StatusInternalServerError, fmt.Sprintf("sudoers write failed: %v", err))
			return
		}
		steps = append(steps, fmt.Sprintf("Sudo configured: %s (h2kvmctl, virsh, qemu-img, mount)", sudoFile))
	}

	jsonResponse(w, http.StatusCreated, map[string]interface{}{
		"username": req.Username,
		"sudo":     req.Sudo,
		"steps":    steps,
		"message":  fmt.Sprintf("User %s created — can login to h2kweb and run migrations", req.Username),
	})
}

// --- Storage management ---

func (s *Server) handleStorageConfig(w http.ResponseWriter, r *http.Request) {
	defaultPath := "/var/lib/libvirt/images"
	result := map[string]interface{}{
		"default_path": defaultPath,
	}

	// Check if it's a symlink
	if target, err := os.Readlink(defaultPath); err == nil {
		result["is_symlink"] = true
		result["symlink_target"] = target
		result["actual_path"] = target
	} else {
		result["is_symlink"] = false
		result["actual_path"] = defaultPath
	}

	// Get disk usage of actual path
	actualPath := result["actual_path"].(string)
	if out, err := exec.CommandContext(r.Context(), "df", "-BM", "--output=source,size,used,avail,pcent,target", actualPath).Output(); err == nil {
		lines := strings.Split(strings.TrimSpace(string(out)), "\n")
		if len(lines) >= 2 {
			fields := strings.Fields(lines[1])
			if len(fields) >= 6 {
				result["device"] = fields[0]
				result["total"] = strings.TrimSuffix(fields[1], "M") + " MB"
				result["used"] = strings.TrimSuffix(fields[2], "M") + " MB"
				result["avail"] = strings.TrimSuffix(fields[3], "M") + " MB"
				result["percent"] = strings.TrimSuffix(fields[4], "%")
				result["mountpoint"] = fields[5]
			}
		}
	}

	// List existing images
	if entries, err := os.ReadDir(actualPath); err == nil {
		var images []map[string]interface{}
		for _, e := range entries {
			if e.IsDir() {
				continue
			}
			name := e.Name()
			ext := strings.ToLower(filepath.Ext(name))
			if ext == ".qcow2" || ext == ".raw" || ext == ".img" || ext == ".xml" {
				info, _ := e.Info()
				images = append(images, map[string]interface{}{
					"name": name,
					"size": info.Size(),
					"type": ext[1:],
				})
			}
		}
		result["images"] = images
		result["image_count"] = len(images)
	}

	// SELinux status
	if out, err := exec.CommandContext(r.Context(), "getenforce").Output(); err == nil {
		result["selinux"] = strings.TrimSpace(string(out))
	}

	jsonResponse(w, http.StatusOK, result)
}

func (s *Server) handleStorageRelocate(w http.ResponseWriter, r *http.Request) {
	var req struct {
		TargetDir string `json:"target_dir"`
		MoveData  bool   `json:"move_data"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.TargetDir == "" {
		jsonError(w, http.StatusBadRequest, "target_dir required")
		return
	}

	targetDir := filepath.Clean(req.TargetDir)
	defaultPath := "/var/lib/libvirt/images"
	steps := []string{}

	// Validate target exists and is a directory
	targetInfo, err := os.Stat(targetDir)
	if err != nil {
		// Try to create it
		if err := os.MkdirAll(targetDir, 0755); err != nil {
			jsonError(w, http.StatusBadRequest, fmt.Sprintf("cannot create %s: %v", targetDir, err))
			return
		}
		steps = append(steps, fmt.Sprintf("Created directory %s", targetDir))
	} else if !targetInfo.IsDir() {
		jsonError(w, http.StatusBadRequest, fmt.Sprintf("%s is not a directory", targetDir))
		return
	}

	// Check if already a symlink pointing to target
	if target, err := os.Readlink(defaultPath); err == nil && target == targetDir {
		jsonResponse(w, http.StatusOK, map[string]interface{}{
			"status": "already_configured",
			"message": fmt.Sprintf("%s already points to %s", defaultPath, targetDir),
		})
		return
	}

	// Stop libvirtd temporarily
	exec.CommandContext(r.Context(), "systemctl", "stop", "libvirtd").Run()
	steps = append(steps, "Stopped libvirtd")

	// Move existing data if requested
	if req.MoveData {
		// Check if default path is a real directory (not symlink)
		if _, err := os.Readlink(defaultPath); err != nil {
			// It's a real directory — move contents
			entries, _ := os.ReadDir(defaultPath)
			for _, e := range entries {
				src := filepath.Join(defaultPath, e.Name())
				dst := filepath.Join(targetDir, e.Name())
				if _, err := os.Stat(dst); err == nil {
					continue // skip if already exists at target
				}
				if out, err := exec.CommandContext(r.Context(), "mv", src, dst).CombinedOutput(); err != nil {
					steps = append(steps, fmt.Sprintf("Warning: failed to move %s: %s", e.Name(), string(out)))
				} else {
					steps = append(steps, fmt.Sprintf("Moved %s → %s", e.Name(), dst))
				}
			}
		}
	}

	// Remove old directory / symlink and create new symlink
	if info, err := os.Lstat(defaultPath); err == nil {
		if info.Mode()&os.ModeSymlink != 0 {
			os.Remove(defaultPath)
			steps = append(steps, "Removed old symlink")
		} else if info.IsDir() {
			// Only remove if empty or data was moved
			entries, _ := os.ReadDir(defaultPath)
			if len(entries) == 0 || req.MoveData {
				os.RemoveAll(defaultPath)
				steps = append(steps, "Removed old directory")
			} else {
				// Rename as backup
				backup := defaultPath + ".bak"
				os.Rename(defaultPath, backup)
				steps = append(steps, fmt.Sprintf("Backed up old directory to %s", backup))
			}
		}
	}

	// Create symlink
	if err := os.Symlink(targetDir, defaultPath); err != nil {
		jsonError(w, http.StatusInternalServerError, fmt.Sprintf("symlink failed: %v", err))
		return
	}
	steps = append(steps, fmt.Sprintf("Created symlink %s → %s", defaultPath, targetDir))

	// Fix SELinux context
	exec.CommandContext(r.Context(), "restorecon", "-Rv", targetDir).Run()
	exec.CommandContext(r.Context(), "chcon", "-t", "virt_image_t", targetDir).Run()
	// Also set semanage for persistence
	exec.CommandContext(r.Context(), "semanage", "fcontext", "-a", "-t", "virt_image_t", targetDir+"(/.*)?").Run()
	exec.CommandContext(r.Context(), "restorecon", "-Rv", targetDir).Run()
	steps = append(steps, "Applied SELinux context (virt_image_t)")

	// Set ownership
	exec.CommandContext(r.Context(), "chown", "-R", "qemu:qemu", targetDir).Run()
	steps = append(steps, "Set ownership to qemu:qemu")

	// Restart libvirtd
	exec.CommandContext(r.Context(), "systemctl", "start", "libvirtd").Run()
	steps = append(steps, "Started libvirtd")

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"status":  "relocated",
		"from":    defaultPath,
		"to":      targetDir,
		"steps":   steps,
		"message": fmt.Sprintf("Storage relocated: %s → %s", defaultPath, targetDir),
	})
}

// --- Storage artifact cleanup ---

func formatBytesHuman(b int64) string {
	if b > 1<<30 {
		return fmt.Sprintf("%.1f GB", float64(b)/float64(1<<30))
	}
	if b > 1<<20 {
		return fmt.Sprintf("%.1f MB", float64(b)/float64(1<<20))
	}
	return fmt.Sprintf("%.1f KB", float64(b)/float64(1<<10))
}

func (s *Server) handleListArtifacts(w http.ResponseWriter, r *http.Request) {
	dirs := []string{"/var/lib/hyper2kvm/output", "/var/lib/hyper2kvm/input"}

	type artifact struct {
		Name      string `json:"name"`
		Path      string `json:"path"`
		SizeBytes int64  `json:"size_bytes"`
		Modified  string `json:"modified"`
		Dir       string `json:"dir"`
	}

	var artifacts []artifact
	var totalBytes int64

	for _, dir := range dirs {
		dirName := filepath.Base(dir)
		filepath.Walk(dir, func(path string, info os.FileInfo, err error) error {
			if err != nil || info.IsDir() {
				return nil
			}
			artifacts = append(artifacts, artifact{
				Name:      info.Name(),
				Path:      path,
				SizeBytes: info.Size(),
				Modified:  info.ModTime().Format(time.RFC3339),
				Dir:       dirName,
			})
			totalBytes += info.Size()
			return nil
		})
	}

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"artifacts":   artifacts,
		"total_bytes": totalBytes,
		"total_human": formatBytesHuman(totalBytes),
	})
}

func (s *Server) handleStorageCleanup(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Dirs         []string `json:"dirs"`
		OlderThanHrs int      `json:"older_than_hours"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	// Validate dirs whitelist.
	allowedDirs := map[string]string{
		"output": "/var/lib/hyper2kvm/output",
		"input":  "/var/lib/hyper2kvm/input",
	}
	var targetDirs []string
	for _, d := range req.Dirs {
		fullPath, ok := allowedDirs[d]
		if !ok {
			jsonError(w, http.StatusBadRequest, fmt.Sprintf("invalid dir %q: allowed values are \"output\" and \"input\"", d))
			return
		}
		targetDirs = append(targetDirs, fullPath)
	}
	if len(targetDirs) == 0 {
		jsonError(w, http.StatusBadRequest, "dirs required: specify [\"output\"], [\"input\"], or both")
		return
	}

	var deleted int
	var freedBytes int64
	cutoff := time.Time{}
	if req.OlderThanHrs > 0 {
		cutoff = time.Now().Add(-time.Duration(req.OlderThanHrs) * time.Hour)
	}

	for _, dir := range targetDirs {
		filepath.Walk(dir, func(path string, info os.FileInfo, err error) error {
			if err != nil || info.IsDir() {
				return nil
			}
			// Safety: never delete anything outside /var/lib/hyper2kvm/
			if !strings.HasPrefix(path, "/var/lib/hyper2kvm/") {
				return nil
			}
			if !cutoff.IsZero() && info.ModTime().After(cutoff) {
				return nil
			}
			size := info.Size()
			if err := os.Remove(path); err != nil {
				log.Printf("[storage-cleanup] failed to delete %s: %v", path, err)
				return nil
			}
			log.Printf("[storage-cleanup] deleted %s (%s)", path, formatBytesHuman(size))
			deleted++
			freedBytes += size
			return nil
		})
	}

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"deleted":    deleted,
		"freed_bytes": freedBytes,
		"freed_human": formatBytesHuman(freedBytes),
	})
}

// --- Host info ---

func (s *Server) handleHostInfo(w http.ResponseWriter, r *http.Request) {
	info := map[string]interface{}{}

	// Hostname
	if h, err := os.Hostname(); err == nil {
		info["hostname"] = h
	}

	// OS info from /etc/os-release
	if data, err := os.ReadFile("/etc/os-release"); err == nil {
		osInfo := map[string]string{}
		for _, line := range strings.Split(string(data), "\n") {
			parts := strings.SplitN(line, "=", 2)
			if len(parts) == 2 {
				osInfo[strings.ToLower(parts[0])] = strings.Trim(parts[1], "\"")
			}
		}
		info["os_name"] = osInfo["pretty_name"]
		info["os_id"] = osInfo["id"]
		info["os_version"] = osInfo["version_id"]
	}

	// Kernel
	if out, err := exec.CommandContext(r.Context(), "uname", "-r").Output(); err == nil {
		info["kernel"] = strings.TrimSpace(string(out))
	}

	// Uptime
	if data, err := os.ReadFile("/proc/uptime"); err == nil {
		parts := strings.Fields(string(data))
		if len(parts) > 0 {
			if secs, err := strconv.ParseFloat(parts[0], 64); err == nil {
				days := int(secs) / 86400
				hours := (int(secs) % 86400) / 3600
				mins := (int(secs) % 3600) / 60
				info["uptime_seconds"] = int(secs)
				info["uptime_human"] = fmt.Sprintf("%dd %dh %dm", days, hours, mins)
			}
		}
	}

	// Load average
	if data, err := os.ReadFile("/proc/loadavg"); err == nil {
		parts := strings.Fields(string(data))
		if len(parts) >= 3 {
			info["load_1m"] = parts[0]
			info["load_5m"] = parts[1]
			info["load_15m"] = parts[2]
		}
	}

	// CPU info
	if data, err := os.ReadFile("/proc/cpuinfo"); err == nil {
		cpuCount := 0
		cpuModel := ""
		for _, line := range strings.Split(string(data), "\n") {
			if strings.HasPrefix(line, "processor") {
				cpuCount++
			}
			if strings.HasPrefix(line, "model name") && cpuModel == "" {
				parts := strings.SplitN(line, ":", 2)
				if len(parts) == 2 {
					cpuModel = strings.TrimSpace(parts[1])
				}
			}
		}
		info["cpu_cores"] = cpuCount
		info["cpu_model"] = cpuModel
	}

	// Memory from /proc/meminfo
	if data, err := os.ReadFile("/proc/meminfo"); err == nil {
		mem := map[string]int64{}
		for _, line := range strings.Split(string(data), "\n") {
			parts := strings.Fields(line)
			if len(parts) >= 2 {
				key := strings.TrimSuffix(parts[0], ":")
				if val, err := strconv.ParseInt(parts[1], 10, 64); err == nil {
					mem[key] = val // in kB
				}
			}
		}
		totalMB := mem["MemTotal"] / 1024
		availMB := mem["MemAvailable"] / 1024
		usedMB := totalMB - availMB
		info["mem_total_mb"] = totalMB
		info["mem_used_mb"] = usedMB
		info["mem_available_mb"] = availMB
		if totalMB > 0 {
			info["mem_percent"] = int((usedMB * 100) / totalMB)
		}
		info["swap_total_mb"] = mem["SwapTotal"] / 1024
		info["swap_used_mb"] = (mem["SwapTotal"] - mem["SwapFree"]) / 1024
	}

	// All real disks from lsblk + df
	type diskEntry struct {
		Name       string `json:"name"`
		Size       string `json:"size"`
		Mountpoint string `json:"mountpoint"`
		Fstype     string `json:"fstype"`
		Used       string `json:"used"`
		Avail      string `json:"avail"`
		Percent    string `json:"percent"`
	}
	var disks []diskEntry
	if out, err := exec.CommandContext(r.Context(), "lsblk", "-ndo", "NAME,SIZE,FSTYPE,MOUNTPOINT", "--exclude", "7,43").Output(); err == nil {
		// Get df data for mount usage
		dfData := map[string][]string{}
		if dfOut, err := exec.CommandContext(r.Context(), "df", "-BM", "--output=target,size,used,avail,pcent").Output(); err == nil {
			for _, line := range strings.Split(string(dfOut), "\n")[1:] {
				fields := strings.Fields(line)
				if len(fields) >= 5 {
					dfData[fields[0]] = fields
				}
			}
		}
		for _, line := range strings.Split(strings.TrimSpace(string(out)), "\n") {
			fields := strings.Fields(line)
			if len(fields) < 2 {
				continue
			}
			// Skip nbd, loop, ram devices
			name := fields[0]
			if strings.HasPrefix(name, "nbd") || strings.HasPrefix(name, "loop") || strings.HasPrefix(name, "ram") {
				continue
			}
			// Get partitions with mountpoints
			partOut, _ := exec.CommandContext(r.Context(), "lsblk", "-nro", "NAME,SIZE,FSTYPE,MOUNTPOINT", "/dev/"+name).Output()
			for _, pline := range strings.Split(strings.TrimSpace(string(partOut)), "\n") {
				pf := strings.Fields(pline)
				if len(pf) >= 4 && pf[3] != "" && !strings.Contains(pf[3], "containerd") && !strings.HasPrefix(pf[3], "/run/k3s") {
					d := diskEntry{Name: pf[0], Size: pf[1], Fstype: pf[2], Mountpoint: pf[3]}
					if df, ok := dfData[pf[3]]; ok && len(df) >= 5 {
						d.Used = strings.TrimSuffix(df[2], "M") + " MB"
						d.Avail = strings.TrimSuffix(df[3], "M") + " MB"
						d.Percent = strings.TrimSuffix(df[4], "%")
					}
					disks = append(disks, d)
				}
			}
		}
	}
	if len(disks) > 0 {
		info["disks"] = disks
	}
	// Legacy single disk fields (for backward compat with dashboard resource cards)
	if out, err := exec.CommandContext(r.Context(), "df", "-BM", "--output=size,used,avail,pcent", "/").Output(); err == nil {
		lines := strings.Split(strings.TrimSpace(string(out)), "\n")
		if len(lines) >= 2 {
			fields := strings.Fields(lines[1])
			if len(fields) >= 4 {
				info["disk_total"] = strings.TrimSuffix(fields[0], "M") + " MB"
				info["disk_used"] = strings.TrimSuffix(fields[1], "M") + " MB"
				info["disk_avail"] = strings.TrimSuffix(fields[2], "M") + " MB"
				info["disk_percent"] = strings.TrimSuffix(fields[3], "%")
			}
		}
	}

	// Libvirt VMs
	if out, err := exec.CommandContext(r.Context(), "virsh", "list", "--all", "--name").Output(); err == nil {
		names := []string{}
		for _, name := range strings.Split(strings.TrimSpace(string(out)), "\n") {
			if name != "" {
				names = append(names, name)
			}
		}
		info["libvirt_vms"] = names
		info["libvirt_vm_count"] = len(names)
	}

	// Running VM count
	if out, err := exec.CommandContext(r.Context(), "virsh", "list", "--state-running", "--name").Output(); err == nil {
		count := 0
		for _, name := range strings.Split(strings.TrimSpace(string(out)), "\n") {
			if name != "" {
				count++
			}
		}
		info["libvirt_running"] = count
	}

	// KVM available
	info["kvm_available"] = fileExists("/dev/kvm")

	// K3s / K8s cluster detection
	if out, err := s.kubectlCmd(r.Context(), "cluster-info").Output(); err == nil {
		info["k8s_available"] = true
		lines := strings.Split(strings.TrimSpace(string(out)), "\n")
		if len(lines) > 0 {
			info["k8s_endpoint"] = lines[0]
		}
		// Get node count
		if nodeOut, err := s.kubectlCmd(r.Context(), "get", "nodes", "--no-headers").Output(); err == nil {
			nodeLines := strings.Split(strings.TrimSpace(string(nodeOut)), "\n")
			nodes := []map[string]string{}
			for _, line := range nodeLines {
				fields := strings.Fields(line)
				if len(fields) >= 3 {
					nodes = append(nodes, map[string]string{"name": fields[0], "status": fields[1], "roles": fields[2]})
				}
			}
			info["k8s_nodes"] = nodes
			info["k8s_node_count"] = len(nodes)
		}
		// Get version
		if verOut, err := s.kubectlCmd(r.Context(), "version", "--short").Output(); err == nil {
			info["k8s_version"] = strings.TrimSpace(string(verOut))
		} else if verOut, err := s.kubectlCmd(r.Context(), "version", "--client").Output(); err == nil {
			first := strings.Split(string(verOut), "\n")[0]
			info["k8s_version"] = strings.TrimSpace(first)
		}
		// Check if K3s specifically
		if fileExists("/etc/rancher/k3s/k3s.yaml") {
			info["k3s"] = true
		}
		// KubeVirt check
		if _, err := s.kubectlCmd(r.Context(), "get", "crd", "virtualmachines.kubevirt.io").Output(); err == nil {
			info["kubevirt_available"] = true
			if vmiOut, err := s.kubectlCmd(r.Context(), "get", "vmi", "--no-headers", "-A").Output(); err == nil {
				vmiLines := strings.Split(strings.TrimSpace(string(vmiOut)), "\n")
				count := 0
				for _, l := range vmiLines {
					if strings.TrimSpace(l) != "" {
						count++
					}
				}
				info["kubevirt_vmi_count"] = count
			}
		}
		// Pod count
		if podOut, err := s.kubectlCmd(r.Context(), "get", "pods", "-A", "--no-headers").Output(); err == nil {
			podLines := strings.Split(strings.TrimSpace(string(podOut)), "\n")
			info["k8s_pod_count"] = len(podLines)
		}
	} else {
		info["k8s_available"] = false
	}

	// QEMU version
	qemuBin := "/usr/bin/qemu-system-x86_64"
	if !fileExists(qemuBin) {
		qemuBin = "/usr/libexec/qemu-kvm"
	}
	if out, err := exec.CommandContext(r.Context(), qemuBin, "--version").Output(); err == nil {
		first := strings.Split(string(out), "\n")[0]
		info["qemu_version"] = first
	}

	jsonResponse(w, http.StatusOK, info)
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

// --- Deployed VM status ---

func (s *Server) handleGetVMIP(w http.ResponseWriter, r *http.Request) {
	vmName := chi.URLParam(r, "vmName")

	// Try virsh domifaddr first (libvirt).
	out, err := exec.CommandContext(r.Context(), "virsh", "domifaddr", vmName).Output()
	if err == nil {
		ips := parseVirshIPs(string(out))
		if len(ips) > 0 {
			jsonResponse(w, http.StatusOK, map[string]interface{}{
				"vm_name":  vmName,
				"source":   "libvirt",
				"ips":      ips,
				"status":   "running",
			})
			return
		}
	}

	// Try kubectl get vmi (kubevirt).
	out, err = s.kubectlCmd(r.Context(), "get", "vmi", vmName, "-o", "jsonpath={.status.interfaces[*].ipAddress}").Output()
	if err == nil && len(out) > 0 {
		ips := strings.Fields(string(out))
		if len(ips) > 0 {
			jsonResponse(w, http.StatusOK, map[string]interface{}{
				"vm_name":  vmName,
				"source":   "kubevirt",
				"ips":      ips,
				"status":   "running",
			})
			return
		}
	}

	// Try OpenStack Nova (when openstack CLI is configured on the host).
	if openstackCLIAvailable(r.Context()) {
		if ips, source := openstackServerIPs(r.Context(), vmName, vmName+"-instance"); len(ips) > 0 {
			jsonResponse(w, http.StatusOK, map[string]interface{}{
				"vm_name": vmName,
				"source":  source,
				"ips":     ips,
				"status":  "running",
			})
			return
		}
	}

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"vm_name": vmName,
		"ips":     []string{},
		"status":  "waiting",
	})
}

func (s *Server) handleGetVMStatus(w http.ResponseWriter, r *http.Request) {
	vmName := chi.URLParam(r, "vmName")

	result := map[string]interface{}{
		"vm_name":    vmName,
		"libvirt":    map[string]interface{}{"defined": false, "running": false},
		"kubevirt":   map[string]interface{}{"defined": false, "running": false},
		"openstack":  map[string]interface{}{"defined": false, "running": false},
	}

	// Check libvirt.
	out, err := exec.CommandContext(r.Context(), "virsh", "domstate", vmName).Output()
	if err == nil {
		state := strings.TrimSpace(string(out))
		result["libvirt"] = map[string]interface{}{
			"defined": true,
			"running": state == "running",
			"state":   state,
		}
	}

	// Check kubevirt.
	out, err = s.kubectlCmd(r.Context(), "get", "vmi", vmName, "-o", "jsonpath={.status.phase}").Output()
	if err == nil && len(out) > 0 {
		phase := strings.TrimSpace(string(out))
		result["kubevirt"] = map[string]interface{}{
			"defined": true,
			"running": phase == "Running",
			"phase":   phase,
		}
	}

	if openstackCLIAvailable(r.Context()) {
		result["openstack"] = queryOpenStackDeployStatus(r.Context(), vmName)
	}

	jsonResponse(w, http.StatusOK, result)
}

// parseVirshIPs extracts IP addresses from `virsh domifaddr` output.
func parseVirshIPs(output string) []string {
	var ips []string
	for _, line := range strings.Split(output, "\n") {
		fields := strings.Fields(line)
		// Format: " vnet0 52:54:00:xx:xx:xx ipv4 192.168.122.x/24"
		for _, f := range fields {
			if strings.Contains(f, "/") && (strings.Contains(f, ".") || strings.Contains(f, ":")) {
				ip := strings.Split(f, "/")[0]
				if ip != "" {
					ips = append(ips, ip)
				}
			}
		}
	}
	return ips
}

// --- Webhooks ---

func (s *Server) handleListWebhooks(w http.ResponseWriter, r *http.Request) {
	s.webhookMu.RLock()
	hooks := make([]WebhookRegistration, len(s.webhooks))
	copy(hooks, s.webhooks)
	s.webhookMu.RUnlock()

	jsonResponse(w, http.StatusOK, hooks)
}

func (s *Server) handleRegisterWebhook(w http.ResponseWriter, r *http.Request) {
	var req struct {
		URL    string   `json:"url"`
		Events []string `json:"events,omitempty"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.URL == "" {
		jsonError(w, http.StatusBadRequest, "url is required")
		return
	}

	// Basic URL validation.
	if !strings.HasPrefix(req.URL, "http://") && !strings.HasPrefix(req.URL, "https://") {
		jsonError(w, http.StatusBadRequest, "url must start with http:// or https://")
		return
	}

	// Generate a short ID.
	idBytes := make([]byte, 4)
	rand.Read(idBytes)
	id := hex.EncodeToString(idBytes)

	hook := WebhookRegistration{
		ID:     id,
		URL:    req.URL,
		Events: req.Events,
	}

	s.webhookMu.Lock()
	if len(s.webhooks) >= 100 {
		s.webhookMu.Unlock()
		jsonError(w, http.StatusConflict, "maximum 100 webhooks reached; delete unused ones first")
		return
	}
	s.webhooks = append(s.webhooks, hook)
	s.saveWebhooks()
	s.webhookMu.Unlock()

	log.Printf("[webhook] registered id=%s url=%s events=%v from %s", hook.ID, hook.URL, hook.Events, r.RemoteAddr)

	jsonResponse(w, http.StatusCreated, hook)
}

func (s *Server) handleDeleteWebhook(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "webhookID")

	s.webhookMu.Lock()
	found := false
	for i, h := range s.webhooks {
		if h.ID == id {
			s.webhooks = append(s.webhooks[:i], s.webhooks[i+1:]...)
			found = true
			break
		}
	}
	if found {
		s.saveWebhooks()
	}
	s.webhookMu.Unlock()

	if !found {
		jsonError(w, http.StatusNotFound, "webhook not found")
		return
	}

	jsonResponse(w, http.StatusOK, map[string]string{"message": "webhook removed"})
}

// FireWebhooks sends a webhook payload to all matching registered webhooks.
// Called asynchronously -- does not block the caller.
func (s *Server) FireWebhooks(event, jobID, status, vmName string) {
	payload := WebhookPayload{
		Event:     event,
		JobID:     jobID,
		Status:    status,
		VMName:    vmName,
		Timestamp: time.Now().Format(time.RFC3339),
	}

	s.webhookMu.RLock()
	hooks := make([]WebhookRegistration, len(s.webhooks))
	copy(hooks, s.webhooks)
	s.webhookMu.RUnlock()

	if len(hooks) == 0 {
		return
	}

	log.Printf("[webhook] firing event=%s job=%s status=%s vm=%s to %d hook(s)", event, jobID, status, vmName, len(hooks))

	body, err := json.Marshal(payload)
	if err != nil {
		log.Printf("[webhook] marshal error: %v", err)
		return
	}

	for _, hook := range hooks {
		// Check if this webhook wants this event.
		if len(hook.Events) > 0 {
			matched := false
			for _, ev := range hook.Events {
				if ev == event {
					matched = true
					break
				}
			}
			if !matched {
				continue
			}
		}

		sem <- struct{}{} // Acquire semaphore slot.
		go func(url string) {
			defer func() { <-sem }() // Release slot.
			client := &http.Client{Timeout: 10 * time.Second}
			resp, err := client.Post(url, "application/json", bytes.NewReader(body))
			if err != nil {
				log.Printf("[webhook] POST %s failed: %v", url, err)
				return
			}
			resp.Body.Close()
			log.Printf("[webhook] POST %s => %d", url, resp.StatusCode)
		}(hook.URL)
	}
}

// webhookSem limits concurrent outgoing webhook HTTP requests.
var sem = make(chan struct{}, 10)

// --- Email Notifications ---

func (s *Server) handleGetEmailConfig(w http.ResponseWriter, r *http.Request) {
	s.emailMu.RLock()
	cfg := s.emailConfig
	s.emailMu.RUnlock()

	if cfg == nil {
		jsonResponse(w, http.StatusOK, map[string]interface{}{
			"configured": false,
		})
		return
	}

	// Mask password.
	masked := *cfg
	if masked.Password != "" {
		masked.Password = "********"
	}
	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"configured": true,
		"config":     masked,
	})
}

func (s *Server) handleSaveEmailConfig(w http.ResponseWriter, r *http.Request) {
	var cfg EmailConfig
	if err := readJSON(r, &cfg); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if cfg.Host == "" || cfg.Port == 0 || cfg.From == "" || len(cfg.ToAddresses) == 0 {
		jsonError(w, http.StatusBadRequest, "host, port, from, and to_addresses are required")
		return
	}

	s.emailMu.Lock()
	// If password is masked, keep the old one.
	if cfg.Password == "********" && s.emailConfig != nil {
		cfg.Password = s.emailConfig.Password
	}
	s.emailConfig = &cfg
	s.saveEmailConfig()
	s.emailMu.Unlock()

	jsonResponse(w, http.StatusOK, map[string]string{
		"message": "email configuration saved",
	})
}

func (s *Server) handleTestEmail(w http.ResponseWriter, r *http.Request) {
	s.emailMu.RLock()
	cfg := s.emailConfig
	s.emailMu.RUnlock()

	if cfg == nil || cfg.Host == "" {
		jsonError(w, http.StatusBadRequest, "email not configured")
		return
	}

	subject := "[hyper2kvm] Test Email"
	body := fmt.Sprintf("This is a test email from hyper2kvm.\n\nSent at: %s\nSMTP Host: %s:%d\n", time.Now().Format(time.RFC3339), cfg.Host, cfg.Port)

	if err := sendEmail(cfg, subject, body); err != nil {
		jsonResponse(w, http.StatusOK, map[string]interface{}{
			"success": false,
			"error":   err.Error(),
		})
		return
	}

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"success": true,
		"message": fmt.Sprintf("test email sent to %s", strings.Join(cfg.ToAddresses, ", ")),
	})
}

// --- Config Backup/Restore ---

func (s *Server) handleConfigExport(w http.ResponseWriter, r *http.Request) {
	export := map[string]interface{}{}

	// Webhooks.
	s.webhookMu.RLock()
	export["webhooks"] = s.webhooks
	s.webhookMu.RUnlock()

	// Email config (mask password).
	s.emailMu.RLock()
	if s.emailConfig != nil {
		masked := *s.emailConfig
		if masked.Password != "" {
			masked.Password = "********"
		}
		export["email"] = masked
	}
	s.emailMu.RUnlock()

	export["exported_at"] = time.Now().Format(time.RFC3339)

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Content-Disposition", "attachment; filename=hyper2kvm-config.json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(export)
}

func (s *Server) handleConfigImport(w http.ResponseWriter, r *http.Request) {
	var imported map[string]json.RawMessage
	if err := readJSON(r, &imported); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	applied := []string{}

	// Import webhooks.
	if raw, ok := imported["webhooks"]; ok {
		var hooks []WebhookRegistration
		if err := json.Unmarshal(raw, &hooks); err == nil && len(hooks) > 0 {
			s.webhookMu.Lock()
			s.webhooks = hooks
			s.saveWebhooks()
			s.webhookMu.Unlock()
			applied = append(applied, fmt.Sprintf("webhooks: %d imported", len(hooks)))
		}
	}

	// Import email config.
	if raw, ok := imported["email"]; ok {
		var cfg EmailConfig
		if err := json.Unmarshal(raw, &cfg); err == nil && cfg.Host != "" {
			s.emailMu.Lock()
			// Don't overwrite password with masked value.
			if cfg.Password == "********" && s.emailConfig != nil {
				cfg.Password = s.emailConfig.Password
			}
			s.emailConfig = &cfg
			s.saveEmailConfig()
			s.emailMu.Unlock()
			applied = append(applied, "email: config imported")
		}
	}

	if len(applied) == 0 {
		jsonError(w, http.StatusBadRequest, "no valid configuration found in import")
		return
	}

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": "configuration imported",
		"applied": applied,
	})
}

// --- VM Health Check ---

func (s *Server) handleVMHealthCheck(w http.ResponseWriter, r *http.Request) {
	vmName := chi.URLParam(r, "vmName")

	sshUser := r.URL.Query().Get("ssh_user")
	if sshUser == "" {
		sshUser = "root"
	}

	result := map[string]interface{}{
		"vm_name":      vmName,
		"running":      false,
		"ip":           "",
		"ssh_reachable": false,
		"guest_agent":  false,
		"ssh_user":     sshUser,
	}

	// Check if VM is running.
	stateCtx, stateCancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer stateCancel()
	stateOut, err := exec.CommandContext(stateCtx, "virsh", "domstate", vmName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, fmt.Sprintf("VM %s not found", vmName))
		return
	}
	state := strings.TrimSpace(string(stateOut))
	result["running"] = state == "running"

	if state != "running" {
		jsonResponse(w, http.StatusOK, result)
		return
	}

	// Get IP address.
	ipCtx, ipCancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer ipCancel()
	ipOut, err := exec.CommandContext(ipCtx, "virsh", "domifaddr", vmName).Output()
	if err == nil {
		ips := parseVirshIPs(string(ipOut))
		if len(ips) > 0 {
			result["ip"] = ips[0]

			// Check SSH reachability.
			sshCtx, sshCancel := context.WithTimeout(r.Context(), 3*time.Second)
			defer sshCancel()
			conn, err := (&net.Dialer{}).DialContext(sshCtx, "tcp", ips[0]+":22")
			if err == nil {
				conn.Close()
				result["ssh_reachable"] = true
			}
		}
	}

	// Check guest agent.
	agentCtx, agentCancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer agentCancel()
	if err := exec.CommandContext(agentCtx, "virsh", "qemu-agent-command", vmName, `{"execute":"guest-ping"}`).Run(); err == nil {
		result["guest_agent"] = true
	}

	jsonResponse(w, http.StatusOK, result)
}

// --- Top VMs ---

// handleTopVMs returns the top 5 VMs by CPU time and memory usage.
func (s *Server) handleTopVMs(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()

	// Get running VMs.
	listOut, err := exec.CommandContext(ctx, "virsh", "list", "--name").Output()
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "virsh list failed")
		return
	}

	var vmNames []string
	for _, line := range strings.Split(strings.TrimSpace(string(listOut)), "\n") {
		name := strings.TrimSpace(line)
		if name != "" {
			vmNames = append(vmNames, name)
		}
	}

	type vmCPU struct {
		Name       string  `json:"name"`
		CPUTimeNs  uint64  `json:"cpu_time_ns"`
		CPUPercent float64 `json:"cpu_percent"`
	}
	type vmMem struct {
		Name          string  `json:"name"`
		MemoryMB      uint64  `json:"memory_mb"`
		MemoryPercent float64 `json:"memory_percent"`
	}

	var cpuList []vmCPU
	var memList []vmMem

	// Get host total memory for percentage calculation.
	var hostMemKB uint64
	meminfoOut, _ := os.ReadFile("/proc/meminfo")
	for _, line := range strings.Split(string(meminfoOut), "\n") {
		if strings.HasPrefix(line, "MemTotal:") {
			fields := strings.Fields(line)
			if len(fields) >= 2 {
				if v, err := strconv.ParseUint(fields[1], 10, 64); err == nil {
					hostMemKB = v
				}
			}
			break
		}
	}

	// Get host CPU count for percentage calculation.
	var hostCPUs int
	cpuInfoOut, _ := exec.CommandContext(ctx, "nproc").Output()
	if v, err := strconv.Atoi(strings.TrimSpace(string(cpuInfoOut))); err == nil {
		hostCPUs = v
	}

	for _, vmName := range vmNames {
		statsCtx, statsCancel := context.WithTimeout(ctx, 3*time.Second)
		statsOut, err := exec.CommandContext(statsCtx, "virsh", "domstats", vmName, "--cpu-total", "--balloon").Output()
		statsCancel()
		if err != nil {
			continue
		}

		var cpuTimeNs uint64
		var balloonCurrentKB, balloonMaxKB uint64

		for _, line := range strings.Split(string(statsOut), "\n") {
			line = strings.TrimSpace(line)
			parts := strings.SplitN(line, "=", 2)
			if len(parts) != 2 {
				continue
			}
			key := strings.TrimSpace(parts[0])
			val := strings.TrimSpace(parts[1])

			switch key {
			case "cpu.time":
				if v, err := strconv.ParseUint(val, 10, 64); err == nil {
					cpuTimeNs = v
				}
			case "balloon.current":
				if v, err := strconv.ParseUint(val, 10, 64); err == nil {
					balloonCurrentKB = v
				}
			case "balloon.maximum":
				if v, err := strconv.ParseUint(val, 10, 64); err == nil {
					balloonMaxKB = v
				}
			}
		}

		// CPU percent estimate: cpu_time is nanoseconds since boot.
		// We estimate percentage relative to host CPUs and uptime (rough).
		var cpuPct float64
		if hostCPUs > 0 {
			// Get VM uptime by checking /proc/uptime for a rough percentage.
			// Using a simple heuristic: cpu_time / (uptime * nCPU * 1e9) * 100.
			uptimeBytes, _ := os.ReadFile("/proc/uptime")
			if fields := strings.Fields(string(uptimeBytes)); len(fields) >= 1 {
				if uptime, err := strconv.ParseFloat(fields[0], 64); err == nil && uptime > 0 {
					cpuPct = float64(cpuTimeNs) / (uptime * float64(hostCPUs) * 1e9) * 100.0
					if cpuPct > 100 {
						cpuPct = 100
					}
				}
			}
		}

		cpuList = append(cpuList, vmCPU{
			Name:       vmName,
			CPUTimeNs:  cpuTimeNs,
			CPUPercent: math.Round(cpuPct*10) / 10,
		})

		memMB := balloonCurrentKB / 1024
		if memMB == 0 {
			memMB = balloonMaxKB / 1024
		}
		var memPct float64
		if hostMemKB > 0 {
			memPct = float64(balloonCurrentKB) / float64(hostMemKB) * 100.0
		}

		memList = append(memList, vmMem{
			Name:          vmName,
			MemoryMB:      memMB,
			MemoryPercent: math.Round(memPct*10) / 10,
		})
	}

	// Sort by CPU time descending, take top 5.
	sort.Slice(cpuList, func(i, j int) bool {
		return cpuList[i].CPUTimeNs > cpuList[j].CPUTimeNs
	})
	if len(cpuList) > 5 {
		cpuList = cpuList[:5]
	}

	// Sort by memory descending, take top 5.
	sort.Slice(memList, func(i, j int) bool {
		return memList[i].MemoryMB > memList[j].MemoryMB
	})
	if len(memList) > 5 {
		memList = memList[:5]
	}

	log.Printf("[vm] topVMs: %d running VMs, returning top %d CPU / %d memory", len(vmNames), len(cpuList), len(memList))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"by_cpu":    cpuList,
		"by_memory": memList,
	})
}

// --- API Docs ---

func (s *Server) handleAPIDocs(w http.ResponseWriter, r *http.Request) {
	log.Printf("[api] API docs accessed from %s", r.RemoteAddr)
	type paramDoc struct {
		Name     string `json:"name"`
		In       string `json:"in"` // "query", "path", "body"
		Required bool   `json:"required"`
		Type     string `json:"type"`
	}
	type endpointDoc struct {
		Method      string     `json:"method"`
		Path        string     `json:"path"`
		Description string     `json:"description"`
		Params      []paramDoc `json:"params,omitempty"`
		ExampleReq  string     `json:"example_request,omitempty"`
		ExampleResp string     `json:"example_response,omitempty"`
	}

	docs := []endpointDoc{
		// Auth
		{Method: "POST", Path: "/api/v1/auth/login", Description: "Authenticate with PAM credentials",
			ExampleReq:  `{"username":"admin","password":"secret"}`,
			ExampleResp: `{"status":"ok","username":"admin"}`},
		{Method: "POST", Path: "/api/v1/auth/logout", Description: "End the current session"},
		{Method: "GET", Path: "/api/v1/auth/session", Description: "Check current session status"},

		// Health
		{Method: "GET", Path: "/api/v1/health", Description: "Health check (public, no auth required)"},
		{Method: "GET", Path: "/api/v1/status", Description: "Server status with job stats, providers, and WebSocket client count"},

		// Providers
		{Method: "GET", Path: "/api/v1/providers", Description: "List all connected migration providers"},
		{Method: "POST", Path: "/api/v1/providers", Description: "Connect a new provider (vSphere, Azure, etc.)",
			ExampleReq: `{"type":"vsphere","host":"vcenter.example.com","username":"admin","password":"secret"}`},
		{Method: "POST", Path: "/api/v1/providers/test", Description: "Test provider connection without persisting"},
		{Method: "GET", Path: "/api/v1/providers/{providerID}", Description: "Get provider details"},
		{Method: "DELETE", Path: "/api/v1/providers/{providerID}", Description: "Disconnect a provider"},
		{Method: "GET", Path: "/api/v1/providers/{providerID}/vms", Description: "List VMs from a provider",
			Params: []paramDoc{
				{Name: "name", In: "query", Type: "string"},
				{Name: "state", In: "query", Type: "string"},
			}},
		{Method: "GET", Path: "/api/v1/providers/{providerID}/vms/{vmID}", Description: "Get VM details from provider"},

		// Migrations
		{Method: "POST", Path: "/api/v1/migrations/preview", Description: "Preview migration config as YAML"},
		{Method: "POST", Path: "/api/v1/migrations/submit", Description: "Submit a single migration job",
			ExampleReq:  `{"command":"local","vmdk":"/data/vm.vmdk","output_dir":"/var/lib/libvirt/images"}`,
			ExampleResp: `{"job_id":"abc12345","message":"migration submitted"}`},
		{Method: "POST", Path: "/api/v1/migrations/batch", Description: "Submit multiple migrations at once",
			ExampleReq:  `{"configs":[{"command":"local","vmdk":"/data/vm1.vmdk"},{"command":"local","vmdk":"/data/vm2.vmdk"}]}`,
			ExampleResp: `{"jobs":[{"id":"abc12345","source":"/data/vm1.vmdk"}],"total":2}`},

		// Jobs
		{Method: "GET", Path: "/api/v1/jobs", Description: "List all migration jobs"},
		{Method: "GET", Path: "/api/v1/jobs/stats", Description: "Get aggregate job statistics"},
		{Method: "GET", Path: "/api/v1/jobs/{jobID}", Description: "Get job details by ID"},
		{Method: "POST", Path: "/api/v1/jobs/{jobID}/cancel", Description: "Cancel a running or pending job"},
		{Method: "GET", Path: "/api/v1/jobs/{jobID}/logs", Description: "Get job log lines"},
		{Method: "GET", Path: "/api/v1/jobs/{jobID}/report", Description: "Download migration report as text file"},

		// Libvirt VMs
		{Method: "GET", Path: "/api/v1/vms", Description: "List all libvirt VMs with optional filtering",
			Params: []paramDoc{
				{Name: "state", In: "query", Type: "string", Required: false},
				{Name: "os", In: "query", Type: "string", Required: false},
				{Name: "search", In: "query", Type: "string", Required: false},
			},
			ExampleResp: `[{"name":"myvm","state":"running","os_type":"linux","memory":"2097152 KiB","vcpus":"2"}]`},
		{Method: "POST", Path: "/api/v1/vms/bulk-action", Description: "Perform action on multiple VMs",
			ExampleReq:  `{"names":["vm1","vm2"],"action":"start"}`,
			ExampleResp: `{"results":[{"name":"vm1","success":true},{"name":"vm2","success":true}]}`},
		{Method: "GET", Path: "/api/v1/vms/{vmName}/stats", Description: "Get VM domstats"},
		{Method: "GET", Path: "/api/v1/vms/{vmName}/stats/live", Description: "Get live CPU and memory stats"},
		{Method: "GET", Path: "/api/v1/vms/{vmName}/vnc", Description: "Get VNC connection details"},
		{Method: "GET", Path: "/api/v1/vms/{vmName}/screenshot", Description: "Get VM screenshot as PNG"},
		{Method: "POST", Path: "/api/v1/vms/{vmName}/start", Description: "Start a VM"},
		{Method: "POST", Path: "/api/v1/vms/{vmName}/stop", Description: "Gracefully shut down a VM"},
		{Method: "POST", Path: "/api/v1/vms/{vmName}/reboot", Description: "Reboot a VM"},
		{Method: "POST", Path: "/api/v1/vms/{vmName}/destroy", Description: "Force stop a VM"},
		{Method: "POST", Path: "/api/v1/vms/{vmName}/delete", Description: "Delete a VM and its storage"},
		{Method: "POST", Path: "/api/v1/vms/{vmName}/autostart", Description: "Enable/disable VM autostart",
			ExampleReq: `{"enable":true}`},
		{Method: "GET", Path: "/api/v1/vms/{vmName}/guest-info", Description: "Query QEMU guest agent for VM internals (hostname, OS, filesystems, network interfaces)",
			ExampleResp: `{"available":true,"hostname":"myvm","os":{"name":"Ubuntu","version":"24.04","kernel":"6.8.0"},"filesystems":[{"mountpoint":"/","type":"ext4","total_bytes":53687091200}],"interfaces":[{"name":"eth0","ip":"192.168.122.10","mac":"52:54:00:ab:cd:ef"}]}`},
		{Method: "GET", Path: "/api/v1/vms/{vmName}/status-detail", Description: "Get enriched VM status with reason, warnings, and resource pressure",
			ExampleResp: `{"state":"running","reason":"booted","state_detail":"Running (booted) — no issues detected","warnings":[],"resource_pressure":{"cpu_percent":85.2,"memory_percent":45.0}}`},
		{Method: "GET", Path: "/api/v1/vms/{vmName}/xml", Description: "Get raw domain XML (virsh dumpxml) for a VM",
			ExampleResp: `{"xml":"<domain type='kvm'>...</domain>"}`},
		{Method: "GET", Path: "/api/v1/vms/{vmName}/connectivity-test", Description: "Test VM network reachability (ping + port scan for SSH, HTTP, RDP)",
			ExampleResp: `{"ip":"192.168.122.26","reachable":true,"ports":[{"port":22,"name":"SSH","open":true},{"port":80,"name":"HTTP","open":false},{"port":3389,"name":"RDP","open":false}]}`},
		{Method: "GET", Path: "/api/v1/vms/{vmName}/recommendations", Description: "Get smart recommendations for VM optimization (disk bus, guest agent, storage format, hugepages)",
			ExampleResp: `{"recommendations":[{"type":"performance","severity":"medium","title":"Upgrade to VirtIO disk bus","detail":"Current bus: sata. VirtIO provides better I/O performance.","action":"promote"}],"score":85}`},
		{Method: "GET", Path: "/api/v1/vms/{vmName}/security", Description: "Security exposure analysis (host passthrough, VNC binding, block devices, CPU mode)",
			ExampleResp: `{"findings":[{"severity":"medium","category":"console","title":"VNC on 0.0.0.0","detail":"VNC console accessible from all network interfaces."}],"score":90,"summary":"1 findings (1 medium)"}`},
		{Method: "GET", Path: "/api/v1/vms/{vmName}/storage-detail", Description: "Get VM storage detail (block stats, disk sizes, snapshot tree, pool info)",
			ExampleResp: `{"disks":[{"target":"vda","source":"/var/lib/libvirt/images/vm.qcow2","read_bytes":1234567,"write_bytes":7654321,"read_ops":100,"write_ops":50,"errors":0,"capacity_bytes":21474836480,"allocation_bytes":5368709120}],"snapshot_tree":"snap1","pool":{"name":"default","capacity_gb":100.0,"used_gb":45.2,"available_gb":54.8}}`},
		{Method: "GET", Path: "/api/v1/vms/{vmName}/processes", Description: "View running processes inside a VM via QEMU guest agent (top 15 by CPU)",
			ExampleResp: `{"available":true,"processes":[{"user":"root","pid":1,"cpu":0.5,"mem":1.2,"command":"/sbin/init"}]}`},
		{Method: "GET", Path: "/api/v1/vms/{vmName}/network-detail", Description: "Get detailed network interface info with traffic stats (domiflist + domifstat)",
			ExampleResp: `{"interfaces":[{"name":"vnet0","mac":"52:54:00:xx:xx:xx","source":"virbr0","model":"virtio","rx_bytes":123456,"tx_bytes":654321,"rx_packets":1000,"tx_packets":500,"rx_errors":0,"tx_errors":0,"rx_drops":0,"tx_drops":0}]}`},
		{Method: "POST", Path: "/api/v1/vms/create", Description: "Create a new VM via virt-install",
			ExampleReq:  `{"name":"my-new-vm","vcpus":2,"memory_mb":2048,"disk_gb":20,"os_variant":"generic","network":"default","cdrom":"/path/to/iso"}`,
			ExampleResp: `{"message":"VM my-new-vm created successfully","name":"my-new-vm"}`},
		{Method: "POST", Path: "/api/v1/vms/clone", Description: "Clone an existing VM using virt-clone",
			ExampleReq:  `{"source":"my-vm","name":"my-vm-clone"}`,
			ExampleResp: `{"message":"VM cloned","name":"my-vm-clone"}`},
		{Method: "POST", Path: "/api/v1/vms/import", Description: "Import an existing disk image as a new VM",
			ExampleReq:  `{"name":"imported-vm","disk_path":"/var/lib/libvirt/images/disk.qcow2","vcpus":2,"memory_mb":2048,"os_variant":"generic"}`,
			ExampleResp: `{"message":"VM imported-vm imported successfully","name":"imported-vm","disk_path":"/var/lib/libvirt/images/disk.qcow2"}`},
		{Method: "POST", Path: "/api/v1/vms/{vmName}/resize", Description: "Resize VM vCPUs and/or memory (hot for running, config for stopped)",
			ExampleReq:  `{"vcpus":4,"memory_mb":4096}`,
			ExampleResp: `{"message":"VM resized","vcpus":4,"memory_mb":4096}`},

		// Disk & CDROM management
		{Method: "POST", Path: "/api/v1/vms/{vmName}/disk/attach", Description: "Create and attach a new disk to a VM",
			ExampleReq:  `{"size_gb":10,"format":"qcow2","bus":"virtio"}`,
			ExampleResp: `{"message":"Disk attached as vdb","target":"vdb","path":"/var/lib/libvirt/images/myvm-extra-1712678400.qcow2","size_gb":10}`},
		{Method: "POST", Path: "/api/v1/vms/{vmName}/disk/detach", Description: "Detach a disk from a VM",
			ExampleReq:  `{"target":"vdb"}`,
			ExampleResp: `{"message":"Disk vdb detached","target":"vdb"}`},
		{Method: "POST", Path: "/api/v1/vms/{vmName}/cdrom/change", Description: "Insert or eject ISO in VM CDROM drive (empty path = eject)",
			ExampleReq:  `{"path":"/path/to/install.iso"}`,
			ExampleResp: `{"message":"CDROM sda: inserted","target":"sda","action":"inserted","path":"/path/to/install.iso"}`},

		// VM Events
		{Method: "GET", Path: "/api/v1/vms/{vmName}/events", Description: "Get VM lifecycle events from current state, disk errors, and audit log",
			ExampleResp: `{"events":[{"timestamp":"2026-04-09T12:00:00Z","type":"lifecycle","action":"current_state","detail":"running (booted)"}]}`},

		// Libvirt-to-KubeVirt migration
		{Method: "POST", Path: "/api/v1/vms/{vmName}/migrate-to-kubevirt", Description: "Migrate a libvirt VM to KubeVirt (convert disks, upload PVCs, create VM CR)",
			ExampleReq:  `{"namespace":"default","kubevirt_vm_name":"my-vm","storage_class":"local-path","auto_stop":true,"auto_start":true}`,
			ExampleResp: `{"message":"VM myvm migrated to KubeVirt as default/my-vm","vm_name":"my-vm","namespace":"default","disks":1,"pvc_names":["my-vm-disk0"],"uefi":false,"windows":false,"vcpus":2,"memory_mb":2048}`},

		// Top VMs
		{Method: "GET", Path: "/api/v1/vms/top", Description: "Get top 5 VMs by CPU and memory consumption",
			ExampleResp: `{"by_cpu":[{"name":"vm1","cpu_time_ns":123456789,"cpu_percent":45.2}],"by_memory":[{"name":"vm1","memory_mb":2048,"memory_percent":50.0}]}`},

		// Activity feed
		{Method: "GET", Path: "/api/v1/activity", Description: "Get recent activity feed (last 20 audit entries, newest first)",
			ExampleResp: `{"activities":[{"timestamp":"2026-04-09T12:00:00Z","user":"admin","action":"vm_start","target":"myvm","result":"ok"}],"total":1}`},

		// Snapshots
		{Method: "GET", Path: "/api/v1/vms/{vmName}/snapshots", Description: "List VM snapshots"},
		{Method: "POST", Path: "/api/v1/vms/{vmName}/snapshots", Description: "Create a VM snapshot",
			ExampleReq: `{"name":"before-update","description":"Snapshot before OS update"}`},
		{Method: "POST", Path: "/api/v1/vms/{vmName}/snapshots/{snapName}/revert", Description: "Revert to a snapshot"},
		{Method: "DELETE", Path: "/api/v1/vms/{vmName}/snapshots/{snapName}", Description: "Delete a snapshot"},

		// Console / VNC proxy
		{Method: "GET", Path: "/api/v1/vnc-proxy/{vmName}", Description: "WebSocket VNC proxy for libvirt VM"},
		{Method: "GET", Path: "/api/v1/console/{vmName}", Description: "Start noVNC console proxy"},

		// Networks
		{Method: "GET", Path: "/api/v1/networks", Description: "List libvirt networks"},
		{Method: "POST", Path: "/api/v1/networks/{name}/start", Description: "Start a network"},
		{Method: "POST", Path: "/api/v1/networks/{name}/stop", Description: "Stop a network"},
		{Method: "GET", Path: "/api/v1/networks/topology", Description: "Get network topology with VM mappings"},

		// KubeVirt
		{Method: "GET", Path: "/api/v1/kubevirt/vms", Description: "List all KubeVirt VMs"},
		{Method: "GET", Path: "/api/v1/kubevirt/vmis", Description: "List all KubeVirt VM instances"},
		{Method: "GET", Path: "/api/v1/kubevirt/vms/{ns}/{name}", Description: "Get KubeVirt VM details"},
		{Method: "POST", Path: "/api/v1/kubevirt/vms/{ns}/{name}/start", Description: "Start a KubeVirt VM"},
		{Method: "POST", Path: "/api/v1/kubevirt/vms/{ns}/{name}/stop", Description: "Stop a KubeVirt VM"},
		{Method: "DELETE", Path: "/api/v1/kubevirt/vms/{ns}/{name}", Description: "Delete a KubeVirt VM"},

		// Multi-kubeconfig management
		{Method: "GET", Path: "/api/v1/kubeconfigs", Description: "List all registered kubeconfigs with live connection status",
			ExampleResp: `{"active":"production","clusters":[{"id":"production","name":"Production","connected":true,"version":"v1.28.3","server_url":"https://k8s.example.com:6443","is_active":true}]}`},
		{Method: "POST", Path: "/api/v1/kubeconfigs/add", Description: "Add a kubeconfig via file upload (multipart/form-data) or server path (application/json)",
			ExampleReq:  `{"name":"staging","path":"/etc/rancher/k3s/k3s.yaml"}`,
			ExampleResp: `{"id":"staging","name":"staging","source":"path","filename":"staging.kubeconfig","added_at":"2026-04-09T12:00:00Z"}`},
		{Method: "PUT", Path: "/api/v1/kubeconfigs/{id}/activate", Description: "Set a cluster as the active kubeconfig for all KubeVirt operations",
			ExampleResp: `{"status":"activated","active":"staging"}`},
		{Method: "DELETE", Path: "/api/v1/kubeconfigs/{id}", Description: "Remove a kubeconfig entry and its file",
			ExampleResp: `{"status":"deleted","cluster":"staging"}`},

		// Audit log
		{Method: "GET", Path: "/api/v1/audit", Description: "Get audit log entries (in-memory, last 500)",
			Params: []paramDoc{
				{Name: "limit", In: "query", Type: "integer", Required: false},
			},
			ExampleResp: `[{"timestamp":"2026-04-02T10:00:00Z","user":"admin","action":"vm_start","target":"myvm","result":"ok"}]`},

		// Webhooks
		{Method: "GET", Path: "/api/v1/webhooks", Description: "List registered webhooks"},
		{Method: "POST", Path: "/api/v1/webhooks", Description: "Register a webhook URL",
			ExampleReq:  `{"url":"https://example.com/hook","events":["job_completed","job_failed"]}`,
			ExampleResp: `{"id":"a1b2c3d4","url":"https://example.com/hook","events":["job_completed","job_failed"]}`},
		{Method: "DELETE", Path: "/api/v1/webhooks/{id}", Description: "Remove a registered webhook"},

		// Host
		{Method: "GET", Path: "/api/v1/host/info", Description: "Get host system information (CPU, memory, disks, libvirt, K8s)"},
		{Method: "GET", Path: "/api/v1/capacity", Description: "Get cluster capacity overview (host resources, VM allocations, utilization percentages)",
			ExampleResp: `{"host":{"cpus":16,"memory_total_gb":64.0,"memory_used_gb":32.5,"storage_total_gb":500,"storage_used_gb":210},"vms":{"total":10,"running":6,"vcpus_allocated":24,"memory_allocated_gb":48.0},"utilization":{"cpu_percent":45.0,"memory_percent":50.8,"storage_percent":42.0}}`},
		{Method: "GET", Path: "/api/v1/readiness", Description: "Check migration readiness (tools, modules, services)"},
		{Method: "GET", Path: "/api/v1/disk-images", Description: "Discover disk images on the server"},

		// Storage
		{Method: "GET", Path: "/api/v1/storage/config", Description: "Get storage configuration and usage"},
		{Method: "POST", Path: "/api/v1/storage/relocate", Description: "Relocate libvirt image storage to a new path",
			ExampleReq: `{"target_dir":"/data/libvirt/images","move_data":true}`},
		{Method: "GET", Path: "/api/v1/storage/artifacts", Description: "List conversion output and input artifacts with sizes",
			ExampleResp: `{"artifacts":[{"name":"vm.qcow2","path":"/var/lib/hyper2kvm/output/vm.qcow2","size_bytes":10737418240,"modified":"2026-04-09T12:00:00Z","dir":"output"}],"total_bytes":10737418240,"total_human":"10.0 GB"}`},
		{Method: "POST", Path: "/api/v1/storage/cleanup", Description: "Delete conversion artifacts (output and/or input files)",
			ExampleReq:  `{"dirs":["output","input"],"older_than_hours":0}`,
			ExampleResp: `{"deleted":5,"freed_bytes":12345678900,"freed_human":"12.3 GB"}`},

		// File management
		{Method: "GET", Path: "/api/v1/browse", Description: "Browse server filesystem",
			Params: []paramDoc{
				{Name: "path", In: "query", Type: "string"},
				{Name: "filter", In: "query", Type: "string"},
			}},
		{Method: "POST", Path: "/api/v1/upload", Description: "Upload a disk image file (multipart)"},
		{Method: "POST", Path: "/api/v1/upload/init", Description: "Initialize chunked upload session"},
		{Method: "POST", Path: "/api/v1/upload/chunk", Description: "Upload a single chunk"},
		{Method: "POST", Path: "/api/v1/upload/complete", Description: "Finalize chunked upload"},
		{Method: "GET", Path: "/api/v1/upload/status/{uploadId}", Description: "Get chunked upload progress"},
		{Method: "GET", Path: "/api/v1/download", Description: "Download a disk image file",
			Params: []paramDoc{
				{Name: "path", In: "query", Type: "string", Required: true},
			}},

		// Deploy status
		{Method: "GET", Path: "/api/v1/deploy/{vmName}/ip", Description: "Get deployed VM IP address"},
		{Method: "GET", Path: "/api/v1/deploy/{vmName}/status", Description: "Get deployed VM status (libvirt, kubevirt, openstack)"},

		// Users
		{Method: "GET", Path: "/api/v1/users", Description: "List system users with migration access"},
		{Method: "POST", Path: "/api/v1/users", Description: "Create a new migration operator user",
			ExampleReq: `{"username":"operator1","password":"secret","sudo":true}`},

		// WebSocket
		{Method: "GET", Path: "/api/v1/ws", Description: "WebSocket connection for real-time job events"},

		// API docs
		{Method: "GET", Path: "/api/v1/docs", Description: "This endpoint -- list all API endpoints with documentation"},
	}

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"version":   "v1",
		"base_url":  "/api/v1",
		"endpoints": docs,
		"total":     len(docs),
	})
}

// --- File upload ---

// allowedUploadExts lists the file extensions accepted for upload.
var allowedUploadExts = map[string]bool{
	".vmdk": true, ".ova": true, ".ovf": true,
	".vhd": true, ".vhdx": true, ".qcow2": true,
	".raw": true, ".img": true,
}

// filenameSanitizer replaces anything that isn't alphanumeric, dash, underscore, or dot.
var filenameSanitizer = regexp.MustCompile(`[^a-zA-Z0-9._-]`)

const uploadDir = "/var/lib/hyper2kvm/input"

// uploadMu prevents concurrent uploads of the same filename from racing.
var uploadMu sync.Mutex

func (s *Server) handleUpload(w http.ResponseWriter, r *http.Request) {
	uploadStart := time.Now()
	log.Printf("[upload] request from %s, content-length=%d", r.RemoteAddr, r.ContentLength)

	// 50 GB max body size.
	r.Body = http.MaxBytesReader(w, r.Body, 50<<30)

	// 32 MB memory buffer — the rest spills to disk automatically.
	if err := r.ParseMultipartForm(32 << 20); err != nil {
		jsonError(w, http.StatusBadRequest, "parse form failed: "+err.Error())
		return
	}

	file, header, err := r.FormFile("file")
	if err != nil {
		jsonError(w, http.StatusBadRequest, "no file in request")
		return
	}
	defer file.Close()

	log.Printf("[upload] original filename=%q reported-size=%d", header.Filename, header.Size)

	// Sanitize filename: strip path components, replace unsafe chars.
	name := filepath.Base(filenameSanitizer.ReplaceAllString(header.Filename, "_"))
	if name == "" || name == "." || name == ".." || strings.HasPrefix(name, ".") {
		jsonError(w, http.StatusBadRequest, "invalid filename")
		return
	}

	// Validate extension.
	ext := strings.ToLower(filepath.Ext(name))
	if !allowedUploadExts[ext] {
		allowed := make([]string, 0, len(allowedUploadExts))
		for k := range allowedUploadExts {
			allowed = append(allowed, k)
		}
		jsonError(w, http.StatusBadRequest, "unsupported file type: "+ext+". Allowed: "+strings.Join(allowed, ", "))
		return
	}

	// Ensure upload directory exists.
	if err := os.MkdirAll(uploadDir, 0755); err != nil {
		jsonError(w, http.StatusInternalServerError, "cannot create upload dir: "+err.Error())
		return
	}

	// Serialize filename dedup to prevent concurrent uploads overwriting each other.
	uploadMu.Lock()
	destPath := filepath.Join(uploadDir, name)
	if _, err := os.Stat(destPath); err == nil {
		base := strings.TrimSuffix(name, ext)
		stamp := time.Now().Format("20060102-150405")
		name = base + "_" + stamp + ext
		destPath = filepath.Join(uploadDir, name)
	}
	// Create the file while holding the lock to reserve the name.
	dst, err := os.Create(destPath)
	uploadMu.Unlock()
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "create file failed: "+err.Error())
		return
	}

	// Stream the upload. Clean up partial file on any error.
	written, err := io.Copy(dst, file)
	if err != nil {
		dst.Close()
		os.Remove(destPath)
		jsonError(w, http.StatusInternalServerError, "write failed: "+err.Error())
		return
	}

	// Sync to disk before reporting success.
	if err := dst.Sync(); err != nil {
		dst.Close()
		os.Remove(destPath)
		jsonError(w, http.StatusInternalServerError, "sync failed: "+err.Error())
		return
	}
	dst.Close()

	elapsed := time.Since(uploadStart)
	format := strings.TrimPrefix(ext, ".")
	speed := float64(0)
	if elapsed.Seconds() > 0 {
		speed = float64(written) / elapsed.Seconds() / (1024 * 1024)
	}
	log.Printf("[upload] saved %s (%d bytes, format=%s, sanitized=%s, elapsed=%s, speed=%.1f MB/s)", destPath, written, format, name, elapsed.Round(time.Millisecond), speed)

	s.metrics.UploadsTotal.Add(1)
	s.metrics.UploadBytesTotal.Add(written)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"path":   destPath,
		"name":   name,
		"size":   written,
		"format": format,
	})
}

// --- Chunked / resumable upload ---

const chunkedUploadDir = uploadDir + "/.uploads"
const defaultChunkSize = 10 * 1024 * 1024 // 10 MB

// uploadIDSanitizer allows only alphanumeric and dash characters.
var uploadIDSanitizer = regexp.MustCompile(`[^a-zA-Z0-9-]`)

// chunkedUploadMeta is persisted as meta.json inside the upload session dir.
type chunkedUploadMeta struct {
	UploadID    string `json:"upload_id"`
	Filename    string `json:"filename"`
	Size        int64  `json:"size"`
	ChunkSize   int64  `json:"chunk_size"`
	TotalChunks int    `json:"total_chunks"`
	CreatedAt   string `json:"created_at"`
}

// generateUploadID creates a unique upload session identifier.
func generateUploadID() string {
	b := make([]byte, 8)
	rand.Read(b)
	return fmt.Sprintf("%s-%s", time.Now().Format("20060102-150405"), hex.EncodeToString(b))
}

// sanitizeUploadID validates and cleans an upload ID.
func sanitizeUploadID(id string) string {
	return uploadIDSanitizer.ReplaceAllString(id, "")
}

// readChunkedMeta loads meta.json for a given upload session.
func readChunkedMeta(uploadID string) (*chunkedUploadMeta, string, error) {
	clean := sanitizeUploadID(uploadID)
	if clean == "" || clean != uploadID {
		return nil, "", fmt.Errorf("invalid upload_id")
	}
	sessionDir := filepath.Join(chunkedUploadDir, clean)
	metaPath := filepath.Join(sessionDir, "meta.json")
	data, err := os.ReadFile(metaPath)
	if err != nil {
		return nil, "", fmt.Errorf("upload session not found")
	}
	var meta chunkedUploadMeta
	if err := json.Unmarshal(data, &meta); err != nil {
		return nil, "", fmt.Errorf("corrupt session metadata")
	}
	return &meta, sessionDir, nil
}

// receivedChunks returns the sorted list of chunk indices already saved.
func receivedChunks(sessionDir string, totalChunks int) []int {
	var received []int
	for i := 0; i < totalChunks; i++ {
		chunkPath := filepath.Join(sessionDir, strconv.Itoa(i))
		if _, err := os.Stat(chunkPath); err == nil {
			received = append(received, i)
		}
	}
	sort.Ints(received)
	return received
}

func (s *Server) handleUploadInit(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Filename  string `json:"filename"`
		Size      int64  `json:"size"`
		ChunkSize int64  `json:"chunk_size"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.Filename == "" || req.Size <= 0 {
		jsonError(w, http.StatusBadRequest, "filename and size are required")
		return
	}

	// Sanitize filename.
	name := filepath.Base(filenameSanitizer.ReplaceAllString(req.Filename, "_"))
	if name == "" || name == "." || name == ".." || strings.HasPrefix(name, ".") {
		jsonError(w, http.StatusBadRequest, "invalid filename")
		return
	}

	// Validate extension.
	ext := strings.ToLower(filepath.Ext(name))
	if !allowedUploadExts[ext] {
		allowed := make([]string, 0, len(allowedUploadExts))
		for k := range allowedUploadExts {
			allowed = append(allowed, k)
		}
		jsonError(w, http.StatusBadRequest, "unsupported file type: "+ext+". Allowed: "+strings.Join(allowed, ", "))
		return
	}

	chunkSize := req.ChunkSize
	if chunkSize <= 0 {
		chunkSize = int64(defaultChunkSize)
	}

	totalChunks := int((req.Size + chunkSize - 1) / chunkSize)
	uploadID := generateUploadID()

	sessionDir := filepath.Join(chunkedUploadDir, uploadID)
	if err := os.MkdirAll(sessionDir, 0755); err != nil {
		jsonError(w, http.StatusInternalServerError, "cannot create session dir: "+err.Error())
		return
	}

	meta := chunkedUploadMeta{
		UploadID:    uploadID,
		Filename:    name,
		Size:        req.Size,
		ChunkSize:   chunkSize,
		TotalChunks: totalChunks,
		CreatedAt:   time.Now().Format(time.RFC3339),
	}
	metaBytes, err := json.Marshal(meta)
	if err != nil {
		log.Printf("[warn] json marshal failed: %v", err)
	}
	if err := os.WriteFile(filepath.Join(sessionDir, "meta.json"), metaBytes, 0644); err != nil {
		jsonError(w, http.StatusInternalServerError, "cannot write metadata: "+err.Error())
		return
	}

	log.Printf("[upload/init] session=%s file=%s size=%d chunks=%d chunkSize=%d", uploadID, name, req.Size, totalChunks, chunkSize)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"upload_id":    uploadID,
		"chunk_size":   chunkSize,
		"total_chunks": totalChunks,
	})
}

func (s *Server) handleUploadChunk(w http.ResponseWriter, r *http.Request) {
	// 32 MB max per chunk request.
	r.Body = http.MaxBytesReader(w, r.Body, 32<<20)

	if err := r.ParseMultipartForm(32 << 20); err != nil {
		jsonError(w, http.StatusBadRequest, "parse form failed: "+err.Error())
		return
	}

	uploadID := sanitizeUploadID(r.FormValue("upload_id"))
	chunkIndexStr := r.FormValue("chunk_index")

	meta, sessionDir, err := readChunkedMeta(uploadID)
	if err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	chunkIndex, err := strconv.Atoi(chunkIndexStr)
	if err != nil || chunkIndex < 0 || chunkIndex >= meta.TotalChunks {
		jsonError(w, http.StatusBadRequest, fmt.Sprintf("invalid chunk_index: must be 0-%d", meta.TotalChunks-1))
		return
	}

	file, _, err := r.FormFile("chunk")
	if err != nil {
		jsonError(w, http.StatusBadRequest, "no chunk in request")
		return
	}
	defer file.Close()

	chunkPath := filepath.Join(sessionDir, strconv.Itoa(chunkIndex))
	tmpPath := chunkPath + ".tmp"
	dst, err := os.Create(tmpPath)
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "create chunk file failed: "+err.Error())
		return
	}

	written, err := io.Copy(dst, file)
	if err != nil {
		dst.Close()
		os.Remove(tmpPath)
		jsonError(w, http.StatusInternalServerError, "write chunk failed: "+err.Error())
		return
	}
	dst.Close()

	// Atomic rename to prevent partial reads during concurrent access.
	if err := os.Rename(tmpPath, chunkPath); err != nil {
		os.Remove(tmpPath)
		jsonError(w, http.StatusInternalServerError, "finalize chunk failed: "+err.Error())
		return
	}

	log.Printf("[upload/chunk] session=%s chunk=%d/%d size=%d", uploadID, chunkIndex, meta.TotalChunks, written)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"chunk_index":  chunkIndex,
		"received":     written,
		"total_chunks": meta.TotalChunks,
	})
}

func (s *Server) handleUploadComplete(w http.ResponseWriter, r *http.Request) {
	assemblyStart := time.Now()

	var req struct {
		UploadID string `json:"upload_id"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	log.Printf("[upload/complete] assembling session=%s", req.UploadID)

	meta, sessionDir, err := readChunkedMeta(req.UploadID)
	if err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	// Verify all chunks are present.
	received := receivedChunks(sessionDir, meta.TotalChunks)
	if len(received) != meta.TotalChunks {
		missing := []int{}
		receivedSet := map[int]bool{}
		for _, c := range received {
			receivedSet[c] = true
		}
		for i := 0; i < meta.TotalChunks; i++ {
			if !receivedSet[i] {
				missing = append(missing, i)
			}
		}
		jsonError(w, http.StatusBadRequest, fmt.Sprintf("missing %d chunks: %v", len(missing), missing))
		return
	}

	// Ensure upload directory exists.
	if err := os.MkdirAll(uploadDir, 0755); err != nil {
		jsonError(w, http.StatusInternalServerError, "cannot create upload dir: "+err.Error())
		return
	}

	// Determine final filename (dedup like handleUpload).
	name := meta.Filename
	ext := strings.ToLower(filepath.Ext(name))
	uploadMu.Lock()
	destPath := filepath.Join(uploadDir, name)
	if _, err := os.Stat(destPath); err == nil {
		base := strings.TrimSuffix(name, ext)
		stamp := time.Now().Format("20060102-150405")
		name = base + "_" + stamp + ext
		destPath = filepath.Join(uploadDir, name)
	}
	dst, err := os.Create(destPath)
	uploadMu.Unlock()
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "create file failed: "+err.Error())
		return
	}

	// Concatenate all chunks sequentially.
	var totalWritten int64
	for i := 0; i < meta.TotalChunks; i++ {
		chunkPath := filepath.Join(sessionDir, strconv.Itoa(i))
		chunk, err := os.Open(chunkPath)
		if err != nil {
			dst.Close()
			os.Remove(destPath)
			jsonError(w, http.StatusInternalServerError, fmt.Sprintf("open chunk %d failed: %v", i, err))
			return
		}
		n, err := io.Copy(dst, chunk)
		chunk.Close()
		if err != nil {
			dst.Close()
			os.Remove(destPath)
			jsonError(w, http.StatusInternalServerError, fmt.Sprintf("write chunk %d failed: %v", i, err))
			return
		}
		totalWritten += n
	}

	if err := dst.Sync(); err != nil {
		dst.Close()
		os.Remove(destPath)
		jsonError(w, http.StatusInternalServerError, "sync failed: "+err.Error())
		return
	}
	dst.Close()

	// Clean up session directory.
	os.RemoveAll(sessionDir)

	assemblyElapsed := time.Since(assemblyStart)
	format := strings.TrimPrefix(ext, ".")
	log.Printf("[upload/complete] session=%s saved %s (%d bytes, format=%s, chunks=%d, assembly_time=%s)", req.UploadID, destPath, totalWritten, format, meta.TotalChunks, assemblyElapsed.Round(time.Millisecond))

	s.metrics.UploadsTotal.Add(1)
	s.metrics.UploadBytesTotal.Add(totalWritten)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"path":   destPath,
		"name":   name,
		"size":   totalWritten,
		"format": format,
	})
}

func (s *Server) handleUploadStatus(w http.ResponseWriter, r *http.Request) {
	uploadID := sanitizeUploadID(chi.URLParam(r, "uploadId"))

	meta, sessionDir, err := readChunkedMeta(uploadID)
	if err != nil {
		jsonError(w, http.StatusNotFound, err.Error())
		return
	}

	received := receivedChunks(sessionDir, meta.TotalChunks)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"upload_id":       meta.UploadID,
		"filename":        meta.Filename,
		"total_chunks":    meta.TotalChunks,
		"received_chunks": received,
		"complete":        len(received) == meta.TotalChunks,
	})
}

// --- File download ---

// allowedDownloadDirs lists directories from which files may be downloaded.
var allowedDownloadDirs = []string{
	"/var/lib/libvirt/images/",
	"/var/lib/hyper2kvm/",
	"/data/demo/",
}

func (s *Server) handleDownload(w http.ResponseWriter, r *http.Request) {
	filePath := r.URL.Query().Get("path")
	if filePath == "" {
		jsonError(w, http.StatusBadRequest, "path parameter required")
		return
	}

	// Must be absolute.
	if !filepath.IsAbs(filePath) {
		jsonError(w, http.StatusBadRequest, "path must be absolute")
		return
	}

	// Must not contain path traversal.
	if strings.Contains(filePath, "..") {
		jsonError(w, http.StatusBadRequest, "path must not contain '..'")
		return
	}

	// Clean the path.
	filePath = filepath.Clean(filePath)

	// Must be under an allowed directory.
	allowed := false
	for _, dir := range allowedDownloadDirs {
		if strings.HasPrefix(filePath, dir) {
			allowed = true
			break
		}
	}
	if !allowed {
		jsonError(w, http.StatusForbidden, "path is not in an allowed directory")
		return
	}

	// Validate extension.
	ext := strings.ToLower(filepath.Ext(filePath))
	if !allowedUploadExts[ext] {
		jsonError(w, http.StatusBadRequest, "file type not allowed for download: "+ext)
		return
	}

	// Must be a regular file (not dir, symlink, etc.).
	info, err := os.Lstat(filePath)
	if err != nil {
		jsonError(w, http.StatusNotFound, "file not found")
		return
	}
	if !info.Mode().IsRegular() {
		jsonError(w, http.StatusBadRequest, "path is not a regular file")
		return
	}

	log.Printf("[download] serving %s (%d bytes) to %s", filePath, info.Size(), r.RemoteAddr)

	w.Header().Set("Content-Disposition", fmt.Sprintf("attachment; filename=%q", filepath.Base(filePath)))
	http.ServeFile(w, r, filePath)
}

// --- Browse server filesystem ---

func (s *Server) handleBrowse(w http.ResponseWriter, r *http.Request) {
	dir := r.URL.Query().Get("path")
	if dir == "" {
		dir = "/"
	}

	// Clean and validate path.
	dir = filepath.Clean(dir)
	info, err := os.Stat(dir)
	if err != nil {
		jsonError(w, http.StatusBadRequest, fmt.Sprintf("path not found: %s", dir))
		return
	}
	if !info.IsDir() {
		// If it's a file, return its parent directory.
		dir = filepath.Dir(dir)
	}

	entries, err := os.ReadDir(dir)
	if err != nil {
		jsonError(w, http.StatusForbidden, fmt.Sprintf("cannot read: %s", dir))
		return
	}

	type FileEntry struct {
		Name  string `json:"name"`
		Path  string `json:"path"`
		IsDir bool   `json:"is_dir"`
		IsVM  bool   `json:"is_vm"`
		Size  int64  `json:"size"`
	}

	// VM-related extensions get a special marker.
	vmExts := map[string]bool{
		".vmdk": true, ".ova": true, ".ovf": true,
		".vhd": true, ".vhdx": true, ".qcow2": true,
		".raw": true, ".img": true, ".iso": true,
		".yaml": true, ".yml": true, ".json": true,
	}

	// Show all files by default; filter=vm shows only VM files.
	filterVM := r.URL.Query().Get("filter") == "vm"

	files := make([]FileEntry, 0)
	for _, e := range entries {
		name := e.Name()
		if strings.HasPrefix(name, ".") {
			continue // skip hidden files
		}
		entry := FileEntry{
			Name:  name,
			Path:  filepath.Join(dir, name),
			IsDir: e.IsDir(),
		}
		if !e.IsDir() {
			ext := strings.ToLower(filepath.Ext(name))
			entry.IsVM = vmExts[ext]
			if filterVM && !entry.IsVM {
				continue
			}
			if fi, err := e.Info(); err == nil {
				entry.Size = fi.Size()
			}
		}
		files = append(files, entry)
	}

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"path":    dir,
		"parent":  filepath.Dir(dir),
		"entries": files,
	})
}

// --- Static files ---

func (s *Server) handleStatic(w http.ResponseWriter, r *http.Request) {
	if s.staticDir == "" {
		jsonError(w, http.StatusNotFound, "dashboard not built (run: cd dashboard && npm run build)")
		return
	}

	// Try to serve the requested file (JS, CSS, etc.).
	reqPath := strings.TrimPrefix(r.URL.Path, "/")
	if reqPath == "" {
		reqPath = "index.html"
	}
	filePath := filepath.Join(s.staticDir, filepath.Clean(reqPath))

	// If the file exists, serve it directly.
	if _, err := os.Stat(filePath); err == nil {
		http.ServeFile(w, r, filePath)
		return
	}

	// For SPA: serve index.html for any unknown path (client-side routing).
	http.ServeFile(w, r, filepath.Join(s.staticDir, "index.html"))
}

// --- Cluster Capacity ---

func (s *Server) handleCapacity(w http.ResponseWriter, r *http.Request) {
	log.Printf("[capacity] capacity requested from %s", r.RemoteAddr)

	type hostInfo struct {
		CPUs           int     `json:"cpus"`
		MemoryTotalGB  float64 `json:"memory_total_gb"`
		MemoryUsedGB   float64 `json:"memory_used_gb"`
		StorageTotalGB float64 `json:"storage_total_gb"`
		StorageUsedGB  float64 `json:"storage_used_gb"`
	}
	type vmsInfo struct {
		Total             int     `json:"total"`
		Running           int     `json:"running"`
		VCPUsAllocated    int     `json:"vcpus_allocated"`
		MemoryAllocatedGB float64 `json:"memory_allocated_gb"`
	}
	type utilInfo struct {
		CPUPercent     float64 `json:"cpu_percent"`
		MemoryPercent  float64 `json:"memory_percent"`
		StoragePercent float64 `json:"storage_percent"`
	}

	host := hostInfo{}
	vms := vmsInfo{}

	// Get CPU count from nproc.
	nprocCtx, nprocCancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer nprocCancel()
	if out, err := exec.CommandContext(nprocCtx, "nproc").Output(); err == nil {
		var cpuErr error
		host.CPUs, cpuErr = strconv.Atoi(strings.TrimSpace(string(out)))
		if cpuErr != nil {
			log.Printf("[warn] failed to parse nproc output: %v", cpuErr)
		}
	}

	// Get memory from free -b.
	freeCtx, freeCancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer freeCancel()
	if out, err := exec.CommandContext(freeCtx, "free", "-b").Output(); err == nil {
		for _, line := range strings.Split(string(out), "\n") {
			if strings.HasPrefix(line, "Mem:") {
				fields := strings.Fields(line)
				if len(fields) >= 4 {
					total, err := strconv.ParseFloat(fields[1], 64)
					if err != nil {
						log.Printf("[warn] failed to parse memory total %s: %v", fields[1], err)
					}
					used, err := strconv.ParseFloat(fields[2], 64)
					if err != nil {
						log.Printf("[warn] failed to parse memory used %s: %v", fields[2], err)
					}
					host.MemoryTotalGB = math.Round(total/1073741824*10) / 10
					host.MemoryUsedGB = math.Round(used/1073741824*10) / 10
				}
			}
		}
	}

	// Get storage from df -B1 /var/lib/libvirt.
	dfCtx, dfCancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer dfCancel()
	if out, err := exec.CommandContext(dfCtx, "df", "-B1", "/var/lib/libvirt").Output(); err == nil {
		lines := strings.Split(string(out), "\n")
		// df output may wrap across two lines; find a line with enough numeric fields.
		for _, line := range lines[1:] {
			fields := strings.Fields(line)
			if len(fields) >= 4 {
				total, err := strconv.ParseFloat(fields[1], 64)
				if err != nil {
					log.Printf("[warn] failed to parse storage total %s: %v", fields[1], err)
				}
				used, err := strconv.ParseFloat(fields[2], 64)
				if err != nil {
					log.Printf("[warn] failed to parse storage used %s: %v", fields[2], err)
				}
				if total > 0 {
					host.StorageTotalGB = math.Round(total/1073741824*10) / 10
					host.StorageUsedGB = math.Round(used/1073741824*10) / 10
					break
				}
			}
		}
	}

	// List all VMs and count running/total.
	listCtx, listCancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer listCancel()
	if out, err := exec.CommandContext(listCtx, "virsh", "list", "--all").Output(); err == nil {
		var runningNames []string
		for _, line := range strings.Split(string(out), "\n")[2:] {
			fields := strings.Fields(line)
			if len(fields) < 2 {
				continue
			}
			vms.Total++
			// A running VM has a numeric ID in column 0.
			if fields[0] != "-" {
				if _, err := strconv.Atoi(fields[0]); err == nil {
					vms.Running++
					runningNames = append(runningNames, fields[1])
				}
			}
		}

		// For each running VM, sum vCPUs and memory.
		for _, vmName := range runningNames {
			infoCtx, infoCancel := context.WithTimeout(r.Context(), 5*time.Second)
			infoOut, err := exec.CommandContext(infoCtx, "virsh", "dominfo", vmName).Output()
			infoCancel()
			if err != nil {
				continue
			}
			for _, line := range strings.Split(string(infoOut), "\n") {
				if strings.HasPrefix(line, "CPU(s):") {
					v, err := strconv.Atoi(strings.TrimSpace(strings.TrimPrefix(line, "CPU(s):")))
					if err != nil {
						log.Printf("[warn] failed to parse vcpus: %v", err)
					}
					vms.VCPUsAllocated += v
				}
				if strings.HasPrefix(line, "Max memory:") {
					memStr := strings.TrimSpace(strings.TrimPrefix(line, "Max memory:"))
					memFields := strings.Fields(memStr)
					if len(memFields) >= 1 {
						val, err := strconv.ParseFloat(memFields[0], 64)
						if err != nil {
							log.Printf("[warn] failed to parse memory %s: %v", memFields[0], err)
						}
						// virsh dominfo reports memory in KiB.
						vms.MemoryAllocatedGB += val / 1048576.0
					}
				}
			}
		}
		vms.MemoryAllocatedGB = math.Round(vms.MemoryAllocatedGB*10) / 10
	}

	// Compute utilization percentages.
	util := utilInfo{}
	if host.CPUs > 0 {
		util.CPUPercent = math.Round(float64(vms.VCPUsAllocated)/float64(host.CPUs)*1000) / 10
		if util.CPUPercent > 100 {
			util.CPUPercent = 100
		}
	}
	if host.MemoryTotalGB > 0 {
		util.MemoryPercent = math.Round(host.MemoryUsedGB/host.MemoryTotalGB*1000) / 10
	}
	if host.StorageTotalGB > 0 {
		util.StoragePercent = math.Round(host.StorageUsedGB/host.StorageTotalGB*1000) / 10
	}

	log.Printf("[capacity] cpus=%d mem=%.1f/%.1fGB vms=%d/%d vcpus=%d",
		host.CPUs, host.MemoryUsedGB, host.MemoryTotalGB, vms.Running, vms.Total, vms.VCPUsAllocated)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"host":        host,
		"vms":         vms,
		"utilization": util,
	})
}

// --- Helpers ---

func readJSON(r *http.Request, v interface{}) error {
	body, err := io.ReadAll(io.LimitReader(r.Body, 10*1024*1024))
	if err != nil {
		return fmt.Errorf("read body: %w", err)
	}
	return json.Unmarshal(body, v)
}

func jsonResponse(w http.ResponseWriter, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data)
}

func jsonError(w http.ResponseWriter, status int, message string) {
	jsonResponse(w, status, map[string]string{"error": message})
}
