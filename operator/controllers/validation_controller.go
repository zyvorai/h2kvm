// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package controllers

import (
	"context"
	"fmt"
	"time"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/kubernetes"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/log"

	h2kvmv1 "github.com/h2kvm/operator/api/v1"
	opmetrics "github.com/h2kvm/operator/pkg/metrics"
	validationpkg "github.com/h2kvm/operator/pkg/validation"
	kubevirtv1 "kubevirt.io/api/core/v1"
)

const (
	validationFinalizer = "h2kvm.io/finalizer"
)

// ValidationReconciler reconciles a Validation object
type ValidationReconciler struct {
	client.Client
	Scheme    *runtime.Scheme
	Clientset kubernetes.Interface
}

//+kubebuilder:rbac:groups=h2kvm.io,resources=validations,verbs=get;list;watch;create;update;patch;delete
//+kubebuilder:rbac:groups=h2kvm.io,resources=validations/status,verbs=get;update;patch
//+kubebuilder:rbac:groups=h2kvm.io,resources=validations/finalizers,verbs=update
//+kubebuilder:rbac:groups="",resources=pods,verbs=get;list;watch;create;delete
//+kubebuilder:rbac:groups="",resources=pods/log,verbs=get
//+kubebuilder:rbac:groups="",resources=persistentvolumeclaims,verbs=get;list
//+kubebuilder:rbac:groups=kubevirt.io,resources=virtualmachines,verbs=get;list;create;update
//+kubebuilder:rbac:groups="",resources=events,verbs=create;patch

// Reconcile handles the reconciliation loop for Validation resources
func (r *ValidationReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	// Fetch the Validation instance
	validation := &h2kvmv1.Validation{}
	if err := r.Get(ctx, req.NamespacedName, validation); err != nil {
		if errors.IsNotFound(err) {
			logger.Info("Validation resource not found, ignoring reconcile")
			return ctrl.Result{}, nil
		}
		logger.Error(err, "Failed to get Validation resource")
		return ctrl.Result{}, err
	}

	// Handle deletion
	if !validation.ObjectMeta.DeletionTimestamp.IsZero() {
		return r.handleDeletion(ctx, validation)
	}

	// Add finalizer if not present
	if !controllerutil.ContainsFinalizer(validation, validationFinalizer) {
		controllerutil.AddFinalizer(validation, validationFinalizer)
		if err := r.Update(ctx, validation); err != nil {
			return ctrl.Result{}, err
		}
		return ctrl.Result{Requeue: true}, nil
	}

	// Handle validation based on current phase
	switch validation.Status.Phase {
	case "", h2kvmv1.PhasePending:
		return r.handlePending(ctx, validation)
	case h2kvmv1.PhaseRunning:
		return r.handleRunning(ctx, validation)
	case h2kvmv1.PhaseValidated:
		return r.handleValidated(ctx, validation)
	case h2kvmv1.PhaseFailed:
		return ctrl.Result{}, nil
	case h2kvmv1.PhaseKubeVirtCreated:
		return ctrl.Result{}, nil
	}

	return ctrl.Result{}, nil
}

// handlePending creates the validation pod and transitions to Running phase
func (r *ValidationReconciler) handlePending(ctx context.Context, validation *h2kvmv1.Validation) (ctrl.Result, error) {
	logger := log.FromContext(ctx)
	logger.Info("Starting validation", "name", validation.Name)

	// Update phase to Running
	now := metav1.Now()
	validation.Status.Phase = h2kvmv1.PhaseRunning
	validation.Status.StartTime = &now
	validation.Status.Message = "Creating validation pod"

	if err := r.Status().Update(ctx, validation); err != nil {
		logger.Error(err, "Failed to update status to Running")
		return ctrl.Result{}, err
	}

	// Create validation pod
	opmetrics.ActiveValidations.Inc()
	podCreateStart := time.Now()
	pod, err := r.createValidationPod(ctx, validation)
	opmetrics.ValidationPodCreationDuration.Observe(time.Since(podCreateStart).Seconds())
	if err != nil {
		logger.Error(err, "Failed to create validation pod")
		opmetrics.ActiveValidations.Dec()
		opmetrics.RecordReconcileError("pending")
		validation.Status.Phase = h2kvmv1.PhaseFailed
		validation.Status.Message = fmt.Sprintf("Failed to create validation pod: %v", err)
		_ = r.Status().Update(ctx, validation)
		return ctrl.Result{}, err
	}

	validation.Status.ValidationPod = pod.Name
	if err := r.Status().Update(ctx, validation); err != nil {
		logger.Error(err, "Failed to update status with pod name")
		return ctrl.Result{}, err
	}

	logger.Info("Validation pod created", "pod", pod.Name)
	return ctrl.Result{RequeueAfter: 10 * time.Second}, nil
}

// handleRunning checks the validation pod status and processes results
func (r *ValidationReconciler) handleRunning(ctx context.Context, validation *h2kvmv1.Validation) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	// Get validation pod
	pod := &corev1.Pod{}
	podName := types.NamespacedName{
		Name:      validation.Status.ValidationPod,
		Namespace: validation.Namespace,
	}

	if err := r.Get(ctx, podName, pod); err != nil {
		if errors.IsNotFound(err) {
			logger.Error(err, "Validation pod not found")
			validation.Status.Phase = h2kvmv1.PhaseFailed
			validation.Status.Message = "Validation pod disappeared"
			_ = r.Status().Update(ctx, validation)
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	// Check timeout
	if validation.Status.StartTime != nil {
		elapsed := time.Since(validation.Status.StartTime.Time).Seconds()
		timeout := float64(validation.Spec.Timeout)
		if timeout == 0 {
			timeout = 300 // Default 5 minutes
		}
		if elapsed > timeout {
			logger.Info("Validation timeout exceeded", "elapsed", elapsed, "timeout", timeout)
			opmetrics.ActiveValidations.Dec()
			opmetrics.ValidationTimeouts.Inc()
			opmetrics.RecordValidationResult("timeout", elapsed)
			validation.Status.Phase = h2kvmv1.PhaseFailed
			validation.Status.Message = fmt.Sprintf("Validation timeout exceeded (%0.0fs)", elapsed)
			validation.Status.Validated = false
			now := metav1.Now()
			validation.Status.CompletionTime = &now
			_ = r.Status().Update(ctx, validation)
			_ = r.Delete(ctx, pod)
			return ctrl.Result{}, nil
		}
	}

	// Check pod status
	switch pod.Status.Phase {
	case corev1.PodPending:
		validation.Status.Message = "Validation pod pending"
		_ = r.Status().Update(ctx, validation)
		return ctrl.Result{RequeueAfter: 10 * time.Second}, nil

	case corev1.PodRunning:
		validation.Status.Message = "Validation running"
		_ = r.Status().Update(ctx, validation)
		return ctrl.Result{RequeueAfter: 10 * time.Second}, nil

	case corev1.PodSucceeded:
		return r.handleValidationSuccess(ctx, validation, pod)

	case corev1.PodFailed:
		return r.handleValidationFailure(ctx, validation, pod)
	}

	return ctrl.Result{RequeueAfter: 10 * time.Second}, nil
}

// handleValidationSuccess processes successful validation results
func (r *ValidationReconciler) handleValidationSuccess(ctx context.Context, validation *h2kvmv1.Validation, pod *corev1.Pod) (ctrl.Result, error) {
	logger := log.FromContext(ctx)
	logger.Info("Validation succeeded", "name", validation.Name)

	opmetrics.ActiveValidations.Dec()
	if validation.Status.StartTime != nil {
		opmetrics.RecordValidationResult("success", time.Since(validation.Status.StartTime.Time).Seconds())
	}

	// Parse validation results from pod logs
	checks, err := validationpkg.ParseValidationResults(ctx, r.Clientset, pod.Name, pod.Namespace)
	if err != nil {
		logger.Error(err, "Failed to parse validation results")
		validation.Status.Phase = h2kvmv1.PhaseFailed
		validation.Status.Message = fmt.Sprintf("Failed to parse results: %v", err)
		validation.Status.Validated = false
	} else {
		validation.Status.Phase = h2kvmv1.PhaseValidated
		validation.Status.Message = "Validation successful"
		validation.Status.Validated = true
		validation.Status.Checks = checks
	}

	now := metav1.Now()
	validation.Status.CompletionTime = &now

	if err := r.Status().Update(ctx, validation); err != nil {
		return ctrl.Result{}, err
	}

	// Clean up validation pod
	if err := r.Delete(ctx, pod); err != nil {
		logger.Error(err, "Failed to delete validation pod")
	}

	return ctrl.Result{}, nil
}

// handleValidationFailure processes failed validation
func (r *ValidationReconciler) handleValidationFailure(ctx context.Context, validation *h2kvmv1.Validation, pod *corev1.Pod) (ctrl.Result, error) {
	logger := log.FromContext(ctx)
	logger.Info("Validation failed", "name", validation.Name)

	opmetrics.ActiveValidations.Dec()
	if validation.Status.StartTime != nil {
		opmetrics.RecordValidationResult("failed", time.Since(validation.Status.StartTime.Time).Seconds())
	}

	validation.Status.Phase = h2kvmv1.PhaseFailed
	validation.Status.Validated = false

	// Get failure reason from pod
	if len(pod.Status.ContainerStatuses) > 0 {
		containerStatus := pod.Status.ContainerStatuses[0]
		if containerStatus.State.Terminated != nil {
			validation.Status.Message = fmt.Sprintf("Validation failed: %s", containerStatus.State.Terminated.Reason)
		}
	}
	if validation.Status.Message == "" {
		validation.Status.Message = "Validation failed"
	}

	now := metav1.Now()
	validation.Status.CompletionTime = &now

	if err := r.Status().Update(ctx, validation); err != nil {
		return ctrl.Result{}, err
	}

	// Clean up validation pod
	if err := r.Delete(ctx, pod); err != nil {
		logger.Error(err, "Failed to delete validation pod")
	}

	return ctrl.Result{}, nil
}

// handleValidated creates KubeVirt VM if requested
func (r *ValidationReconciler) handleValidated(ctx context.Context, validation *h2kvmv1.Validation) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	// Check if KubeVirt VM creation is requested
	if !validation.Spec.CreateKubeVirtVM {
		return ctrl.Result{}, nil
	}

	// Check if VM already created
	if validation.Status.KubeVirtVM != "" {
		return ctrl.Result{}, nil
	}

	logger.Info("Creating KubeVirt VM", "name", validation.Name)

	vmCreateStart := time.Now()
	vm, err := r.createKubeVirtVM(ctx, validation)
	vmCreateDuration := time.Since(vmCreateStart).Seconds()
	if err != nil {
		logger.Error(err, "Failed to create KubeVirt VM")
		opmetrics.RecordKubeVirtVMCreation("failed", vmCreateDuration)
		validation.Status.Message = fmt.Sprintf("Failed to create KubeVirt VM: %v", err)
		_ = r.Status().Update(ctx, validation)
		return ctrl.Result{}, err
	}

	opmetrics.RecordKubeVirtVMCreation("success", vmCreateDuration)

	validation.Status.Phase = h2kvmv1.PhaseKubeVirtCreated
	validation.Status.KubeVirtVM = vm.Name
	validation.Status.Message = fmt.Sprintf("KubeVirt VM created: %s", vm.Name)

	if err := r.Status().Update(ctx, validation); err != nil {
		return ctrl.Result{}, err
	}

	logger.Info("KubeVirt VM created successfully", "vm", vm.Name)
	return ctrl.Result{}, nil
}

// createValidationPod creates a pod that runs the validation
func (r *ValidationReconciler) createValidationPod(ctx context.Context, validation *h2kvmv1.Validation) (*corev1.Pod, error) {
	podSpec := validationpkg.BuildValidationPodSpec(validation)

	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      fmt.Sprintf("%s-validation", validation.Name),
			Namespace: validation.Namespace,
			Labels: map[string]string{
				"app":                         "h2kvm-validation",
				"h2kvm.io/validation":     validation.Name,
				"h2kvm.io/validation-uid": string(validation.UID),
			},
		},
		Spec: *podSpec,
	}

	// Set owner reference
	if err := controllerutil.SetControllerReference(validation, pod, r.Scheme); err != nil {
		return nil, fmt.Errorf("failed to set owner reference on validation pod %q in namespace %q: %w", pod.Name, pod.Namespace, err)
	}

	if err := r.Create(ctx, pod); err != nil {
		if errors.IsAlreadyExists(err) {
			// Pod already exists (e.g. status update failed on previous reconcile).
			// Fetch and return the existing pod.
			existing := &corev1.Pod{}
			if getErr := r.Get(ctx, types.NamespacedName{Name: pod.Name, Namespace: pod.Namespace}, existing); getErr != nil {
				return nil, fmt.Errorf("validation pod %q already exists in namespace %q but failed to retrieve it: %w", pod.Name, pod.Namespace, getErr)
			}
			return existing, nil
		}
		return nil, fmt.Errorf("failed to create validation pod %q in namespace %q: %w — check RBAC permissions and resource quotas", pod.Name, pod.Namespace, err)
	}

	return pod, nil
}

// createKubeVirtVM creates a KubeVirt VirtualMachine from the validation
func (r *ValidationReconciler) createKubeVirtVM(ctx context.Context, validation *h2kvmv1.Validation) (*kubevirtv1.VirtualMachine, error) {
	vmSpec, err := validationpkg.BuildKubeVirtVMSpec(validation)
	if err != nil {
		return nil, err
	}

	vm := &kubevirtv1.VirtualMachine{
		ObjectMeta: metav1.ObjectMeta{
			Name:      fmt.Sprintf("%s-vm", validation.Name),
			Namespace: validation.Namespace,
			Labels: map[string]string{
				"app":                     "h2kvm",
				"h2kvm.io/validation": validation.Name,
			},
		},
		Spec: *vmSpec,
	}

	// Set owner reference
	if err := controllerutil.SetControllerReference(validation, vm, r.Scheme); err != nil {
		return nil, fmt.Errorf("failed to set owner reference on KubeVirt VM %q in namespace %q: %w", vm.Name, vm.Namespace, err)
	}

	if err := r.Create(ctx, vm); err != nil {
		return nil, fmt.Errorf("failed to create KubeVirt VM %q in namespace %q: %w — ensure KubeVirt is installed ('kubectl get kubevirt -A') and the operator has RBAC permissions for kubevirt.io/virtualmachines", vm.Name, vm.Namespace, err)
	}

	return vm, nil
}

// handleDeletion handles cleanup when Validation is deleted
func (r *ValidationReconciler) handleDeletion(ctx context.Context, validation *h2kvmv1.Validation) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	if controllerutil.ContainsFinalizer(validation, validationFinalizer) {
		// Clean up validation pod if exists
		if validation.Status.ValidationPod != "" {
			pod := &corev1.Pod{}
			podName := types.NamespacedName{
				Name:      validation.Status.ValidationPod,
				Namespace: validation.Namespace,
			}
			if err := r.Get(ctx, podName, pod); err == nil {
				if err := r.Delete(ctx, pod); err != nil {
					logger.Error(err, "Failed to delete validation pod during cleanup")
				}
			}
		}

		// Remove finalizer
		controllerutil.RemoveFinalizer(validation, validationFinalizer)
		if err := r.Update(ctx, validation); err != nil {
			return ctrl.Result{}, err
		}
	}

	return ctrl.Result{}, nil
}

// SetupWithManager sets up the controller with the Manager
func (r *ValidationReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&h2kvmv1.Validation{}).
		Owns(&corev1.Pod{}).
		Owns(&kubevirtv1.VirtualMachine{}).
		Complete(r)
}
