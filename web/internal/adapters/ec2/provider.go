// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package ec2

import (
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"

	"github.com/h2kvm/web/internal/domain"
)

// Provider implements ports.ComputeProvider for AWS EC2.
// Uses the `aws` CLI for simplicity — avoids pulling in the full AWS SDK.
type Provider struct {
	name      string
	region    string
	profile   string
	connected bool
}

// New creates a new EC2 provider.
func New() *Provider {
	return &Provider{}
}

func (p *Provider) Name() string              { return p.name }
func (p *Provider) Type() domain.ProviderType { return domain.ProviderEC2 }

// Connect validates AWS CLI credentials.
func (p *Provider) Connect(ctx context.Context, config domain.ProviderConfig) error {
	p.name = config.Name
	p.region = config.Region
	p.profile = config.Metadata["profile"]

	if p.region == "" {
		p.region = "us-east-1"
	}

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

// ValidateCredentials verifies AWS CLI is configured.
func (p *Provider) ValidateCredentials(ctx context.Context) error {
	args := p.baseArgs("sts", "get-caller-identity")
	cmd := exec.CommandContext(ctx, "aws", args...)
	if _, err := cmd.Output(); err != nil {
		return fmt.Errorf("aws CLI not authenticated: %w (run 'aws configure')", err)
	}
	return nil
}

// ListVMs returns EC2 instances in the configured region.
func (p *Provider) ListVMs(ctx context.Context, filter domain.VMFilter) ([]*domain.VMInfo, error) {
	if !p.connected {
		return nil, fmt.Errorf("not connected")
	}

	args := p.baseArgs("ec2", "describe-instances", "--output", "json")

	// Add name filter if specified.
	if filter.NamePattern != "" {
		args = append(args, "--filters",
			fmt.Sprintf("Name=tag:Name,Values=*%s*", filter.NamePattern))
	}

	cmd := exec.CommandContext(ctx, "aws", args...)
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("aws ec2 describe-instances: %w", err)
	}

	var resp ec2DescribeResponse
	if err := json.Unmarshal(out, &resp); err != nil {
		return nil, fmt.Errorf("parse instances: %w", err)
	}

	var result []*domain.VMInfo
	for _, reservation := range resp.Reservations {
		for _, inst := range reservation.Instances {
			vm := convertInstance(inst, p.region)

			if filter.State != "" && vm.State != filter.State {
				continue
			}

			result = append(result, vm)
			if filter.Limit > 0 && len(result) >= filter.Limit {
				break
			}
		}
	}

	return result, nil
}

// GetVM returns details for a single EC2 instance.
func (p *Provider) GetVM(ctx context.Context, identifier string) (*domain.VMInfo, error) {
	if !p.connected {
		return nil, fmt.Errorf("not connected")
	}

	args := p.baseArgs("ec2", "describe-instances",
		"--instance-ids", identifier,
		"--output", "json")

	cmd := exec.CommandContext(ctx, "aws", args...)
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("aws ec2 describe-instances %q: %w", identifier, err)
	}

	var resp ec2DescribeResponse
	if err := json.Unmarshal(out, &resp); err != nil {
		return nil, fmt.Errorf("parse instance: %w", err)
	}

	if len(resp.Reservations) == 0 || len(resp.Reservations[0].Instances) == 0 {
		return nil, fmt.Errorf("instance not found: %s", identifier)
	}

	return convertInstance(resp.Reservations[0].Instances[0], p.region), nil
}

func (p *Provider) baseArgs(args ...string) []string {
	base := make([]string, 0, len(args)+4)
	base = append(base, args...)
	base = append(base, "--region", p.region)
	if p.profile != "" {
		base = append(base, "--profile", p.profile)
	}
	return base
}

func convertInstance(inst ec2Instance, region string) *domain.VMInfo {
	vm := &domain.VMInfo{
		Provider: domain.ProviderEC2,
		ID:       inst.InstanceID,
		Location: region,
	}

	if inst.State.Name != "" {
		vm.State = inst.State.Name
	}

	// Extract name from tags.
	for _, tag := range inst.Tags {
		if tag.Key == "Name" {
			vm.Name = tag.Value
		}
	}
	if vm.Name == "" {
		vm.Name = inst.InstanceID
	}

	vm.GuestOS = inst.Platform
	if vm.GuestOS == "" {
		vm.GuestOS = "linux"
	}

	vm.Tags = map[string]string{
		"instance_type": inst.InstanceType,
		"ami_id":        inst.ImageID,
	}

	if inst.PrivateIPAddress != "" {
		vm.IPAddresses = append(vm.IPAddresses, inst.PrivateIPAddress)
	}
	if inst.PublicIPAddress != "" {
		vm.IPAddresses = append(vm.IPAddresses, inst.PublicIPAddress)
	}

	// Map volumes.
	for _, mapping := range inst.BlockDeviceMappings {
		di := domain.DiskInfo{
			Name:   mapping.DeviceName,
			IsRoot: strings.HasSuffix(mapping.DeviceName, "a") || strings.HasSuffix(mapping.DeviceName, "a1"),
		}
		if mapping.EBS.VolumeID != "" {
			di.ID = mapping.EBS.VolumeID
		}
		vm.Disks = append(vm.Disks, di)
	}

	return vm
}

// AWS CLI JSON structures.
type ec2DescribeResponse struct {
	Reservations []struct {
		Instances []ec2Instance `json:"Instances"`
	} `json:"Reservations"`
}

type ec2Instance struct {
	InstanceID       string `json:"InstanceId"`
	InstanceType     string `json:"InstanceType"`
	ImageID          string `json:"ImageId"`
	Platform         string `json:"Platform"`
	PrivateIPAddress string `json:"PrivateIpAddress"`
	PublicIPAddress  string `json:"PublicIpAddress"`
	State            struct {
		Name string `json:"Name"`
	} `json:"State"`
	Tags []struct {
		Key   string `json:"Key"`
		Value string `json:"Value"`
	} `json:"Tags"`
	BlockDeviceMappings []struct {
		DeviceName string `json:"DeviceName"`
		EBS        struct {
			VolumeID string `json:"VolumeId"`
		} `json:"Ebs"`
	} `json:"BlockDeviceMappings"`
}
