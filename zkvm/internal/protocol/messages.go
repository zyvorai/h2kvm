// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package protocol

import "encoding/json"

// Request represents a client-to-server JSON message.
type Request struct {
	Type   string          `json:"type"`
	ID     string          `json:"id,omitempty"`
	Source string          `json:"source,omitempty"`
	Path   string          `json:"path,omitempty"`
	Params json.RawMessage `json:"params,omitempty"`

	// Subscribe-specific
	Topics []string `json:"topics,omitempty"`

	// Migration control
	MigrationID string          `json:"migration_id,omitempty"`
	Config      json.RawMessage `json:"config,omitempty"`
	Settings    json.RawMessage `json:"settings,omitempty"`
}

// Response represents a server-to-client response.
type Response struct {
	Type    string          `json:"type"`
	Success bool            `json:"success"`
	Data    json.RawMessage `json:"data,omitempty"`
	Error   string          `json:"error,omitempty"`
}

// Event represents a server-pushed event.
type Event struct {
	Type string          `json:"type"`
	Data json.RawMessage `json:"data,omitempty"`
}

// Envelope is the raw JSON message received on the socket.
// We first decode into this to determine the message category.
type Envelope struct {
	Type    string          `json:"type"`
	Success *bool           `json:"success,omitempty"`
	Data    json.RawMessage `json:"data,omitempty"`
	Error   string          `json:"error,omitempty"`
}

// IsResponse returns true if the envelope looks like a response (has success field).
func (e *Envelope) IsResponse() bool {
	return e.Success != nil
}

// MigrationUpdateData is the payload of a migration_update event.
type MigrationUpdateData struct {
	ID           string  `json:"id"`
	VMName       string  `json:"vm_name"`
	Status       string  `json:"status"`
	Progress     float64 `json:"progress"`
	CurrentStage string  `json:"current_stage,omitempty"`
	Throughput   float64 `json:"throughput_mbps,omitempty"`
	Elapsed      float64 `json:"elapsed_seconds,omitempty"`
	ETA          float64 `json:"eta_seconds,omitempty"`
	Error        string  `json:"error,omitempty"`
}

// LogData is the payload of a log event.
type LogData struct {
	Message   string `json:"message"`
	Level     string `json:"level"`
	Timestamp string `json:"timestamp"`
}

// MetricsData is the payload of a metrics event.
type MetricsData struct {
	Active           int     `json:"active"`
	Completed        int     `json:"completed"`
	Failed           int     `json:"failed"`
	TotalMigrations  int     `json:"total_migrations"`
	SuccessRate      float64 `json:"success_rate"`
	AvgDuration      float64 `json:"avg_duration_seconds"`
	CompletedToday   int     `json:"completed_today"`
}

// MigrationCompleteData is the payload of a migration_complete event.
type MigrationCompleteData struct {
	ID      string `json:"id"`
	VMName  string `json:"vm_name"`
	Success bool   `json:"success"`
	Error   string `json:"error,omitempty"`
}

// ErrorData is the payload of an error event.
type ErrorData struct {
	Message string `json:"message"`
	Code    string `json:"code,omitempty"`
}

// StartMigrationConfig is the config for starting a migration.
type StartMigrationConfig struct {
	VMName       string `json:"vm_name"`
	SourceType   string `json:"source_type"`
	SourcePath   string `json:"source_path,omitempty"`
	OutputDir    string `json:"output_dir,omitempty"`
	OutputFormat string `json:"output_format,omitempty"`
	Compress     bool   `json:"compress,omitempty"`

	// vSphere-specific
	VCenterHost string `json:"vcenter_host,omitempty"`
	VCenterUser string `json:"vcenter_user,omitempty"`
	VCenterPass string `json:"vcenter_pass,omitempty"`

	// Offline fixes
	FixFstab       bool `json:"fix_fstab,omitempty"`
	RegenInitramfs bool `json:"regen_initramfs,omitempty"`
	UpdateGrub     bool `json:"update_grub,omitempty"`
	FixNetwork     bool `json:"fix_network,omitempty"`
}

// VMInfo represents a VM entry from list_vms.
type VMInfo struct {
	Name       string `json:"name"`
	PowerState string `json:"power_state,omitempty"`
	GuestOS    string `json:"guest_os,omitempty"`
	NumCPUs    int    `json:"num_cpus,omitempty"`
	MemoryMB   int    `json:"memory_mb,omitempty"`
	DiskSizeMB int64  `json:"disk_size_mb,omitempty"`
}

// DiskInfo represents a local disk entry.
type DiskInfo struct {
	Path     string `json:"path"`
	Format   string `json:"format"`
	SizeMB   int64  `json:"size_mb"`
	Modified string `json:"modified,omitempty"`
}

// AIInfo represents AI module status.
type AIInfo struct {
	Enabled          bool    `json:"enabled"`
	KnowledgeEntries int     `json:"knowledge_entries"`
	PredictionReady  bool    `json:"prediction_ready"`
	SuccessRate      float64 `json:"success_rate,omitempty"`
}

// NewSubscribeRequest creates a subscribe request.
func NewSubscribeRequest(topics ...string) Request {
	return Request{Type: "subscribe", Topics: topics}
}

// NewListMigrationsRequest creates a list_migrations request.
func NewListMigrationsRequest() Request {
	return Request{Type: "list_migrations"}
}

// NewListVMsRequest creates a list_vms request.
func NewListVMsRequest(source string, params json.RawMessage) Request {
	return Request{Type: "list_vms", Source: source, Params: params}
}

// NewListLocalDisksRequest creates a list_local_disks request.
func NewListLocalDisksRequest(path string) Request {
	return Request{Type: "list_local_disks", Path: path}
}

// NewStartMigrationRequest creates a start_migration request.
func NewStartMigrationRequest(config StartMigrationConfig) Request {
	raw, _ := json.Marshal(config)
	return Request{Type: "start_migration", Config: raw}
}

// NewPauseMigrationRequest creates a pause_migration request.
func NewPauseMigrationRequest(id string) Request {
	return Request{Type: "pause_migration", MigrationID: id}
}

// NewResumeMigrationRequest creates a resume_migration request.
func NewResumeMigrationRequest(id string) Request {
	return Request{Type: "resume_migration", MigrationID: id}
}

// NewCancelMigrationRequest creates a cancel_migration request.
func NewCancelMigrationRequest(id string) Request {
	return Request{Type: "cancel_migration", MigrationID: id}
}

// NewGetStatsRequest creates a get_stats request.
func NewGetStatsRequest() Request {
	return Request{Type: "get_stats"}
}

// NewGetConfigRequest creates a get_config request.
func NewGetConfigRequest() Request {
	return Request{Type: "get_config"}
}

// NewSetConfigRequest creates a set_config request.
func NewSetConfigRequest(settings json.RawMessage) Request {
	return Request{Type: "set_config", Settings: settings}
}

// NewGetAIInfoRequest creates a get_ai_info request.
func NewGetAIInfoRequest() Request {
	return Request{Type: "get_ai_info"}
}
