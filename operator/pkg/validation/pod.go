// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package validation

import (
	"encoding/base64"
	"fmt"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"

	h2kvmv1 "github.com/h2kvm/operator/api/v1"
)

// BuildValidationPodSpec builds the pod specification for running validation
func BuildValidationPodSpec(validation *h2kvmv1.Validation) *corev1.PodSpec {
	// Build command arguments
	args := []string{
		"python3", "-m", "h2kvm.vmspawn.validator",
		"--image", validation.Spec.Image,
		"--memory", fmt.Sprintf("%d", validation.Spec.Memory),
		"--cpus", fmt.Sprintf("%d", validation.Spec.CPUs),
		"--timeout", fmt.Sprintf("%d", validation.Spec.Timeout),
	}

	if validation.Spec.TPM {
		args = append(args, "--tpm")
	}

	if validation.Spec.Vsock {
		args = append(args, "--vsock")
	}

	if validation.Spec.KubernetesValidation {
		args = append(args, "--kubernetes")
	}

	if validation.Spec.CloudInit != "" {
		// Encode cloud-init data as base64
		encoded := base64.StdEncoding.EncodeToString([]byte(validation.Spec.CloudInit))
		args = append(args, "--cloud-init-base64", encoded)
	}

	// Add JSON output flag
	args = append(args, "--output", "json")

	privileged := true
	hostNetwork := true

	podSpec := &corev1.PodSpec{
		RestartPolicy: corev1.RestartPolicyNever,
		HostNetwork:   hostNetwork,
		Containers: []corev1.Container{
			{
				Name:  "validator",
				Image: "ghcr.io/ssahani/h2kvm-validator:0.3.0",
				Args:  args,
				SecurityContext: &corev1.SecurityContext{
					Privileged: &privileged,
				},
				Resources: corev1.ResourceRequirements{
					Requests: corev1.ResourceList{
						corev1.ResourceCPU:    resource.MustParse("1"),
						corev1.ResourceMemory: resource.MustParse("2Gi"),
					},
					Limits: corev1.ResourceList{
						corev1.ResourceCPU:    resource.MustParse("4"),
						corev1.ResourceMemory: resource.MustParse("8Gi"),
					},
				},
				VolumeMounts: []corev1.VolumeMount{
					{
						Name:      "dev-kvm",
						MountPath: "/dev/kvm",
					},
					{
						Name:      "sys-fs-cgroup",
						MountPath: "/sys/fs/cgroup",
						ReadOnly:  true,
					},
				},
			},
		},
		Volumes: []corev1.Volume{
			{
				Name: "dev-kvm",
				VolumeSource: corev1.VolumeSource{
					HostPath: &corev1.HostPathVolumeSource{
						Path: "/dev/kvm",
					},
				},
			},
			{
				Name: "sys-fs-cgroup",
				VolumeSource: corev1.VolumeSource{
					HostPath: &corev1.HostPathVolumeSource{
						Path: "/sys/fs/cgroup",
					},
				},
			},
		},
	}

	// Add image volume if it's a host path
	if !isPVCName(validation.Spec.Image) {
		podSpec.Volumes = append(podSpec.Volumes, corev1.Volume{
			Name: "image",
			VolumeSource: corev1.VolumeSource{
				HostPath: &corev1.HostPathVolumeSource{
					Path: validation.Spec.Image,
				},
			},
		})
		podSpec.Containers[0].VolumeMounts = append(podSpec.Containers[0].VolumeMounts,
			corev1.VolumeMount{
				Name:      "image",
				MountPath: validation.Spec.Image,
				ReadOnly:  true,
			},
		)
	} else {
		// Use PVC
		podSpec.Volumes = append(podSpec.Volumes, corev1.Volume{
			Name: "image",
			VolumeSource: corev1.VolumeSource{
				PersistentVolumeClaim: &corev1.PersistentVolumeClaimVolumeSource{
					ClaimName: validation.Spec.Image,
					ReadOnly:  true,
				},
			},
		})
		podSpec.Containers[0].VolumeMounts = append(podSpec.Containers[0].VolumeMounts,
			corev1.VolumeMount{
				Name:      "image",
				MountPath: "/mnt/image",
				ReadOnly:  true,
			},
		)
		// Update image path in args
		for i, arg := range args {
			if arg == validation.Spec.Image {
				args[i] = "/mnt/image/disk.img"
			}
		}
	}

	return podSpec
}

// isPVCName checks if the image name is a PVC reference
func isPVCName(image string) bool {
	// Simple heuristic: if it doesn't start with /, it's a PVC name
	return len(image) > 0 && image[0] != '/'
}
