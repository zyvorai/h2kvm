// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
	"sigs.k8s.io/controller-runtime/pkg/metrics"
)

var (
	// ValidationTotal tracks total number of validations
	ValidationTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "h2kvm_validation_total",
			Help: "Total number of VM validations",
		},
		[]string{"status"},
	)

	// ValidationDuration tracks validation duration
	ValidationDuration = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "h2kvm_validation_duration_seconds",
			Help:    "Duration of VM validations in seconds",
			Buckets: []float64{10, 30, 60, 120, 300, 600, 1200},
		},
		[]string{"status"},
	)

	// ValidationChecks tracks individual check results
	ValidationChecks = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "h2kvm_validation_checks_total",
			Help: "Total number of validation checks by type",
		},
		[]string{"check", "result"},
	)

	// ActiveValidations tracks currently running validations
	ActiveValidations = prometheus.NewGauge(
		prometheus.GaugeOpts{
			Name: "h2kvm_active_validations",
			Help: "Number of currently active validations",
		},
	)

	// ValidationPodCreationDuration tracks pod creation time
	ValidationPodCreationDuration = prometheus.NewHistogram(
		prometheus.HistogramOpts{
			Name:    "h2kvm_validation_pod_creation_duration_seconds",
			Help:    "Duration of validation pod creation in seconds",
			Buckets: prometheus.DefBuckets,
		},
	)

	// KubeVirtVMCreationTotal tracks KubeVirt VM creation
	KubeVirtVMCreationTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "h2kvm_kubevirt_vm_creation_total",
			Help: "Total number of KubeVirt VM creations",
		},
		[]string{"status"},
	)

	// KubeVirtVMCreationDuration tracks KubeVirt VM creation time
	KubeVirtVMCreationDuration = prometheus.NewHistogram(
		prometheus.HistogramOpts{
			Name:    "h2kvm_kubevirt_vm_creation_duration_seconds",
			Help:    "Duration of KubeVirt VM creation in seconds",
			Buckets: prometheus.DefBuckets,
		},
	)

	// ReconcileErrorsTotal tracks reconciliation errors
	ReconcileErrorsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "h2kvm_reconcile_errors_total",
			Help: "Total number of reconciliation errors",
		},
		[]string{"phase"},
	)

	// ReconcileDuration tracks reconciliation duration
	ReconcileDuration = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "h2kvm_reconcile_duration_seconds",
			Help:    "Duration of reconciliation loops in seconds",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"phase"},
	)

	// ValidationTimeouts tracks validation timeouts
	ValidationTimeouts = prometheus.NewCounter(
		prometheus.CounterOpts{
			Name: "h2kvm_validation_timeouts_total",
			Help: "Total number of validation timeouts",
		},
	)

	// ValidationQueueSize tracks validation queue size
	ValidationQueueSize = prometheus.NewGauge(
		prometheus.GaugeOpts{
			Name: "h2kvm_validation_queue_size",
			Help: "Current size of the validation queue",
		},
	)
)

func init() {
	// Register custom metrics with the controller-runtime metrics registry
	metrics.Registry.MustRegister(
		ValidationTotal,
		ValidationDuration,
		ValidationChecks,
		ActiveValidations,
		ValidationPodCreationDuration,
		KubeVirtVMCreationTotal,
		KubeVirtVMCreationDuration,
		ReconcileErrorsTotal,
		ReconcileDuration,
		ValidationTimeouts,
		ValidationQueueSize,
	)
}

// RecordValidationResult records a validation result
func RecordValidationResult(status string, duration float64) {
	ValidationTotal.WithLabelValues(status).Inc()
	ValidationDuration.WithLabelValues(status).Observe(duration)
}

// RecordValidationCheck records a validation check result
func RecordValidationCheck(check string, result string) {
	ValidationChecks.WithLabelValues(check, result).Inc()
}

// RecordKubeVirtVMCreation records a KubeVirt VM creation
func RecordKubeVirtVMCreation(status string, duration float64) {
	KubeVirtVMCreationTotal.WithLabelValues(status).Inc()
	KubeVirtVMCreationDuration.Observe(duration)
}

// RecordReconcileError records a reconciliation error
func RecordReconcileError(phase string) {
	ReconcileErrorsTotal.WithLabelValues(phase).Inc()
}

// RecordReconcileDuration records reconciliation duration
func RecordReconcileDuration(phase string, duration float64) {
	ReconcileDuration.WithLabelValues(phase).Observe(duration)
}
