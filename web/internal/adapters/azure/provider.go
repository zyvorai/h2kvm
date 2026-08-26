// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package azure

import (
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"

	"github.com/h2kvm/web/internal/domain"
)

// Provider implements ports.ComputeProvider for Microsoft Azure.
// Uses `az` CLI for simplicity — avoids pulling in the full Azure SDK.
type Provider struct {
	name           string
	subscriptionID string
	resourceGroup  string
	connected      bool
}

// New creates a new Azure provider.
func New() *Provider {
	return &Provider{}
}

func (p *Provider) Name() string              { return p.name }
func (p *Provider) Type() domain.ProviderType { return domain.ProviderAzure }

// Connect validates Azure CLI credentials and sets scope.
func (p *Provider) Connect(ctx context.Context, config domain.ProviderConfig) error {
	p.name = config.Name
	p.subscriptionID = config.Metadata["subscription_id"]
	p.resourceGroup = config.Metadata["resource_group"]

	if p.subscriptionID == "" {
		return fmt.Errorf("subscription_id is required")
	}
	if p.resourceGroup == "" {
		return fmt.Errorf("resource_group is required")
	}

	// Verify az CLI is available and logged in.
	if err := p.ValidateCredentials(ctx); err != nil {
		return err
	}

	p.connected = true
	return nil
}

func (p *Provider) Disconnect(_ context.Context) error {
	p.connected = false
	return nil
}

// ValidateCredentials verifies the az CLI is authenticated.
func (p *Provider) ValidateCredentials(ctx context.Context) error {
	cmd := exec.CommandContext(ctx, "az", "account", "show", "--subscription", p.subscriptionID, "-o", "json")
	out, err := cmd.Output()
	if err != nil {
		return fmt.Errorf("az CLI not authenticated or subscription not found: %w (run 'az login')", err)
	}
	var acct map[string]interface{}
	if err := json.Unmarshal(out, &acct); err != nil {
		return fmt.Errorf("parse az account: %w", err)
	}
	return nil
}

// ListVMs returns VMs in the configured resource group.
func (p *Provider) ListVMs(ctx context.Context, filter domain.VMFilter) ([]*domain.VMInfo, error) {
	if !p.connected {
		return nil, fmt.Errorf("not connected")
	}

	args := []string{"vm", "list",
		"--subscription", p.subscriptionID,
		"--resource-group", p.resourceGroup,
		"-d", "-o", "json",
	}
	cmd := exec.CommandContext(ctx, "az", args...)
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("az vm list: %w", err)
	}

	var azVMs []azureVM
	if err := json.Unmarshal(out, &azVMs); err != nil {
		return nil, fmt.Errorf("parse VM list: %w", err)
	}

	var result []*domain.VMInfo
	for _, azVM := range azVMs {
		if filter.NamePattern != "" && !strings.Contains(strings.ToLower(azVM.Name), strings.ToLower(filter.NamePattern)) {
			continue
		}

		vm := &domain.VMInfo{
			Provider: domain.ProviderAzure,
			ID:       azVM.VMID,
			Name:     azVM.Name,
			State:    azVM.PowerState,
			Location: azVM.Location,
			GuestOS:  azVM.StorageProfile.OSDisk.OSType,
		}

		if azVM.HardwareProfile.VMSize != "" {
			vm.Tags = map[string]string{"vm_size": azVM.HardwareProfile.VMSize}
		}

		// Map IPs.
		for _, iface := range azVM.NetworkProfile.NetworkInterfaces {
			for _, ipConfig := range iface.IPConfigurations {
				if ipConfig.PrivateIPAddress != "" {
					vm.IPAddresses = append(vm.IPAddresses, ipConfig.PrivateIPAddress)
				}
			}
		}

		// Map disks.
		osDisk := azVM.StorageProfile.OSDisk
		vm.Disks = append(vm.Disks, domain.DiskInfo{
			ID:     osDisk.ManagedDisk.ID,
			Name:   osDisk.Name,
			SizeGB: osDisk.DiskSizeGB,
			IsRoot: true,
		})
		for _, dd := range azVM.StorageProfile.DataDisks {
			vm.Disks = append(vm.Disks, domain.DiskInfo{
				ID:     dd.ManagedDisk.ID,
				Name:   dd.Name,
				SizeGB: dd.DiskSizeGB,
			})
		}

		if filter.State != "" && vm.State != filter.State {
			continue
		}

		result = append(result, vm)
		if filter.Limit > 0 && len(result) >= filter.Limit {
			break
		}
	}

	return result, nil
}

// GetVM returns details for a single Azure VM.
func (p *Provider) GetVM(ctx context.Context, identifier string) (*domain.VMInfo, error) {
	if !p.connected {
		return nil, fmt.Errorf("not connected")
	}

	args := []string{"vm", "show",
		"--subscription", p.subscriptionID,
		"--resource-group", p.resourceGroup,
		"--name", identifier,
		"-d", "-o", "json",
	}
	cmd := exec.CommandContext(ctx, "az", args...)
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("az vm show %q: %w", identifier, err)
	}

	var azVM azureVM
	if err := json.Unmarshal(out, &azVM); err != nil {
		return nil, fmt.Errorf("parse VM: %w", err)
	}

	vm := &domain.VMInfo{
		Provider: domain.ProviderAzure,
		ID:       azVM.VMID,
		Name:     azVM.Name,
		State:    azVM.PowerState,
		Location: azVM.Location,
		GuestOS:  azVM.StorageProfile.OSDisk.OSType,
	}

	return vm, nil
}

// Azure CLI JSON structures.
type azureVM struct {
	VMID           string `json:"vmId"`
	Name           string `json:"name"`
	Location       string `json:"location"`
	PowerState     string `json:"powerState"`
	HardwareProfile struct {
		VMSize string `json:"vmSize"`
	} `json:"hardwareProfile"`
	StorageProfile struct {
		OSDisk struct {
			Name        string `json:"name"`
			OSType      string `json:"osType"`
			DiskSizeGB  int64  `json:"diskSizeGb"`
			ManagedDisk struct {
				ID string `json:"id"`
			} `json:"managedDisk"`
		} `json:"osDisk"`
		DataDisks []struct {
			Name        string `json:"name"`
			DiskSizeGB  int64  `json:"diskSizeGb"`
			ManagedDisk struct {
				ID string `json:"id"`
			} `json:"managedDisk"`
		} `json:"dataDisks"`
	} `json:"storageProfile"`
	NetworkProfile struct {
		NetworkInterfaces []struct {
			IPConfigurations []struct {
				PrivateIPAddress string `json:"privateIpAddress"`
			} `json:"ipConfigurations"`
		} `json:"networkInterfaces"`
	} `json:"networkProfile"`
}
