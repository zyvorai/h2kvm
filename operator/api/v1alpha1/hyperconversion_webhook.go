// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

/*
Copyright 2024.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package v1alpha1

import (
	"context"
	"fmt"
	"net/url"
	"strings"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	logf "sigs.k8s.io/controller-runtime/pkg/log"
	"sigs.k8s.io/controller-runtime/pkg/webhook"
	"sigs.k8s.io/controller-runtime/pkg/webhook/admission"
)

// log is for logging in this package.
var hyperconversionlog = logf.Log.WithName("hyperconversion-resource")

func (r *HyperConversion) SetupWebhookWithManager(mgr ctrl.Manager) error {
	return ctrl.NewWebhookManagedBy(mgr).
		For(r).
		WithDefaulter(&hyperConversionDefaulter{}).
		WithValidator(&hyperConversionValidator{}).
		Complete()
}

// +kubebuilder:webhook:path=/mutate-hyper2kvm-io-v1alpha1-hyperconversion,mutating=true,failurePolicy=fail,sideEffects=None,groups=hyper2kvm.io,resources=hyperconversions,verbs=create;update,versions=v1alpha1,name=mhyperconversion.kb.io,admissionReviewVersions=v1

// hyperConversionDefaulter implements webhook.CustomDefaulter.
type hyperConversionDefaulter struct{}

var _ webhook.CustomDefaulter = &hyperConversionDefaulter{}

// Default implements webhook.CustomDefaulter.
func (d *hyperConversionDefaulter) Default(_ context.Context, obj runtime.Object) error {
	r, ok := obj.(*HyperConversion)
	if !ok {
		return fmt.Errorf("expected *HyperConversion, got %T", obj)
	}
	hyperconversionlog.Info("default", "name", r.Name)

	// Do not set a default storage class - let Kubernetes use the cluster default
	// This prevents hardcoding "local-path" which may not exist on all clusters

	// Set default access mode if not specified
	if r.Spec.Storage.AccessMode == "" {
		r.Spec.Storage.AccessMode = "ReadWriteOnce"
	}

	// Set default volume mode if not specified
	if r.Spec.Storage.VolumeMode == nil {
		defaultMode := corev1.PersistentVolumeFilesystem
		r.Spec.Storage.VolumeMode = &defaultMode
	}

	// Set default firmware if VM is specified but firmware is not
	if r.Spec.VM != nil && r.Spec.VM.Firmware == "" {
		r.Spec.VM.Firmware = "bios"
	}

	// Set default memory if VM is specified but memory is zero
	if r.Spec.VM != nil && r.Spec.VM.Memory.IsZero() {
		r.Spec.VM.Memory = resource.MustParse("2Gi")
	}

	// Set default CPU cores if VM is specified but cores is 0
	if r.Spec.VM != nil && r.Spec.VM.CPU.Cores == 0 {
		r.Spec.VM.CPU.Cores = 2
	}

	// Set default CPU sockets if VM is specified but sockets is 0
	if r.Spec.VM != nil && r.Spec.VM.CPU.Sockets == 0 {
		r.Spec.VM.CPU.Sockets = 1
	}

	// Set default CPU threads if VM is specified but threads is 0
	if r.Spec.VM != nil && r.Spec.VM.CPU.Threads == 0 {
		r.Spec.VM.CPU.Threads = 1
	}

	// Set default run strategy if VM is specified but not set
	if r.Spec.VM != nil && r.Spec.VM.RunStrategy == "" {
		r.Spec.VM.RunStrategy = "Always"
	}

	// Set default eviction strategy if VM is specified but not set
	if r.Spec.VM != nil && r.Spec.VM.EvictionStrategy == "" {
		r.Spec.VM.EvictionStrategy = "LiveMigrateIfPossible"
	}

	// Set default network type if VM has networks but type not specified
	if r.Spec.VM != nil {
		for i := range r.Spec.VM.Networks {
			if r.Spec.VM.Networks[i].Type == "" {
				r.Spec.VM.Networks[i].Type = "pod"
			}
			if r.Spec.VM.Networks[i].Model == "" {
				r.Spec.VM.Networks[i].Model = "virtio"
			}
		}
	}

	// Set default compression if not specified
	if r.Spec.Conversion != nil && r.Spec.Conversion.Compression == "" {
		r.Spec.Conversion.Compression = "zstd"
	}

	// Set default timeout if conversion specified but timeout is 0
	if r.Spec.Conversion != nil && r.Spec.Conversion.Timeout == 0 {
		r.Spec.Conversion.Timeout = 60
	}

	return nil
}

// +kubebuilder:webhook:path=/validate-hyper2kvm-io-v1alpha1-hyperconversion,mutating=false,failurePolicy=fail,sideEffects=None,groups=hyper2kvm.io,resources=hyperconversions,verbs=create;update,versions=v1alpha1,name=vhyperconversion.kb.io,admissionReviewVersions=v1

// hyperConversionValidator implements webhook.CustomValidator.
type hyperConversionValidator struct{}

var _ webhook.CustomValidator = &hyperConversionValidator{}

// ValidateCreate implements webhook.CustomValidator.
func (v *hyperConversionValidator) ValidateCreate(_ context.Context, obj runtime.Object) (admission.Warnings, error) {
	r, ok := obj.(*HyperConversion)
	if !ok {
		return nil, fmt.Errorf("expected *HyperConversion, got %T", obj)
	}
	hyperconversionlog.Info("validate create", "name", r.Name)

	return r.validate()
}

// ValidateUpdate implements webhook.CustomValidator.
func (v *hyperConversionValidator) ValidateUpdate(_ context.Context, oldObj, newObj runtime.Object) (admission.Warnings, error) {
	r, ok := newObj.(*HyperConversion)
	if !ok {
		return nil, fmt.Errorf("expected *HyperConversion, got %T", newObj)
	}
	hyperconversionlog.Info("validate update", "name", r.Name)

	old, ok := oldObj.(*HyperConversion)
	if !ok {
		return nil, fmt.Errorf("expected *HyperConversion, got %T", oldObj)
	}

	// Once a DataVolume has been created, source and storage fields are immutable.
	if old.Status.DataVolumeName != "" {
		if r.Spec.Source.URL != old.Spec.Source.URL {
			return nil, fmt.Errorf("source.url is immutable after DataVolume has been created — to change the source URL, delete this HyperConversion and create a new one")
		}
		if r.Spec.Source.Format != old.Spec.Source.Format {
			return nil, fmt.Errorf("source.format is immutable after DataVolume has been created — to change the disk format, delete this HyperConversion and create a new one")
		}
		if r.Spec.Storage.StorageClass != old.Spec.Storage.StorageClass {
			// Compare pointer values safely.
			oldSC := ""
			newSC := ""
			if old.Spec.Storage.StorageClass != nil {
				oldSC = *old.Spec.Storage.StorageClass
			}
			if r.Spec.Storage.StorageClass != nil {
				newSC = *r.Spec.Storage.StorageClass
			}
			if oldSC != newSC {
				return nil, fmt.Errorf("storage.storageClass is immutable after DataVolume has been created")
			}
		}
		if r.Spec.Storage.AccessMode != old.Spec.Storage.AccessMode {
			return nil, fmt.Errorf("storage.accessMode is immutable after DataVolume has been created")
		}
	}

	return r.validate()
}

// ValidateDelete implements webhook.CustomValidator.
func (v *hyperConversionValidator) ValidateDelete(_ context.Context, obj runtime.Object) (admission.Warnings, error) {
	r, ok := obj.(*HyperConversion)
	if !ok {
		return nil, fmt.Errorf("expected *HyperConversion, got %T", obj)
	}
	hyperconversionlog.Info("validate delete", "name", r.Name)

	// No validation needed for delete
	return nil, nil
}

// validate performs common validation logic.
func (r *HyperConversion) validate() (admission.Warnings, error) {
	var warnings admission.Warnings

	// Validate source URL
	if r.Spec.Source.URL == "" {
		return nil, fmt.Errorf("source.url is required — provide an HTTP/HTTPS/S3 URL pointing to the VM disk image (e.g., https://example.com/vm.qcow2)")
	}

	// Validate URL format
	parsedURL, err := url.Parse(r.Spec.Source.URL)
	if err != nil {
		return nil, fmt.Errorf("source.url is not a valid URL: %v", err)
	}

	// Validate URL scheme
	if parsedURL.Scheme != "http" && parsedURL.Scheme != "https" && parsedURL.Scheme != "s3" {
		return nil, fmt.Errorf("source.url must use http, https, or s3 scheme, got: %s", parsedURL.Scheme)
	}

	// Validate format
	validFormats := []string{"vmdk", "vdi", "vhd", "vhdx", "qcow2", "raw"}
	if r.Spec.Source.Format != "" {
		valid := false
		for _, f := range validFormats {
			if r.Spec.Source.Format == f {
				valid = true
				break
			}
		}
		if !valid {
			return nil, fmt.Errorf("source.format must be one of: %s", strings.Join(validFormats, ", "))
		}
	}

	// Validate storage size if specified
	if r.Spec.Storage.Size != nil && !r.Spec.Storage.Size.IsZero() {
		size := r.Spec.Storage.Size.Value()
		if size < 1024*1024*1024 { // Less than 1GB
			warnings = append(warnings, "storage.size is less than 1GB, this may be too small for most VM images")
		}
	}

	// Validate VM configuration if specified
	if r.Spec.VM != nil {
		// Validate CPU
		if r.Spec.VM.CPU.Cores < 1 || r.Spec.VM.CPU.Cores > 128 {
			return nil, fmt.Errorf("vm.cpu.cores must be between 1 and 128, got %d — typical values: 2 (light workloads), 4 (general), 8+ (databases/heavy workloads)", r.Spec.VM.CPU.Cores)
		}
		if r.Spec.VM.CPU.Sockets < 1 {
			return nil, fmt.Errorf("vm.cpu.sockets must be at least 1")
		}
		if r.Spec.VM.CPU.Threads < 1 {
			return nil, fmt.Errorf("vm.cpu.threads must be at least 1")
		}

		// Validate memory
		if r.Spec.VM.Memory.IsZero() {
			return nil, fmt.Errorf("vm.memory is required when vm is specified — set a memory value like '2Gi', '4Gi', or '8Gi' (minimum recommended: 512Mi)")
		}
		memoryBytes := r.Spec.VM.Memory.Value()
		if memoryBytes < 512*1024*1024 { // Less than 512MB
			warnings = append(warnings, "vm.memory is less than 512MB, this may be too small for most VMs")
		}

		// Validate firmware
		validFirmware := []string{"bios", "uefi", "uefi-secure"}
		if r.Spec.VM.Firmware != "" {
			valid := false
			for _, f := range validFirmware {
				if r.Spec.VM.Firmware == f {
					valid = true
					break
				}
			}
			if !valid {
				return nil, fmt.Errorf("vm.firmware must be one of: %s", strings.Join(validFirmware, ", "))
			}
		}

		// Validate networks
		for i, net := range r.Spec.VM.Networks {
			if net.Name == "" {
				return nil, fmt.Errorf("vm.networks[%d].name is required", i)
			}
			validTypes := []string{"pod", "bridge", "sriov", "multus"}
			valid := false
			for _, t := range validTypes {
				if net.Type == t {
					valid = true
					break
				}
			}
			if !valid {
				return nil, fmt.Errorf("vm.networks[%d].type must be one of: %s", i, strings.Join(validTypes, ", "))
			}

			// Validate bridge/multus requires networkName
			if (net.Type == "bridge" || net.Type == "multus") && net.NetworkName == "" {
				return nil, fmt.Errorf("vm.networks[%d].networkName is required for type %q — specify the Multus NetworkAttachmentDefinition name (e.g., 'default/br-lan')", i, net.Type)
			}
		}

		// Warn about eviction strategy with ReadWriteOnce
		if r.Spec.VM.EvictionStrategy == "LiveMigrate" && r.Spec.Storage.AccessMode == "ReadWriteOnce" {
			warnings = append(warnings, "LiveMigrate eviction strategy requires ReadWriteMany access mode for shared storage")
		}
	}

	// Validate conversion options if specified
	if r.Spec.Conversion != nil {
		if r.Spec.Conversion.Timeout < 5 || r.Spec.Conversion.Timeout > 1440 {
			return nil, fmt.Errorf("conversion.timeout must be between 5 and 1440 minutes (24 hours), got %d — for large disks (>100GB), consider setting timeout to 120+ minutes", r.Spec.Conversion.Timeout)
		}

		validCompression := []string{"zstd", "zlib", "none"}
		if r.Spec.Conversion.Compression != "" {
			valid := false
			for _, c := range validCompression {
				if r.Spec.Conversion.Compression == c {
					valid = true
					break
				}
			}
			if !valid {
				return nil, fmt.Errorf("conversion.compression must be one of: %s", strings.Join(validCompression, ", "))
			}
		}
	}

	return warnings, nil
}
