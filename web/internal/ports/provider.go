// Copyright (c) 2026 ZyvorAI Labs Private Limited.
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
// https://zyvor.dev · info@zyvor.dev


package ports

import (
	"context"

	"github.com/h2kvm/web/internal/domain"
)

// ComputeProvider abstracts VM discovery for a cloud/hypervisor provider.
// The web backend uses this for browsing VMs; actual migration is delegated
// to h2kvmctl via the Runner interface.
type ComputeProvider interface {
	// Name returns the user-assigned connection name.
	Name() string
	// Type returns the provider type (vsphere, azure, ec2).
	Type() domain.ProviderType
	// Connect establishes a connection to the provider.
	Connect(ctx context.Context, config domain.ProviderConfig) error
	// Disconnect closes the provider connection.
	Disconnect(ctx context.Context) error
	// ValidateCredentials tests that the stored credentials are valid.
	ValidateCredentials(ctx context.Context) error
	// ListVMs returns VMs matching the given filter.
	ListVMs(ctx context.Context, filter domain.VMFilter) ([]*domain.VMInfo, error)
	// GetVM returns details for a single VM by identifier.
	GetVM(ctx context.Context, identifier string) (*domain.VMInfo, error)
}
