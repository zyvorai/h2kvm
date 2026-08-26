// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package vsphere

import (
	"context"
	"fmt"
	"net/url"
	"strings"

	"github.com/vmware/govmomi"
	"github.com/vmware/govmomi/find"
	"github.com/vmware/govmomi/object"
	"github.com/vmware/govmomi/property"
	"github.com/vmware/govmomi/vim25/mo"
	"github.com/vmware/govmomi/vim25/types"

	"github.com/h2kvm/web/internal/domain"
)

// Provider implements ports.ComputeProvider for VMware vSphere.
type Provider struct {
	name       string
	client     *govmomi.Client
	datacenter string
}

// New creates a new vSphere provider.
func New() *Provider {
	return &Provider{}
}

func (p *Provider) Name() string              { return p.name }
func (p *Provider) Type() domain.ProviderType { return domain.ProviderVSphere }

// Connect establishes a connection to vCenter.
func (p *Provider) Connect(ctx context.Context, config domain.ProviderConfig) error {
	p.name = config.Name

	endpoint := config.Endpoint
	if !strings.Contains(endpoint, "://") {
		endpoint = "https://" + endpoint
	}
	if !strings.HasSuffix(endpoint, "/sdk") {
		endpoint = strings.TrimRight(endpoint, "/") + "/sdk"
	}

	u, err := url.Parse(endpoint)
	if err != nil {
		return fmt.Errorf("parse vCenter URL: %w", err)
	}
	u.User = url.UserPassword(config.Username, config.Password)

	client, err := govmomi.NewClient(ctx, u, config.Insecure)
	if err != nil {
		return fmt.Errorf("connect to vCenter: %w", err)
	}

	p.client = client
	p.datacenter = config.Metadata["datacenter"]
	return nil
}

// Disconnect closes the vCenter connection.
func (p *Provider) Disconnect(ctx context.Context) error {
	if p.client != nil {
		return p.client.Logout(ctx)
	}
	return nil
}

// ValidateCredentials tests the vCenter connection.
func (p *Provider) ValidateCredentials(ctx context.Context) error {
	if p.client == nil {
		return fmt.Errorf("not connected")
	}
	if !p.client.IsVC() {
		return fmt.Errorf("connected endpoint is not a vCenter")
	}
	return nil
}

// ListVMs returns VMs from the connected vCenter.
func (p *Provider) ListVMs(ctx context.Context, filter domain.VMFilter) ([]*domain.VMInfo, error) {
	if p.client == nil {
		return nil, fmt.Errorf("not connected")
	}

	finder := find.NewFinder(p.client.Client, true)

	// Set datacenter.
	if p.datacenter != "" {
		dc, err := finder.Datacenter(ctx, p.datacenter)
		if err != nil {
			return nil, fmt.Errorf("find datacenter %q: %w", p.datacenter, err)
		}
		finder.SetDatacenter(dc)
	}

	// Find VMs.
	pattern := "*"
	if filter.NamePattern != "" {
		pattern = filter.NamePattern
	}

	vms, err := finder.VirtualMachineList(ctx, pattern)
	if err != nil {
		return nil, fmt.Errorf("list VMs: %w", err)
	}

	// Collect managed object references.
	refs := make([]types.ManagedObjectReference, len(vms))
	for i, vm := range vms {
		refs[i] = vm.Reference()
	}

	// Fetch properties.
	pc := property.DefaultCollector(p.client.Client)
	var moVMs []mo.VirtualMachine
	props := []string{"name", "summary", "config", "guest", "runtime"}
	if err := pc.Retrieve(ctx, refs, props, &moVMs); err != nil {
		return nil, fmt.Errorf("retrieve VM properties: %w", err)
	}

	var result []*domain.VMInfo
	for _, moVM := range moVMs {
		vm := convertVM(moVM)
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

// GetVM returns details for a single VM by path or name.
func (p *Provider) GetVM(ctx context.Context, identifier string) (*domain.VMInfo, error) {
	if p.client == nil {
		return nil, fmt.Errorf("not connected")
	}

	finder := find.NewFinder(p.client.Client, true)
	if p.datacenter != "" {
		dc, err := finder.Datacenter(ctx, p.datacenter)
		if err != nil {
			return nil, fmt.Errorf("find datacenter: %w", err)
		}
		finder.SetDatacenter(dc)
	}

	vm, err := finder.VirtualMachine(ctx, identifier)
	if err != nil {
		return nil, fmt.Errorf("find VM %q: %w", identifier, err)
	}

	var moVM mo.VirtualMachine
	pc := property.DefaultCollector(p.client.Client)
	if err := pc.RetrieveOne(ctx, vm.Reference(), []string{"name", "summary", "config", "guest", "runtime"}, &moVM); err != nil {
		return nil, fmt.Errorf("retrieve VM properties: %w", err)
	}

	return convertVM(moVM), nil
}

// convertVM converts a govmomi VirtualMachine to our domain VMInfo.
func convertVM(moVM mo.VirtualMachine) *domain.VMInfo {
	vm := &domain.VMInfo{
		Provider: domain.ProviderVSphere,
		Name:     moVM.Name,
	}

	if moVM.Summary.Config.InstanceUuid != "" {
		vm.ID = moVM.Summary.Config.InstanceUuid
	} else {
		vm.ID = moVM.Reference().Value
	}

	if moVM.Summary.Runtime.PowerState != "" {
		vm.State = string(moVM.Summary.Runtime.PowerState)
	}

	vm.GuestOS = moVM.Summary.Config.GuestFullName
	vm.MemoryMB = int64(moVM.Summary.Config.MemorySizeMB)
	vm.NumCPUs = int(moVM.Summary.Config.NumCpu)

	if moVM.Summary.Storage != nil {
		vm.StorageGB = int64(moVM.Summary.Storage.Committed+moVM.Summary.Storage.Uncommitted) / (1024 * 1024 * 1024)
	}

	if moVM.Guest != nil {
		for _, nic := range moVM.Guest.Net {
			vm.IPAddresses = append(vm.IPAddresses, nic.IpAddress...)
		}
	}

	// Extract disks from config.
	if moVM.Config != nil {
		vm.Location = moVM.Config.Files.VmPathName
		for _, dev := range moVM.Config.Hardware.Device {
			if disk, ok := dev.(*types.VirtualDisk); ok {
				di := domain.DiskInfo{
					SizeGB: disk.CapacityInKB / (1024 * 1024),
				}
				if disk.DeviceInfo != nil {
					di.Name = disk.DeviceInfo.GetDescription().Label
				}
				if backing, ok := disk.Backing.(*types.VirtualDiskFlatVer2BackingInfo); ok {
					di.Path = backing.FileName
				}
				vm.Disks = append(vm.Disks, di)
			}
		}
	}

	return vm
}

// Datacenter returns the vSphere datacenter for this connection.
func (p *Provider) Datacenter() string {
	return p.datacenter
}

// Finder returns a govmomi finder for advanced operations.
func (p *Provider) Finder(ctx context.Context) (*find.Finder, error) {
	if p.client == nil {
		return nil, fmt.Errorf("not connected")
	}
	f := find.NewFinder(p.client.Client, true)
	if p.datacenter != "" {
		dc, err := f.Datacenter(ctx, p.datacenter)
		if err != nil {
			return nil, err
		}
		f.SetDatacenter(dc)
	}
	return f, nil
}

// ListDatacenters returns available datacenters.
func (p *Provider) ListDatacenters(ctx context.Context) ([]*object.Datacenter, error) {
	if p.client == nil {
		return nil, fmt.Errorf("not connected")
	}
	f := find.NewFinder(p.client.Client, true)
	return f.DatacenterList(ctx, "*")
}
