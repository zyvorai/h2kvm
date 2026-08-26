// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package domain

import "time"

// ProviderType identifies a cloud/hypervisor provider.
type ProviderType string

const (
	ProviderVSphere ProviderType = "vsphere"
	ProviderAzure   ProviderType = "azure"
	ProviderEC2     ProviderType = "ec2"
)

// ProviderConfig holds connection details for a cloud provider.
type ProviderConfig struct {
	ID       string            `json:"id"`
	Type     ProviderType      `json:"type"`
	Name     string            `json:"name"`
	Endpoint string            `json:"endpoint"`
	Username string            `json:"username,omitempty"`
	Password string            `json:"password,omitempty"`
	Region   string            `json:"region,omitempty"`
	Insecure bool              `json:"insecure,omitempty"`
	Metadata map[string]string `json:"metadata,omitempty"`
}

// VMInfo represents a discovered virtual machine.
type VMInfo struct {
	Provider    ProviderType      `json:"provider"`
	ID          string            `json:"id"`
	Name        string            `json:"name"`
	State       string            `json:"state"`
	Location    string            `json:"location"`
	GuestOS     string            `json:"guest_os"`
	MemoryMB    int64             `json:"memory_mb"`
	NumCPUs     int               `json:"num_cpus"`
	StorageGB   int64             `json:"storage_gb"`
	IPAddresses []string          `json:"ip_addresses,omitempty"`
	Tags        map[string]string `json:"tags,omitempty"`
	Disks       []DiskInfo        `json:"disks,omitempty"`
	CreatedAt   time.Time         `json:"created_at,omitempty"`
}

// DiskInfo describes a virtual disk attached to a VM.
type DiskInfo struct {
	ID     string `json:"id"`
	Name   string `json:"name"`
	SizeGB int64  `json:"size_gb"`
	Path   string `json:"path"`
	IsRoot bool   `json:"is_root"`
}

// VMFilter constrains VM listing results.
type VMFilter struct {
	NamePattern string            `json:"name_pattern,omitempty"`
	State       string            `json:"state,omitempty"`
	Tags        map[string]string `json:"tags,omitempty"`
	Location    string            `json:"location,omitempty"`
	Limit       int               `json:"limit,omitempty"`
}

// ProviderStatus represents the connection state of a provider.
type ProviderStatus struct {
	ID        string       `json:"id"`
	Type      ProviderType `json:"type"`
	Name      string       `json:"name"`
	Connected bool         `json:"connected"`
	VMCount   int          `json:"vm_count,omitempty"`
	Error     string       `json:"error,omitempty"`
}
