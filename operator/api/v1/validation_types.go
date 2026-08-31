// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package v1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
)

// ValidationSpec defines the desired state of Validation
type ValidationSpec struct {
	// Image is the disk image path or PVC name
	// +kubebuilder:validation:Required
	Image string `json:"image"`

	// Memory in MB
	// +kubebuilder:default=2048
	Memory int `json:"memory,omitempty"`

	// Number of CPUs
	// +kubebuilder:default=2
	CPUs int `json:"cpus,omitempty"`

	// Validation timeout in seconds
	// +kubebuilder:default=300
	Timeout int `json:"timeout,omitempty"`

	// Enable TPM emulation
	// +kubebuilder:default=false
	TPM bool `json:"tpm,omitempty"`

	// Enable vsock communication
	// +kubebuilder:default=true
	Vsock bool `json:"vsock,omitempty"`

	// Cloud-init user-data
	CloudInit string `json:"cloudInit,omitempty"`

	// Enable Kubernetes node validation
	// +kubebuilder:default=false
	KubernetesValidation bool `json:"kubernetesValidation,omitempty"`

	// Create KubeVirt VM after successful validation
	// +kubebuilder:default=false
	CreateKubeVirtVM bool `json:"createKubeVirtVM,omitempty"`

	// KubeVirt VM template
	KubeVirtTemplate *runtime.RawExtension `json:"kubevirtTemplate,omitempty"`
}

// ValidationChecks contains individual validation check results
type ValidationChecks struct {
	Systemd          bool `json:"systemd,omitempty"`
	Network          bool `json:"network,omitempty"`
	BootComplete     bool `json:"bootComplete,omitempty"`
	CloudInit        bool `json:"cloudInit,omitempty"`
	Kubelet          bool `json:"kubelet,omitempty"`
	ContainerRuntime bool `json:"containerRuntime,omitempty"`
	CNI              bool `json:"cni,omitempty"`
}

// ValidationPhase represents the current phase of validation
type ValidationPhase string

const (
	PhasePending         ValidationPhase = "Pending"
	PhaseRunning         ValidationPhase = "Running"
	PhaseValidated       ValidationPhase = "Validated"
	PhaseFailed          ValidationPhase = "Failed"
	PhaseKubeVirtCreated ValidationPhase = "KubeVirtCreated"
)

// ValidationStatus defines the observed state of Validation
type ValidationStatus struct {
	// Current phase of validation
	Phase ValidationPhase `json:"phase,omitempty"`

	// Whether validation passed
	Validated bool `json:"validated,omitempty"`

	// Human-readable message
	Message string `json:"message,omitempty"`

	// Name of validation pod
	ValidationPod string `json:"validationPod,omitempty"`

	// Name of created KubeVirt VM
	KubeVirtVM string `json:"kubevirtVM,omitempty"`

	// Validation start time
	StartTime *metav1.Time `json:"startTime,omitempty"`

	// Validation completion time
	CompletionTime *metav1.Time `json:"completionTime,omitempty"`

	// Individual validation checks
	Checks *ValidationChecks `json:"checks,omitempty"`
}

//+kubebuilder:object:root=true
//+kubebuilder:subresource:status
//+kubebuilder:resource:shortName=h2kv
//+kubebuilder:printcolumn:name="Phase",type=string,JSONPath=`.status.phase`
//+kubebuilder:printcolumn:name="Validated",type=boolean,JSONPath=`.status.validated`
//+kubebuilder:printcolumn:name="KubeVirt VM",type=string,JSONPath=`.status.kubevirtVM`
//+kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

// Validation is the Schema for VM validation
type Validation struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   ValidationSpec   `json:"spec,omitempty"`
	Status ValidationStatus `json:"status,omitempty"`
}

//+kubebuilder:object:root=true

// ValidationList contains a list of Validation
type ValidationList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []Validation `json:"items"`
}

func init() {
	SchemeBuilder.Register(&Validation{}, &ValidationList{})
}
