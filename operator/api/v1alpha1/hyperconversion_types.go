// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

/*
Copyright 2026 HyperConversion Operator Authors.

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
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// EDIT THIS FILE!  THIS IS SCAFFOLDING FOR YOU TO OWN!
// NOTE: json tags are required.  Any new fields you add must have json tags for the fields to be serialized.

// HyperConversionSpec defines the desired state of HyperConversion
type HyperConversionSpec struct {
	// Source defines the source disk image location and format
	// +kubebuilder:validation:Required
	Source SourceSpec `json:"source"`

	// Storage defines the target storage configuration
	// +kubebuilder:validation:Required
	Storage StorageSpec `json:"storage"`

	// VM defines the VirtualMachine specification (optional - if omitted, only disk conversion is performed)
	// +optional
	VM *VMSpec `json:"vm,omitempty"`

	// Conversion defines conversion options like compression and offline fixes
	// +optional
	Conversion *ConversionOptions `json:"conversion,omitempty"`
}

// SourceSpec defines the source disk image
type SourceSpec struct {
	// URL is the HTTP/HTTPS/S3 URL of the source disk image
	// +kubebuilder:validation:Required
	// +kubebuilder:validation:Pattern=`^https?://.*$|^s3://.*$`
	URL string `json:"url"`

	// Format is the disk image format (vmdk, vdi, vhd, vhdx, qcow2, raw)
	// +kubebuilder:validation:Enum=vmdk;vdi;vhd;vhdx;qcow2;raw
	// +kubebuilder:default=qcow2
	// +optional
	Format string `json:"format,omitempty"`

	// Checksum for source validation (optional)
	// Format: "md5:abc123" or "sha256:def456"
	// +optional
	Checksum string `json:"checksum,omitempty"`

	// SecretRef references a Secret containing authentication credentials
	// Expected keys: username, password (for HTTP basic auth) or accessKeyID, secretAccessKey (for S3)
	// +optional
	SecretRef *corev1.LocalObjectReference `json:"secretRef,omitempty"`

	// Endpoint is the custom S3 endpoint URL (for MinIO, Ceph RGW, etc.)
	// Only applicable when URL scheme is s3://
	// +optional
	Endpoint string `json:"endpoint,omitempty"`

	// Region is the S3 region (defaults to us-east-1 if not specified)
	// Only applicable when URL scheme is s3://
	// +optional
	Region string `json:"region,omitempty"`
}

// StorageSpec defines target storage configuration
type StorageSpec struct {
	// StorageClass to use for the DataVolume PVC
	// If not specified, uses cluster default StorageClass
	// +optional
	StorageClass *string `json:"storageClass,omitempty"`

	// Size is the requested storage size
	// If not specified, attempts auto-detection via HTTP HEAD request
	// +optional
	Size *resource.Quantity `json:"size,omitempty"`

	// AccessMode defines the PVC access mode
	// +kubebuilder:validation:Enum=ReadWriteOnce;ReadWriteMany;ReadOnlyMany
	// +kubebuilder:default=ReadWriteOnce
	// +optional
	AccessMode corev1.PersistentVolumeAccessMode `json:"accessMode,omitempty"`

	// VolumeMode defines whether the volume is block or filesystem
	// +kubebuilder:validation:Enum=Block;Filesystem
	// +kubebuilder:default=Filesystem
	// +optional
	VolumeMode *corev1.PersistentVolumeMode `json:"volumeMode,omitempty"`
}

// VMSpec defines the VirtualMachine configuration
type VMSpec struct {
	// Name of the VirtualMachine (defaults to HyperConversion name)
	// +optional
	Name string `json:"name,omitempty"`

	// CPU configuration
	// +kubebuilder:validation:Required
	CPU CPUSpec `json:"cpu"`

	// Memory is the amount of memory for the VM
	// +kubebuilder:validation:Required
	Memory resource.Quantity `json:"memory"`

	// Firmware configuration (bios, uefi, uefi-secure)
	// +kubebuilder:validation:Enum=bios;uefi;uefi-secure
	// +kubebuilder:default=bios
	// +optional
	Firmware string `json:"firmware,omitempty"`

	// Networks defines network interfaces
	// +optional
	Networks []NetworkSpec `json:"networks,omitempty"`

	// EvictionStrategy defines VM behavior during node drain
	// +kubebuilder:validation:Enum=LiveMigrate;LiveMigrateIfPossible;None
	// +kubebuilder:default=LiveMigrateIfPossible
	// +optional
	EvictionStrategy string `json:"evictionStrategy,omitempty"`

	// RunStrategy defines when the VM should be running
	// +kubebuilder:validation:Enum=Always;RerunOnFailure;Manual;Halted
	// +kubebuilder:default=Always
	// +optional
	RunStrategy string `json:"runStrategy,omitempty"`

	// CloudInit contains cloud-init configuration
	// +optional
	CloudInit *CloudInitSpec `json:"cloudInit,omitempty"`

	// AdditionalDisks defines additional disks to attach to the VM beyond the root disk
	// +optional
	AdditionalDisks []DiskSpec `json:"additionalDisks,omitempty"`
}

// DiskSpec defines an additional disk configuration
type DiskSpec struct {
	// Name of the disk (must be unique within the VM)
	// +kubebuilder:validation:Required
	Name string `json:"name"`

	// Source defines where the disk data comes from
	// +kubebuilder:validation:Required
	Source DiskSource `json:"source"`

	// Size of the disk (required for blank disks, optional for URL sources)
	// +optional
	Size *resource.Quantity `json:"size,omitempty"`

	// StorageClass to use for the disk PVC
	// +optional
	StorageClass *string `json:"storageClass,omitempty"`

	// BootOrder determines the order in which disks are tried for booting
	// Lower numbers are tried first. Root disk defaults to bootOrder 1.
	// +optional
	BootOrder *int `json:"bootOrder,omitempty"`

	// Bus type (virtio, sata, scsi)
	// +kubebuilder:validation:Enum=virtio;sata;scsi
	// +kubebuilder:default=virtio
	// +optional
	Bus string `json:"bus,omitempty"`
}

// DiskSource defines the source of disk data
type DiskSource struct {
	// URL is the HTTP/HTTPS/S3 URL of a disk image to import
	// Mutually exclusive with PVCName and Blank
	// +optional
	URL string `json:"url,omitempty"`

	// Format of the disk image (vmdk, vdi, vhd, vhdx, qcow2, raw)
	// Only applicable when URL is specified
	// +kubebuilder:validation:Enum=vmdk;vdi;vhd;vhdx;qcow2;raw
	// +optional
	Format string `json:"format,omitempty"`

	// PVCName references an existing PVC to use as the disk
	// Mutually exclusive with URL and Blank
	// +optional
	PVCName string `json:"pvcName,omitempty"`

	// Blank creates an empty disk
	// Mutually exclusive with URL and PVCName
	// Requires Size to be specified in DiskSpec
	// +optional
	Blank bool `json:"blank,omitempty"`
}

// CPUSpec defines CPU configuration
type CPUSpec struct {
	// Cores is the number of CPU cores
	// +kubebuilder:validation:Minimum=1
	// +kubebuilder:validation:Maximum=128
	// +kubebuilder:default=2
	Cores int32 `json:"cores"`

	// Sockets is the number of CPU sockets
	// +kubebuilder:validation:Minimum=1
	// +kubebuilder:default=1
	// +optional
	Sockets int32 `json:"sockets,omitempty"`

	// Threads is the number of threads per core
	// +kubebuilder:validation:Minimum=1
	// +kubebuilder:default=1
	// +optional
	Threads int32 `json:"threads,omitempty"`
}

// NetworkSpec defines a network interface
type NetworkSpec struct {
	// Name of the network interface
	// +kubebuilder:validation:Required
	Name string `json:"name"`

	// Type of network (pod, bridge, sriov, multus)
	// +kubebuilder:validation:Enum=pod;bridge;sriov;multus
	// +kubebuilder:default=pod
	Type string `json:"type"`

	// NetworkName for bridge/multus networks (name of NetworkAttachmentDefinition)
	// +optional
	NetworkName string `json:"networkName,omitempty"`

	// MacAddress to assign (optional)
	// +optional
	MacAddress string `json:"macAddress,omitempty"`

	// Model is the network interface model (virtio, e1000, e1000e, rtl8139)
	// +kubebuilder:validation:Enum=virtio;e1000;e1000e;rtl8139
	// +kubebuilder:default=virtio
	// +optional
	Model string `json:"model,omitempty"`
}

// CloudInitSpec defines cloud-init configuration
type CloudInitSpec struct {
	// UserData contains cloud-init user data
	// +optional
	UserData string `json:"userData,omitempty"`

	// UserDataSecretRef references a Secret containing user data
	// +optional
	UserDataSecretRef *corev1.LocalObjectReference `json:"userDataSecretRef,omitempty"`

	// NetworkData contains cloud-init network data
	// +optional
	NetworkData string `json:"networkData,omitempty"`

	// NetworkDataSecretRef references a Secret containing network data
	// +optional
	NetworkDataSecretRef *corev1.LocalObjectReference `json:"networkDataSecretRef,omitempty"`
}

// ConversionOptions defines conversion behavior
type ConversionOptions struct {
	// Compression type for qcow2 output (zstd, zlib, none)
	// +kubebuilder:validation:Enum=zstd;zlib;none
	// +kubebuilder:default=zstd
	// +optional
	Compression string `json:"compression,omitempty"`

	// OfflineFixes enables offline disk modifications (fstab, grub, initramfs)
	// Requires Python worker integration
	// +optional
	OfflineFixes bool `json:"offlineFixes,omitempty"`

	// Timeout for conversion operations (in minutes)
	// +kubebuilder:validation:Minimum=5
	// +kubebuilder:validation:Maximum=1440
	// +kubebuilder:default=60
	// +optional
	Timeout int32 `json:"timeout,omitempty"`
}

// HyperConversionStatus defines the observed state of HyperConversion
type HyperConversionStatus struct {
	// Phase represents the current phase of the conversion
	// +kubebuilder:validation:Enum=Pending;Uploading;Converting;Fixing;CreatingVM;Ready;Failed
	// +optional
	Phase string `json:"phase,omitempty"`

	// Progress percentage (0-100)
	// +optional
	Progress int32 `json:"progress,omitempty"`

	// DataVolumeName is the name of the created DataVolume
	// +optional
	DataVolumeName string `json:"dataVolumeName,omitempty"`

	// AdditionalDiskDataVolumes maps disk name to DataVolume name for additional disks
	// +optional
	AdditionalDiskDataVolumes map[string]string `json:"additionalDiskDataVolumes,omitempty"`

	// FixerJobName is the name of the offline fixer Job
	// +optional
	FixerJobName string `json:"fixerJobName,omitempty"`

	// VirtualMachineName is the name of the created VirtualMachine
	// +optional
	VirtualMachineName string `json:"virtualMachineName,omitempty"`

	// UploadProgress contains detailed upload progress information
	// +optional
	UploadProgress *UploadProgressStatus `json:"uploadProgress,omitempty"`

	// StartTime is when the conversion started
	// +optional
	StartTime *metav1.Time `json:"startTime,omitempty"`

	// CompletionTime is when the conversion completed
	// +optional
	CompletionTime *metav1.Time `json:"completionTime,omitempty"`

	// Conditions represent the latest available observations
	// +optional
	Conditions []metav1.Condition `json:"conditions,omitempty"`

	// Message contains human-readable details about the current state
	// +optional
	Message string `json:"message,omitempty"`
}

// UploadProgressStatus contains detailed upload progress
type UploadProgressStatus struct {
	// BytesUploaded is the number of bytes uploaded so far
	// +optional
	BytesUploaded int64 `json:"bytesUploaded,omitempty"`

	// TotalBytes is the total size in bytes
	// +optional
	TotalBytes int64 `json:"totalBytes,omitempty"`

	// Speed is the current upload speed (bytes per second)
	// +optional
	Speed int64 `json:"speed,omitempty"`

	// LastUpdateTime is when progress was last updated
	// +optional
	LastUpdateTime *metav1.Time `json:"lastUpdateTime,omitempty"`
}

// Condition types
const (
	// ConditionTypeDataVolumeReady indicates DataVolume is ready
	ConditionTypeDataVolumeReady = "DataVolumeReady"
	// ConditionTypeVMReady indicates VirtualMachine is ready
	ConditionTypeVMReady = "VMReady"
	// ConditionTypeConversionComplete indicates conversion is complete
	ConditionTypeConversionComplete = "ConversionComplete"
)

// Phase constants
const (
	PhasePending    = "Pending"
	PhaseUploading  = "Uploading"
	PhaseConverting = "Converting"
	PhaseFixing     = "Fixing"
	PhaseCreatingVM = "CreatingVM"
	PhaseReady      = "Ready"
	PhaseFailed     = "Failed"
)

// Condition type for offline fixes
const (
	ConditionTypeFixesComplete = "FixesComplete"
)

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:shortName=hc;hconv
// +kubebuilder:printcolumn:name="Phase",type=string,JSONPath=`.status.phase`
// +kubebuilder:printcolumn:name="Progress",type=integer,JSONPath=`.status.progress`
// +kubebuilder:printcolumn:name="DataVolume",type=string,JSONPath=`.status.dataVolumeName`
// +kubebuilder:printcolumn:name="VM",type=string,JSONPath=`.status.virtualMachineName`
// +kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

// HyperConversion is the Schema for the hyperconversions API
type HyperConversion struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   HyperConversionSpec   `json:"spec,omitempty"`
	Status HyperConversionStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// HyperConversionList contains a list of HyperConversion
type HyperConversionList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []HyperConversion `json:"items"`
}

func init() {
	SchemeBuilder.Register(&HyperConversion{}, &HyperConversionList{})
}
