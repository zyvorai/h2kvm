// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package validation

import (
	"encoding/json"
	"fmt"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	hyper2kvmv1 "github.com/hyper2kvm/operator/api/v1"
	kubevirtv1 "kubevirt.io/api/core/v1"
)

// BuildKubeVirtVMSpec builds a KubeVirt VirtualMachine spec from the validation
func BuildKubeVirtVMSpec(validation *hyper2kvmv1.Validation) (*kubevirtv1.VirtualMachineSpec, error) {
	// If user provided a custom template, use it
	if validation.Spec.KubeVirtTemplate != nil {
		var vmSpec kubevirtv1.VirtualMachineSpec
		if err := json.Unmarshal(validation.Spec.KubeVirtTemplate.Raw, &vmSpec); err != nil {
			return nil, fmt.Errorf("failed to unmarshal KubeVirt template: %w", err)
		}
		return &vmSpec, nil
	}

	// Build default spec based on validation parameters
	running := true

	vmSpec := &kubevirtv1.VirtualMachineSpec{
		Running: &running,
		Template: &kubevirtv1.VirtualMachineInstanceTemplateSpec{
			ObjectMeta: metav1.ObjectMeta{
				Labels: map[string]string{
					"app":                     "hyper2kvm",
					"hyper2kvm.io/validation": validation.Name,
				},
			},
			Spec: kubevirtv1.VirtualMachineInstanceSpec{
				Domain: kubevirtv1.DomainSpec{
					CPU: &kubevirtv1.CPU{
						Cores: uint32(validation.Spec.CPUs),
					},
					Devices: kubevirtv1.Devices{
						Disks: []kubevirtv1.Disk{
							{
								Name: "disk0",
								DiskDevice: kubevirtv1.DiskDevice{
									Disk: &kubevirtv1.DiskTarget{
										Bus: "virtio",
									},
								},
							},
						},
					},
					Resources: kubevirtv1.ResourceRequirements{
						Requests: corev1.ResourceList{
							corev1.ResourceMemory: resource.MustParse(fmt.Sprintf("%dMi", validation.Spec.Memory)),
						},
					},
				},
				Volumes: []kubevirtv1.Volume{},
			},
		},
	}

	// Add disk volume
	if isPVCName(validation.Spec.Image) {
		vmSpec.Template.Spec.Volumes = append(vmSpec.Template.Spec.Volumes, kubevirtv1.Volume{
			Name: "disk0",
			VolumeSource: kubevirtv1.VolumeSource{
				PersistentVolumeClaim: &kubevirtv1.PersistentVolumeClaimVolumeSource{
					PersistentVolumeClaimVolumeSource: corev1.PersistentVolumeClaimVolumeSource{
						ClaimName: validation.Spec.Image,
					},
				},
			},
		})
	} else {
		// For host path, we need to create a DataVolume or use containerDisk
		// For now, return error as host paths need special handling
		return nil, fmt.Errorf("host path images require manual PVC creation")
	}

	// Add TPM if requested
	if validation.Spec.TPM {
		vmSpec.Template.Spec.Domain.Devices.TPM = &kubevirtv1.TPMDevice{}
	}

	// Add cloud-init if provided
	if validation.Spec.CloudInit != "" {
		vmSpec.Template.Spec.Volumes = append(vmSpec.Template.Spec.Volumes, kubevirtv1.Volume{
			Name: "cloudinit",
			VolumeSource: kubevirtv1.VolumeSource{
				CloudInitNoCloud: &kubevirtv1.CloudInitNoCloudSource{
					UserData: validation.Spec.CloudInit,
				},
			},
		})
		vmSpec.Template.Spec.Domain.Devices.Disks = append(vmSpec.Template.Spec.Domain.Devices.Disks, kubevirtv1.Disk{
			Name: "cloudinit",
			DiskDevice: kubevirtv1.DiskDevice{
				Disk: &kubevirtv1.DiskTarget{
					Bus: "virtio",
				},
			},
		})
	}

	return vmSpec, nil
}
