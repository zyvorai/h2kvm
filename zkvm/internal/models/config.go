// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package models

// TUIConfig holds the TUI configuration settings.
type TUIConfig struct {
	General      GeneralConfig      `json:"general"`
	Migration    MigrationConfig    `json:"migration"`
	VSphere      VSphereConfig      `json:"vsphere"`
	OfflineFixes OfflineFixesConfig `json:"offline_fixes"`
	Performance  PerformanceConfig  `json:"performance"`
	Advanced     AdvancedConfig     `json:"advanced"`
}

// GeneralConfig holds general settings.
type GeneralConfig struct {
	OutputDir   string `json:"default_output_dir"`
	LogLevel    string `json:"log_level"`
	LogToFile   bool   `json:"log_to_file"`
	LogFilePath string `json:"log_file_path"`
}

// MigrationConfig holds migration-specific settings.
type MigrationConfig struct {
	DefaultFormat      string `json:"default_format"`
	EnableCompression  bool   `json:"enable_compression"`
	ParallelMigrations int    `json:"parallel_migrations"`
	SkipExisting       bool   `json:"skip_existing"`
}

// VSphereConfig holds vSphere connection settings.
type VSphereConfig struct {
	VCenterHost       string `json:"vcenter_host"`
	Username          string `json:"vcenter_username"`
	Password          string `json:"-"` // Never serialize plaintext password to disk; use PasswordEnv instead
	PasswordEnv       string `json:"vcenter_password_env"`
	Datacenter        string `json:"vcenter_datacenter"`
	SaveCredentials   bool   `json:"vcenter_save_credentials"`
	VerifySSL         bool   `json:"vcenter_verify_ssl"`
	Insecure          bool   `json:"vcenter_insecure"`
}

// OfflineFixesConfig holds offline fix settings.
type OfflineFixesConfig struct {
	FstabMode      string `json:"fstab_mode"`
	RegenInitramfs bool   `json:"regen_initramfs"`
	UpdateGrub     bool   `json:"update_grub"`
	FixNetwork     bool   `json:"fix_network"`
	EnhancedChroot bool   `json:"enhanced_chroot"`
}

// PerformanceConfig holds performance settings.
type PerformanceConfig struct {
	MaxConcurrentOps int `json:"max_concurrent_operations"`
	OperationTimeout int `json:"operation_timeout"`
	NetworkTimeout   int `json:"network_timeout"`
}

// AdvancedConfig holds advanced settings.
type AdvancedConfig struct {
	GuestfsBackend string `json:"guestfs_backend"`
	DebugMode      bool   `json:"debug_mode"`
	VerboseOutput  bool   `json:"verbose_output"`
}

// DefaultConfig returns the default TUI configuration.
func DefaultConfig() TUIConfig {
	return TUIConfig{
		General: GeneralConfig{
			OutputDir:   "/tmp/h2kvm-output",
			LogLevel:    "info",
			LogToFile:   true,
			LogFilePath: "/tmp/h2kvm.log",
		},
		Migration: MigrationConfig{
			DefaultFormat:      "qcow2",
			EnableCompression:  true,
			ParallelMigrations: 2,
			SkipExisting:       false,
		},
		VSphere: VSphereConfig{
			VerifySSL: true,
		},
		OfflineFixes: OfflineFixesConfig{
			FstabMode:      "stabilize-all",
			RegenInitramfs: true,
			UpdateGrub:     true,
			FixNetwork:     true,
			EnhancedChroot: true,
		},
		Performance: PerformanceConfig{
			MaxConcurrentOps: 4,
			OperationTimeout: 3600,
			NetworkTimeout:   300,
		},
		Advanced: AdvancedConfig{
			GuestfsBackend: "vmcraft",
		},
	}
}
