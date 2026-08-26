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

package controllers

import (
	"context"
	"fmt"
	"os"
	"time"

	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/meta"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/tools/record"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/log"

	h2kvmv1 "github.com/h2kvm/operator/api/v1alpha1"
	opmetrics "github.com/h2kvm/operator/pkg/metrics"
)

const (
	hyperConversionFinalizer = "h2kvm.io/hyperconversion-finalizer"
)

// HyperConversionReconciler reconciles a HyperConversion object
type HyperConversionReconciler struct {
	client.Client
	Scheme   *runtime.Scheme
	Recorder record.EventRecorder
}

//+kubebuilder:rbac:groups=h2kvm.io,resources=hyperconversions,verbs=get;list;watch;create;update;patch;delete
//+kubebuilder:rbac:groups=h2kvm.io,resources=hyperconversions/status,verbs=get;update;patch
//+kubebuilder:rbac:groups=h2kvm.io,resources=hyperconversions/finalizers,verbs=update
//+kubebuilder:rbac:groups=cdi.kubevirt.io,resources=datavolumes,verbs=get;list;watch;create;update;patch;delete
//+kubebuilder:rbac:groups=kubevirt.io,resources=virtualmachines,verbs=get;list;watch;create;update;patch;delete
//+kubebuilder:rbac:groups=batch,resources=jobs,verbs=get;list;watch;create;delete
//+kubebuilder:rbac:groups="",resources=pods,verbs=get;list;watch
//+kubebuilder:rbac:groups="",resources=events,verbs=create;patch
//+kubebuilder:rbac:groups="",resources=persistentvolumeclaims,verbs=get;list;watch
//+kubebuilder:rbac:groups="",resources=configmaps,verbs=get;list;watch
//+kubebuilder:rbac:groups="",resources=secrets,verbs=get;list;watch

// Reconcile handles the reconciliation loop for HyperConversion resources.
func (r *HyperConversionReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	// Fetch the HyperConversion instance
	hc := &h2kvmv1.HyperConversion{}
	if err := r.Get(ctx, req.NamespacedName, hc); err != nil {
		if errors.IsNotFound(err) {
			logger.Info("HyperConversion resource not found, ignoring reconcile")
			return ctrl.Result{}, nil
		}
		logger.Error(err, "Failed to get HyperConversion resource")
		return ctrl.Result{}, err
	}

	// Add finalizer if not present (must happen before deletion check)
	if !controllerutil.ContainsFinalizer(hc, hyperConversionFinalizer) {
		// Only add finalizer if not already being deleted
		if hc.ObjectMeta.DeletionTimestamp.IsZero() {
			controllerutil.AddFinalizer(hc, hyperConversionFinalizer)
			if err := r.Update(ctx, hc); err != nil {
				return ctrl.Result{}, err
			}
			return ctrl.Result{Requeue: true}, nil
		}
	}

	// Handle deletion
	if !hc.ObjectMeta.DeletionTimestamp.IsZero() {
		return r.handleDeletion(ctx, hc)
	}

	// Handle phase transitions
	switch hc.Status.Phase {
	case "", h2kvmv1.PhasePending:
		return r.handlePending(ctx, hc)
	case h2kvmv1.PhaseUploading:
		return r.handleUploading(ctx, hc)
	case h2kvmv1.PhaseConverting:
		return r.handleConverting(ctx, hc)
	case h2kvmv1.PhaseFixing:
		return r.handleFixing(ctx, hc)
	case h2kvmv1.PhaseCreatingVM:
		return r.handleCreatingVM(ctx, hc)
	case h2kvmv1.PhaseReady:
		return ctrl.Result{}, nil
	case h2kvmv1.PhaseFailed:
		// Terminal state, no further reconciliation needed
		return ctrl.Result{}, nil
	}

	return ctrl.Result{}, nil
}

// handlePending creates the CDI DataVolume from the source URL and transitions to Uploading.
func (r *HyperConversionReconciler) handlePending(ctx context.Context, hc *h2kvmv1.HyperConversion) (ctrl.Result, error) {
	logger := log.FromContext(ctx)
	logger.Info("Handling Pending phase", "name", hc.Name)

	// Set start time
	now := metav1.Now()
	hc.Status.Phase = h2kvmv1.PhaseUploading
	hc.Status.StartTime = &now
	hc.Status.Progress = 0
	hc.Status.Message = "Creating DataVolume for disk import"

	// Create the DataVolume
	dv, err := r.createDataVolume(ctx, hc)
	if err != nil {
		logger.Error(err, "Failed to create DataVolume")
		opmetrics.RecordReconcileError("pending")
		hc.Status.Phase = h2kvmv1.PhaseFailed
		hc.Status.Message = fmt.Sprintf("Failed to create DataVolume: %v", err)
		meta.SetStatusCondition(&hc.Status.Conditions, metav1.Condition{
			Type:               h2kvmv1.ConditionTypeDataVolumeReady,
			Status:             metav1.ConditionFalse,
			Reason:             "CreateFailed",
			Message:            err.Error(),
			LastTransitionTime: now,
		})
		_ = r.Status().Update(ctx, hc)
		r.Recorder.Eventf(hc, corev1.EventTypeWarning, "DataVolumeCreateFailed", "Failed to create DataVolume: %v", err)
		return ctrl.Result{}, err
	}

	dvName, _, _ := unstructured.NestedString(dv.Object, "metadata", "name")
	hc.Status.DataVolumeName = dvName
	hc.Status.Message = fmt.Sprintf("DataVolume %s created, waiting for import to complete", dvName)

	meta.SetStatusCondition(&hc.Status.Conditions, metav1.Condition{
		Type:               h2kvmv1.ConditionTypeDataVolumeReady,
		Status:             metav1.ConditionFalse,
		Reason:             "Importing",
		Message:            "DataVolume import in progress",
		LastTransitionTime: now,
	})

	if err := r.Status().Update(ctx, hc); err != nil {
		logger.Error(err, "Failed to update status to Uploading")
		return ctrl.Result{}, err
	}

	r.Recorder.Eventf(hc, corev1.EventTypeNormal, "DataVolumeCreated", "DataVolume %s created", dvName)
	return ctrl.Result{RequeueAfter: 10 * time.Second}, nil
}

// handleUploading watches DataVolume progress, updates status, and transitions to Converting when done.
func (r *HyperConversionReconciler) handleUploading(ctx context.Context, hc *h2kvmv1.HyperConversion) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	if hc.Status.DataVolumeName == "" {
		logger.Error(nil, "DataVolumeName is empty in Uploading phase, transitioning to Failed")
		hc.Status.Phase = h2kvmv1.PhaseFailed
		hc.Status.Message = "DataVolume name missing in Uploading phase"
		_ = r.Status().Update(ctx, hc)
		return ctrl.Result{}, nil
	}

	// Fetch the DataVolume
	dv := &unstructured.Unstructured{}
	dv.SetGroupVersionKind(schema.GroupVersionKind{
		Group:   "cdi.kubevirt.io",
		Version: "v1beta1",
		Kind:    "DataVolume",
	})

	dvKey := types.NamespacedName{
		Name:      hc.Status.DataVolumeName,
		Namespace: hc.Namespace,
	}

	if err := r.Get(ctx, dvKey, dv); err != nil {
		if errors.IsNotFound(err) {
			logger.Error(err, "DataVolume not found")
			hc.Status.Phase = h2kvmv1.PhaseFailed
			hc.Status.Message = "DataVolume disappeared during import"
			_ = r.Status().Update(ctx, hc)
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	// Check the DataVolume phase
	dvPhase, _, _ := unstructured.NestedString(dv.Object, "status", "phase")
	dvProgress, _, _ := unstructured.NestedString(dv.Object, "status", "progress")

	logger.Info("DataVolume status", "phase", dvPhase, "progress", dvProgress, "datavolume", hc.Status.DataVolumeName)

	// Check for timeout
	if hc.Status.StartTime != nil {
		timeoutMinutes := int32(60)
		if hc.Spec.Conversion != nil && hc.Spec.Conversion.Timeout > 0 {
			timeoutMinutes = hc.Spec.Conversion.Timeout
		}
		elapsed := time.Since(hc.Status.StartTime.Time)
		if elapsed > time.Duration(timeoutMinutes)*time.Minute {
			logger.Info("Import timeout exceeded", "elapsed", elapsed, "timeout", timeoutMinutes)
			opmetrics.RecordReconcileError("uploading")
			hc.Status.Phase = h2kvmv1.PhaseFailed
			hc.Status.Message = fmt.Sprintf("Import timeout exceeded after %d minutes", timeoutMinutes)
			now := metav1.Now()
			hc.Status.CompletionTime = &now
			_ = r.Status().Update(ctx, hc)
			r.Recorder.Event(hc, corev1.EventTypeWarning, "ImportTimeout", hc.Status.Message)
			return ctrl.Result{}, nil
		}
	}

	switch dvPhase {
	case "Succeeded":
		logger.Info("DataVolume import succeeded", "datavolume", hc.Status.DataVolumeName)
		now := metav1.Now()
		hc.Status.Phase = h2kvmv1.PhaseConverting
		hc.Status.Progress = 50
		hc.Status.Message = "DataVolume import complete, starting conversion"

		meta.SetStatusCondition(&hc.Status.Conditions, metav1.Condition{
			Type:               h2kvmv1.ConditionTypeDataVolumeReady,
			Status:             metav1.ConditionTrue,
			Reason:             "ImportSucceeded",
			Message:            "DataVolume import completed successfully",
			LastTransitionTime: now,
		})

		if err := r.Status().Update(ctx, hc); err != nil {
			return ctrl.Result{}, err
		}

		r.Recorder.Eventf(hc, corev1.EventTypeNormal, "ImportComplete", "DataVolume %s import completed", hc.Status.DataVolumeName)
		return ctrl.Result{Requeue: true}, nil

	case "Failed":
		logger.Info("DataVolume import failed", "datavolume", hc.Status.DataVolumeName)
		now := metav1.Now()
		hc.Status.Phase = h2kvmv1.PhaseFailed
		hc.Status.CompletionTime = &now

		// Try to extract the failure message from DataVolume conditions
		failureMsg := "DataVolume import failed"
		conditions, found, _ := unstructured.NestedSlice(dv.Object, "status", "conditions")
		if found {
			for _, c := range conditions {
				cond, ok := c.(map[string]interface{})
				if !ok {
					continue
				}
				condType, _, _ := unstructured.NestedString(cond, "type")
				condMsg, _, _ := unstructured.NestedString(cond, "message")
				if condType == "Running" && condMsg != "" {
					failureMsg = fmt.Sprintf("DataVolume import failed: %s", condMsg)
					break
				}
			}
		}
		hc.Status.Message = failureMsg

		meta.SetStatusCondition(&hc.Status.Conditions, metav1.Condition{
			Type:               h2kvmv1.ConditionTypeDataVolumeReady,
			Status:             metav1.ConditionFalse,
			Reason:             "ImportFailed",
			Message:            failureMsg,
			LastTransitionTime: now,
		})

		_ = r.Status().Update(ctx, hc)
		r.Recorder.Event(hc, corev1.EventTypeWarning, "ImportFailed", failureMsg)
		return ctrl.Result{}, nil

	default:
		// Import is still in progress, update upload progress
		hc.Status.Message = fmt.Sprintf("DataVolume import in progress (phase: %s, progress: %s)", dvPhase, dvProgress)

		now := metav1.Now()
		if hc.Status.UploadProgress == nil {
			hc.Status.UploadProgress = &h2kvmv1.UploadProgressStatus{}
		}
		hc.Status.UploadProgress.LastUpdateTime = &now

		// Parse progress percentage if available (CDI reports progress as "N/A" or "XX.X%")
		if dvProgress != "" && dvProgress != "N/A" {
			var pct float64
			if _, err := fmt.Sscanf(dvProgress, "%f%%", &pct); err == nil {
				hc.Status.Progress = int32(pct / 2) // Scale 0-100% to 0-50% (uploading is first half)
			}
		}

		_ = r.Status().Update(ctx, hc)
		return ctrl.Result{RequeueAfter: 10 * time.Second}, nil
	}
}

// handleConverting transitions from CDI import to either offline fixes (Fixing phase)
// or directly to VM creation, depending on whether offlineFixes is enabled.
func (r *HyperConversionReconciler) handleConverting(ctx context.Context, hc *h2kvmv1.HyperConversion) (ctrl.Result, error) {
	logger := log.FromContext(ctx)
	logger.Info("Handling Converting phase", "name", hc.Name)

	now := metav1.Now()

	meta.SetStatusCondition(&hc.Status.Conditions, metav1.Condition{
		Type:               h2kvmv1.ConditionTypeConversionComplete,
		Status:             metav1.ConditionTrue,
		Reason:             "ConversionComplete",
		Message:            "Disk image conversion completed (handled by CDI)",
		LastTransitionTime: now,
	})

	// If offline fixes are enabled, transition to Fixing phase
	if hc.Spec.Conversion != nil && hc.Spec.Conversion.OfflineFixes {
		hc.Status.Phase = h2kvmv1.PhaseFixing
		hc.Status.Progress = 55
		hc.Status.Message = "Conversion complete, starting offline fixes (LVM, initramfs, fstab)"

		if err := r.Status().Update(ctx, hc); err != nil {
			return ctrl.Result{}, err
		}

		r.Recorder.Event(hc, corev1.EventTypeNormal, "ConversionComplete", "Disk conversion complete, starting offline fixes")
		return ctrl.Result{Requeue: true}, nil
	}

	// No offline fixes — skip to VM creation or Ready
	if hc.Spec.VM == nil {
		hc.Status.Phase = h2kvmv1.PhaseReady
		hc.Status.Progress = 100
		hc.Status.CompletionTime = &now
		hc.Status.Message = "Disk import and conversion complete (no VM creation requested)"

		if err := r.Status().Update(ctx, hc); err != nil {
			return ctrl.Result{}, err
		}

		r.Recorder.Event(hc, corev1.EventTypeNormal, "ConversionComplete", "Disk conversion complete, no VM requested")
		return ctrl.Result{}, nil
	}

	hc.Status.Phase = h2kvmv1.PhaseCreatingVM
	hc.Status.Progress = 75
	hc.Status.Message = "Conversion complete, creating VirtualMachine"

	if err := r.Status().Update(ctx, hc); err != nil {
		return ctrl.Result{}, err
	}

	r.Recorder.Event(hc, corev1.EventTypeNormal, "ConversionComplete", "Disk conversion complete, creating VM")
	return ctrl.Result{Requeue: true}, nil
}

// handleFixing spawns a privileged fixer Job that runs h2kvmctl offline fixes
// (LVM activation, initramfs regen, fstab rewrite, network fix) on the imported disk.
func (r *HyperConversionReconciler) handleFixing(ctx context.Context, hc *h2kvmv1.HyperConversion) (ctrl.Result, error) {
	logger := log.FromContext(ctx)
	logger.Info("Handling Fixing phase", "name", hc.Name)

	// If no fixer Job exists yet, create one
	if hc.Status.FixerJobName == "" {
		job, err := r.createFixerJob(ctx, hc)
		if err != nil {
			logger.Error(err, "Failed to create fixer Job")
			opmetrics.RecordReconcileError("fixing")
			now := metav1.Now()
			hc.Status.Phase = h2kvmv1.PhaseFailed
			hc.Status.CompletionTime = &now
			hc.Status.Message = fmt.Sprintf("Failed to create fixer Job: %v", err)
			if updateErr := r.Status().Update(ctx, hc); updateErr != nil {
				logger.Error(updateErr, "Failed to update status")
			}
			r.Recorder.Eventf(hc, corev1.EventTypeWarning, "FixerJobFailed", "Failed to create fixer Job: %v", err)
			return ctrl.Result{}, err
		}

		hc.Status.FixerJobName = job.Name
		hc.Status.Message = fmt.Sprintf("Fixer Job %s created, running offline fixes", job.Name)

		if err := r.Status().Update(ctx, hc); err != nil {
			return ctrl.Result{}, err
		}

		r.Recorder.Eventf(hc, corev1.EventTypeNormal, "FixerJobCreated", "Fixer Job %s created", job.Name)
		return ctrl.Result{RequeueAfter: 15 * time.Second}, nil
	}

	// Watch the existing fixer Job
	job := &batchv1.Job{}
	jobKey := types.NamespacedName{
		Name:      hc.Status.FixerJobName,
		Namespace: hc.Namespace,
	}

	if err := r.Get(ctx, jobKey, job); err != nil {
		if errors.IsNotFound(err) {
			logger.Error(err, "Fixer Job not found")
			now := metav1.Now()
			hc.Status.Phase = h2kvmv1.PhaseFailed
			hc.Status.CompletionTime = &now
			hc.Status.Message = "Fixer Job disappeared"
			if updateErr := r.Status().Update(ctx, hc); updateErr != nil {
				logger.Error(updateErr, "Failed to update status")
			}
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	// Check Job status
	for _, cond := range job.Status.Conditions {
		if cond.Type == batchv1.JobComplete && cond.Status == corev1.ConditionTrue {
			logger.Info("Fixer Job completed successfully", "job", job.Name)
			now := metav1.Now()

			meta.SetStatusCondition(&hc.Status.Conditions, metav1.Condition{
				Type:               h2kvmv1.ConditionTypeFixesComplete,
				Status:             metav1.ConditionTrue,
				Reason:             "FixesComplete",
				Message:            "Offline fixes completed (LVM, initramfs, fstab)",
				LastTransitionTime: now,
			})

			if hc.Spec.VM == nil {
				hc.Status.Phase = h2kvmv1.PhaseReady
				hc.Status.Progress = 100
				hc.Status.CompletionTime = &now
				hc.Status.Message = "Disk import, conversion, and offline fixes complete (no VM creation requested)"
			} else {
				hc.Status.Phase = h2kvmv1.PhaseCreatingVM
				hc.Status.Progress = 75
				hc.Status.Message = "Offline fixes complete, creating VirtualMachine"
			}

			if err := r.Status().Update(ctx, hc); err != nil {
				return ctrl.Result{}, err
			}

			r.Recorder.Event(hc, corev1.EventTypeNormal, "FixesComplete", "Offline fixes completed successfully")
			return ctrl.Result{Requeue: true}, nil
		}

		if cond.Type == batchv1.JobFailed && cond.Status == corev1.ConditionTrue {
			logger.Info("Fixer Job failed", "job", job.Name, "reason", cond.Reason)
			now := metav1.Now()
			hc.Status.Phase = h2kvmv1.PhaseFailed
			hc.Status.CompletionTime = &now
			hc.Status.Message = fmt.Sprintf("Fixer Job failed: %s", cond.Message)

			meta.SetStatusCondition(&hc.Status.Conditions, metav1.Condition{
				Type:               h2kvmv1.ConditionTypeFixesComplete,
				Status:             metav1.ConditionFalse,
				Reason:             "FixesFailed",
				Message:            cond.Message,
				LastTransitionTime: now,
			})

			if updateErr := r.Status().Update(ctx, hc); updateErr != nil {
				logger.Error(updateErr, "Failed to update status")
			}
			r.Recorder.Eventf(hc, corev1.EventTypeWarning, "FixesFailed", "Fixer Job failed: %s", cond.Message)
			return ctrl.Result{}, nil
		}
	}

	// Check timeout based on the fixer Job's own start time
	jobStart := job.Status.StartTime
	if jobStart != nil {
		timeoutMinutes := int32(60)
		if hc.Spec.Conversion != nil && hc.Spec.Conversion.Timeout > 0 {
			timeoutMinutes = hc.Spec.Conversion.Timeout
		}
		elapsed := time.Since(jobStart.Time)
		if elapsed > time.Duration(timeoutMinutes)*time.Minute {
			// Delete the timed-out Job so it stops consuming resources
			if delErr := r.Delete(ctx, job); delErr != nil && !errors.IsNotFound(delErr) {
				logger.Error(delErr, "Failed to delete timed-out fixer Job")
			}
			now := metav1.Now()
			hc.Status.Phase = h2kvmv1.PhaseFailed
			hc.Status.CompletionTime = &now
			hc.Status.Message = fmt.Sprintf("Fixer Job timeout exceeded after %d minutes", timeoutMinutes)
			if updateErr := r.Status().Update(ctx, hc); updateErr != nil {
				logger.Error(updateErr, "Failed to update status")
			}
			r.Recorder.Event(hc, corev1.EventTypeWarning, "FixerTimeout", hc.Status.Message)
			return ctrl.Result{}, nil
		}
	}

	// Still running
	hc.Status.Message = fmt.Sprintf("Fixer Job %s running (active: %d)", hc.Status.FixerJobName, job.Status.Active)
	if updateErr := r.Status().Update(ctx, hc); updateErr != nil {
		logger.V(1).Info("Failed to update progress status", "error", updateErr)
	}
	return ctrl.Result{RequeueAfter: 15 * time.Second}, nil
}

// getFixerImage returns the fixer container image from env or default.
func getFixerImage() string {
	if img := os.Getenv("FIXER_IMAGE"); img != "" {
		return img
	}
	return "ghcr.io/ssahani/h2kvm-fixer:0.3.0"
}

// createFixerJob builds and creates a privileged Job that runs h2kvmctl offline fixes.
// The Job mounts the CDI DataVolume PVC and runs the fixer script against the disk image.
func (r *HyperConversionReconciler) createFixerJob(ctx context.Context, hc *h2kvmv1.HyperConversion) (*batchv1.Job, error) {
	jobName := fmt.Sprintf("%s-fixer", hc.Name)
	privileged := true
	backoffLimit := int32(0)
	ttl := int32(600) // Clean up finished Jobs after 10 minutes

	// PVC name from the DataVolume (CDI creates a PVC with the same name as the DV)
	pvcName := hc.Status.DataVolumeName
	if pvcName == "" {
		return nil, fmt.Errorf("DataVolumeName not set — cannot create fixer Job without a PVC; this usually means the DataVolume was not created in the Uploading phase — check the HyperConversion status conditions with 'kubectl describe hyperconversion %s'", hc.Name)
	}

	diskFormat := "qcow2"
	if hc.Spec.Source.Format != "" {
		validFormats := map[string]bool{"qcow2": true, "raw": true, "vmdk": true, "vhd": true, "vhdx": true}
		if !validFormats[hc.Spec.Source.Format] {
			return nil, fmt.Errorf("unsupported disk format %q (valid: qcow2, raw, vmdk, vhd, vhdx)", hc.Spec.Source.Format)
		}
		diskFormat = hc.Spec.Source.Format
	}

	job := &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      jobName,
			Namespace: hc.Namespace,
			Labels: map[string]string{
				"app":                          "h2kvm",
				"h2kvm.io/hyperconversion": hc.Name,
				"h2kvm.io/component":       "fixer",
			},
		},
		Spec: batchv1.JobSpec{
			BackoffLimit:            &backoffLimit,
			TTLSecondsAfterFinished: &ttl,
			Template: corev1.PodTemplateSpec{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						"app":                          "h2kvm",
						"h2kvm.io/hyperconversion": hc.Name,
						"h2kvm.io/component":       "fixer",
					},
				},
				Spec: corev1.PodSpec{
					RestartPolicy: corev1.RestartPolicyNever,
					Containers: []corev1.Container{
						{
							Name:  "fixer",
							Image: getFixerImage(),
							Env: []corev1.EnvVar{
								{
									Name:  "DISK_PATH",
									Value: "/data/disk.img",
								},
								{
									Name:  "DISK_FORMAT",
									Value: diskFormat,
								},
							},
							SecurityContext: &corev1.SecurityContext{
								Privileged: &privileged,
							},
							Resources: corev1.ResourceRequirements{
								Requests: corev1.ResourceList{
									corev1.ResourceCPU:    resource.MustParse("500m"),
									corev1.ResourceMemory: resource.MustParse("1Gi"),
								},
								Limits: corev1.ResourceList{
									corev1.ResourceCPU:    resource.MustParse("2"),
									corev1.ResourceMemory: resource.MustParse("4Gi"),
								},
							},
							VolumeMounts: []corev1.VolumeMount{
								{
									Name:      "disk",
									MountPath: "/data",
								},
								{
									Name:      "dev",
									MountPath: "/dev",
								},
							},
						},
					},
					Volumes: []corev1.Volume{
						{
							Name: "disk",
							VolumeSource: corev1.VolumeSource{
								PersistentVolumeClaim: &corev1.PersistentVolumeClaimVolumeSource{
									ClaimName: pvcName,
								},
							},
						},
						{
							Name: "dev",
							VolumeSource: corev1.VolumeSource{
								HostPath: &corev1.HostPathVolumeSource{
									Path: "/dev",
								},
							},
						},
					},
				},
			},
		},
	}

	// Set owner reference so the Job is cleaned up with the HyperConversion
	if err := ctrl.SetControllerReference(hc, job, r.Scheme); err != nil {
		return nil, fmt.Errorf("failed to set owner reference on fixer Job %q: %w — this is usually a controller-runtime bug; check that the HyperConversion CRD is properly installed", jobName, err)
	}

	if err := r.Create(ctx, job); err != nil {
		if errors.IsAlreadyExists(err) {
			existing := &batchv1.Job{}
			if getErr := r.Get(ctx, types.NamespacedName{Name: jobName, Namespace: hc.Namespace}, existing); getErr != nil {
				return nil, fmt.Errorf("fixer Job already exists but failed to get it: %w", getErr)
			}
			return existing, nil
		}
		return nil, fmt.Errorf("failed to create fixer Job %q in namespace %q: %w — check RBAC permissions (the operator needs batch/jobs create permission) and ensure the fixer image %q is accessible", jobName, hc.Namespace, err, getFixerImage())
	}

	return job, nil
}

// handleCreatingVM creates the KubeVirt VirtualMachine and transitions to Ready.
func (r *HyperConversionReconciler) handleCreatingVM(ctx context.Context, hc *h2kvmv1.HyperConversion) (ctrl.Result, error) {
	logger := log.FromContext(ctx)
	logger.Info("Handling CreatingVM phase", "name", hc.Name)

	// Check if VM spec is nil (no VM requested after fixes)
	if hc.Spec.VM == nil {
		now := metav1.Now()
		hc.Status.Phase = h2kvmv1.PhaseReady
		hc.Status.Progress = 100
		hc.Status.CompletionTime = &now
		hc.Status.Message = "Conversion and fixes complete (no VM creation requested)"

		if err := r.Status().Update(ctx, hc); err != nil {
			return ctrl.Result{}, err
		}

		r.Recorder.Event(hc, corev1.EventTypeNormal, "ConversionComplete", "Conversion complete, no VM requested")
		return ctrl.Result{}, nil
	}

	// Check if VM already exists (idempotency)
	if hc.Status.VirtualMachineName != "" {
		existingVM := &unstructured.Unstructured{}
		existingVM.SetGroupVersionKind(schema.GroupVersionKind{
			Group:   "kubevirt.io",
			Version: "v1",
			Kind:    "VirtualMachine",
		})
		vmKey := types.NamespacedName{
			Name:      hc.Status.VirtualMachineName,
			Namespace: hc.Namespace,
		}
		if err := r.Get(ctx, vmKey, existingVM); err == nil {
			// VM already exists, transition to Ready
			now := metav1.Now()
			hc.Status.Phase = h2kvmv1.PhaseReady
			hc.Status.Progress = 100
			hc.Status.CompletionTime = &now
			hc.Status.Message = fmt.Sprintf("VirtualMachine %s is ready", hc.Status.VirtualMachineName)

			meta.SetStatusCondition(&hc.Status.Conditions, metav1.Condition{
				Type:               h2kvmv1.ConditionTypeVMReady,
				Status:             metav1.ConditionTrue,
				Reason:             "VMCreated",
				Message:            fmt.Sprintf("VirtualMachine %s created", hc.Status.VirtualMachineName),
				LastTransitionTime: now,
			})

			_ = r.Status().Update(ctx, hc)
			return ctrl.Result{}, nil
		}
	}

	// Create the VirtualMachine
	vmCreateStart := time.Now()
	vm, err := r.createVirtualMachine(ctx, hc)
	vmCreateDuration := time.Since(vmCreateStart).Seconds()
	if err != nil {
		logger.Error(err, "Failed to create VirtualMachine")
		opmetrics.RecordKubeVirtVMCreation("failed", vmCreateDuration)
		opmetrics.RecordReconcileError("creating_vm")
		now := metav1.Now()
		hc.Status.Phase = h2kvmv1.PhaseFailed
		hc.Status.CompletionTime = &now
		hc.Status.Message = fmt.Sprintf("Failed to create VirtualMachine: %v", err)

		meta.SetStatusCondition(&hc.Status.Conditions, metav1.Condition{
			Type:               h2kvmv1.ConditionTypeVMReady,
			Status:             metav1.ConditionFalse,
			Reason:             "CreateFailed",
			Message:            err.Error(),
			LastTransitionTime: now,
		})

		_ = r.Status().Update(ctx, hc)
		r.Recorder.Eventf(hc, corev1.EventTypeWarning, "VMCreateFailed", "Failed to create VirtualMachine: %v", err)
		return ctrl.Result{}, err
	}

	opmetrics.RecordKubeVirtVMCreation("success", vmCreateDuration)

	vmName, _, _ := unstructured.NestedString(vm.Object, "metadata", "name")
	now := metav1.Now()
	hc.Status.Phase = h2kvmv1.PhaseReady
	hc.Status.Progress = 100
	hc.Status.VirtualMachineName = vmName
	hc.Status.CompletionTime = &now
	hc.Status.Message = fmt.Sprintf("VirtualMachine %s created successfully", vmName)

	meta.SetStatusCondition(&hc.Status.Conditions, metav1.Condition{
		Type:               h2kvmv1.ConditionTypeVMReady,
		Status:             metav1.ConditionTrue,
		Reason:             "VMCreated",
		Message:            fmt.Sprintf("VirtualMachine %s created", vmName),
		LastTransitionTime: now,
	})

	if err := r.Status().Update(ctx, hc); err != nil {
		return ctrl.Result{}, err
	}

	r.Recorder.Eventf(hc, corev1.EventTypeNormal, "VMCreated", "VirtualMachine %s created successfully", vmName)
	logger.Info("VirtualMachine created successfully", "vm", vmName)
	return ctrl.Result{}, nil
}

// createDataVolume builds and creates a CDI DataVolume with an HTTP source from the HyperConversion spec.
func (r *HyperConversionReconciler) createDataVolume(ctx context.Context, hc *h2kvmv1.HyperConversion) (*unstructured.Unstructured, error) {
	dvName := fmt.Sprintf("%s-dv", hc.Name)

	// Build the DataVolume source spec based on the URL scheme
	sourceSpec := map[string]interface{}{
		"http": map[string]interface{}{
			"url": hc.Spec.Source.URL,
		},
	}

	// If a secret reference is provided, include it for HTTP basic auth
	if hc.Spec.Source.SecretRef != nil {
		httpSource := sourceSpec["http"].(map[string]interface{})
		httpSource["secretRef"] = hc.Spec.Source.SecretRef.Name
	}

	// Build storage spec (local-path and similar profiles require explicit modes)
	accessMode := hc.Spec.Storage.AccessMode
	if accessMode == "" {
		accessMode = corev1.ReadWriteOnce
	}
	volumeMode := corev1.PersistentVolumeFilesystem
	if hc.Spec.Storage.VolumeMode != nil {
		volumeMode = *hc.Spec.Storage.VolumeMode
	}

	storageSpec := map[string]interface{}{
		"accessModes": []interface{}{string(accessMode)},
		"volumeMode":  string(volumeMode),
	}

	// Set storage class if specified
	if hc.Spec.Storage.StorageClass != nil {
		storageSpec["storageClassName"] = *hc.Spec.Storage.StorageClass
	}

	// Set storage size
	if hc.Spec.Storage.Size != nil {
		storageSpec["resources"] = map[string]interface{}{
			"requests": map[string]interface{}{
				"storage": hc.Spec.Storage.Size.String(),
			},
		}
	}

	// Build the DataVolume
	dv := &unstructured.Unstructured{
		Object: map[string]interface{}{
			"apiVersion": "cdi.kubevirt.io/v1beta1",
			"kind":       "DataVolume",
			"metadata": map[string]interface{}{
				"name":      dvName,
				"namespace": hc.Namespace,
				"labels": map[string]interface{}{
					"app":                              "h2kvm",
					"h2kvm.io/hyperconversion":     hc.Name,
					"h2kvm.io/hyperconversion-uid": string(hc.UID),
				},
			},
			"spec": map[string]interface{}{
				"source":  sourceSpec,
				"storage": storageSpec,
			},
		},
	}

	// Add checksum annotation if provided
	if hc.Spec.Source.Checksum != "" {
		annotations := map[string]interface{}{
			"h2kvm.io/source-checksum": hc.Spec.Source.Checksum,
		}
		_ = unstructured.SetNestedField(dv.Object, annotations, "metadata", "annotations")
	}

	// Set owner reference so the DataVolume is garbage collected with the HyperConversion
	if err := ctrl.SetControllerReference(hc, dv, r.Scheme); err != nil {
		return nil, fmt.Errorf("failed to set owner reference on DataVolume: %w", err)
	}

	// Create the DataVolume
	if err := r.Create(ctx, dv); err != nil {
		if errors.IsAlreadyExists(err) {
			// DataVolume already exists, fetch it
			existing := &unstructured.Unstructured{}
			existing.SetGroupVersionKind(schema.GroupVersionKind{
				Group:   "cdi.kubevirt.io",
				Version: "v1beta1",
				Kind:    "DataVolume",
			})
			if getErr := r.Get(ctx, types.NamespacedName{Name: dvName, Namespace: hc.Namespace}, existing); getErr != nil {
				return nil, fmt.Errorf("DataVolume already exists but failed to get it: %w", getErr)
			}
			return existing, nil
		}
		return nil, fmt.Errorf("failed to create DataVolume %q: %w — ensure CDI (Containerized Data Importer) is installed in the cluster and the source URL %q is reachable", dvName, err, hc.Spec.Source.URL)
	}

	return dv, nil
}

// createVirtualMachine builds and creates a KubeVirt VirtualMachine from the HyperConversion spec.
func (r *HyperConversionReconciler) createVirtualMachine(ctx context.Context, hc *h2kvmv1.HyperConversion) (*unstructured.Unstructured, error) {
	if hc.Spec.VM == nil {
		return nil, fmt.Errorf("VM spec is nil — add a 'vm' section to the HyperConversion spec to define CPU, memory, and network settings for the target VirtualMachine")
	}

	vmSpec := hc.Spec.VM

	// Determine VM name
	vmName := vmSpec.Name
	if vmName == "" {
		vmName = hc.Name
	}

	// Determine VM namespace
	vmNamespace := hc.Namespace

	// Build CPU configuration
	cpuSpec := map[string]interface{}{
		"cores":   int64(vmSpec.CPU.Cores),
		"sockets": int64(vmSpec.CPU.Sockets),
		"threads": int64(vmSpec.CPU.Threads),
	}

	// Build memory configuration
	memorySpec := map[string]interface{}{
		"guest": vmSpec.Memory.String(),
	}

	// Build the root disk and volume
	disks := []interface{}{
		map[string]interface{}{
			"name": "rootdisk",
			"disk": map[string]interface{}{
				"bus": "virtio",
			},
			"bootOrder": int64(1),
		},
	}

	volumes := []interface{}{
		map[string]interface{}{
			"name": "rootdisk",
			"dataVolume": map[string]interface{}{
				"name": hc.Status.DataVolumeName,
			},
		},
	}

	// Add additional disks if specified
	for _, additionalDisk := range vmSpec.AdditionalDisks {
		diskEntry := map[string]interface{}{
			"name": additionalDisk.Name,
			"disk": map[string]interface{}{
				"bus": additionalDisk.Bus,
			},
		}
		if additionalDisk.BootOrder != nil {
			diskEntry["bootOrder"] = int64(*additionalDisk.BootOrder)
		}
		disks = append(disks, diskEntry)

		// Build volume entry based on disk source type
		volumeEntry := map[string]interface{}{
			"name": additionalDisk.Name,
		}

		if additionalDisk.Source.PVCName != "" {
			volumeEntry["persistentVolumeClaim"] = map[string]interface{}{
				"claimName": additionalDisk.Source.PVCName,
			}
		} else if additionalDisk.Source.Blank {
			volumeEntry["emptyDisk"] = map[string]interface{}{}
			if additionalDisk.Size != nil {
				volumeEntry["emptyDisk"] = map[string]interface{}{
					"capacity": additionalDisk.Size.String(),
				}
			}
		}
		// URL-based additional disks would need their own DataVolumes (not handled in this phase)

		volumes = append(volumes, volumeEntry)
	}

	// Build networks and interfaces
	networks := []interface{}{}
	interfaces := []interface{}{}

	if len(vmSpec.Networks) > 0 {
		for _, net := range vmSpec.Networks {
			networkEntry := map[string]interface{}{
				"name": net.Name,
			}

			interfaceEntry := map[string]interface{}{
				"name":  net.Name,
				"model": net.Model,
			}

			if net.MacAddress != "" {
				interfaceEntry["macAddress"] = net.MacAddress
			}

			switch net.Type {
			case "pod":
				networkEntry["pod"] = map[string]interface{}{}
				interfaceEntry["masquerade"] = map[string]interface{}{}
			case "bridge":
				networkEntry["multus"] = map[string]interface{}{
					"networkName": net.NetworkName,
				}
				interfaceEntry["bridge"] = map[string]interface{}{}
			case "sriov":
				networkEntry["multus"] = map[string]interface{}{
					"networkName": net.NetworkName,
				}
				interfaceEntry["sriov"] = map[string]interface{}{}
			case "multus":
				networkEntry["multus"] = map[string]interface{}{
					"networkName": net.NetworkName,
				}
				interfaceEntry["bridge"] = map[string]interface{}{}
			}

			networks = append(networks, networkEntry)
			interfaces = append(interfaces, interfaceEntry)
		}
	} else {
		// Default pod network
		networks = append(networks, map[string]interface{}{
			"name": "default",
			"pod":  map[string]interface{}{},
		})
		interfaces = append(interfaces, map[string]interface{}{
			"name":       "default",
			"model":      "virtio",
			"masquerade": map[string]interface{}{},
		})
	}

	// Build domain spec
	domainSpec := map[string]interface{}{
		"cpu":    cpuSpec,
		"memory": memorySpec,
		"devices": map[string]interface{}{
			"disks":      disks,
			"interfaces": interfaces,
		},
	}

	// Configure firmware
	switch vmSpec.Firmware {
	case "uefi":
		domainSpec["firmware"] = map[string]interface{}{
			"bootloader": map[string]interface{}{
				"efi": map[string]interface{}{},
			},
		}
	case "uefi-secure":
		domainSpec["firmware"] = map[string]interface{}{
			"bootloader": map[string]interface{}{
				"efi": map[string]interface{}{
					"secureBoot": true,
				},
			},
		}
	default:
		// BIOS is the default, no explicit firmware config needed
	}

	// Build cloud-init volume and disk if specified
	if vmSpec.CloudInit != nil {
		cloudInitDisk := map[string]interface{}{
			"name": "cloudinit",
			"disk": map[string]interface{}{
				"bus": "virtio",
			},
		}
		disks = append(disks, cloudInitDisk)

		cloudInitVolume := map[string]interface{}{
			"name": "cloudinit",
		}

		if vmSpec.CloudInit.UserDataSecretRef != nil {
			cloudInitVolume["cloudInitNoCloud"] = map[string]interface{}{
				"userDataSecretRef": map[string]interface{}{
					"name": vmSpec.CloudInit.UserDataSecretRef.Name,
				},
			}
		} else if vmSpec.CloudInit.UserData != "" {
			cloudInitData := map[string]interface{}{
				"userData": vmSpec.CloudInit.UserData,
			}
			if vmSpec.CloudInit.NetworkData != "" {
				cloudInitData["networkData"] = vmSpec.CloudInit.NetworkData
			}
			if vmSpec.CloudInit.NetworkDataSecretRef != nil {
				cloudInitData["networkDataSecretRef"] = map[string]interface{}{
					"name": vmSpec.CloudInit.NetworkDataSecretRef.Name,
				}
			}
			cloudInitVolume["cloudInitNoCloud"] = cloudInitData
		}

		volumes = append(volumes, cloudInitVolume)

		// Update the disks in the domain spec
		_ = unstructured.SetNestedSlice(domainSpec, disks, "devices", "disks")
	}

	// Build the template spec
	templateSpec := map[string]interface{}{
		"metadata": map[string]interface{}{
			"labels": map[string]interface{}{
				"app":                              "h2kvm",
				"h2kvm.io/hyperconversion":     hc.Name,
				"h2kvm.io/hyperconversion-uid": string(hc.UID),
				"kubevirt.io/vm":                   vmName,
			},
		},
		"spec": map[string]interface{}{
			"domain":            domainSpec,
			"volumes":           volumes,
			"networks":          networks,
			"evictionStrategy":  vmSpec.EvictionStrategy,
			"terminationGracePeriodSeconds": int64(30),
		},
	}

	// Build the VirtualMachine
	vmObj := &unstructured.Unstructured{
		Object: map[string]interface{}{
			"apiVersion": "kubevirt.io/v1",
			"kind":       "VirtualMachine",
			"metadata": map[string]interface{}{
				"name":      vmName,
				"namespace": vmNamespace,
				"labels": map[string]interface{}{
					"app":                              "h2kvm",
					"h2kvm.io/hyperconversion":     hc.Name,
					"h2kvm.io/hyperconversion-uid": string(hc.UID),
				},
			},
			"spec": map[string]interface{}{
				"runStrategy": vmSpec.RunStrategy,
				"template":    templateSpec,
			},
		},
	}

	// Set owner reference
	if err := ctrl.SetControllerReference(hc, vmObj, r.Scheme); err != nil {
		return nil, fmt.Errorf("failed to set owner reference on VirtualMachine: %w", err)
	}

	// Create the VirtualMachine
	if err := r.Create(ctx, vmObj); err != nil {
		if errors.IsAlreadyExists(err) {
			existing := &unstructured.Unstructured{}
			existing.SetGroupVersionKind(schema.GroupVersionKind{
				Group:   "kubevirt.io",
				Version: "v1",
				Kind:    "VirtualMachine",
			})
			if getErr := r.Get(ctx, types.NamespacedName{Name: vmName, Namespace: vmNamespace}, existing); getErr != nil {
				return nil, fmt.Errorf("VirtualMachine already exists but failed to get it: %w", getErr)
			}
			return existing, nil
		}
		return nil, fmt.Errorf("failed to create VirtualMachine %q: %w — ensure KubeVirt is installed in the cluster ('kubectl get kubevirt -A') and the operator has RBAC permissions for kubevirt.io/virtualmachines", vmName, err)
	}

	return vmObj, nil
}

// handleDeletion handles cleanup when a HyperConversion resource is deleted.
func (r *HyperConversionReconciler) handleDeletion(ctx context.Context, hc *h2kvmv1.HyperConversion) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	if !controllerutil.ContainsFinalizer(hc, hyperConversionFinalizer) {
		return ctrl.Result{}, nil
	}

	logger.Info("Handling deletion", "name", hc.Name)

	// Clean up DataVolume if it exists
	if hc.Status.DataVolumeName != "" {
		dv := &unstructured.Unstructured{}
		dv.SetGroupVersionKind(schema.GroupVersionKind{
			Group:   "cdi.kubevirt.io",
			Version: "v1beta1",
			Kind:    "DataVolume",
		})
		dvKey := types.NamespacedName{
			Name:      hc.Status.DataVolumeName,
			Namespace: hc.Namespace,
		}
		if err := r.Get(ctx, dvKey, dv); err == nil {
			logger.Info("Deleting DataVolume", "name", hc.Status.DataVolumeName)
			if err := r.Delete(ctx, dv); err != nil && !errors.IsNotFound(err) {
				logger.Error(err, "Failed to delete DataVolume during cleanup")
			}
		} else if !errors.IsNotFound(err) {
			logger.Error(err, "Failed to get DataVolume during cleanup")
		}
	}

	// Clean up fixer Job if it exists
	if hc.Status.FixerJobName != "" {
		job := &batchv1.Job{}
		jobKey := types.NamespacedName{
			Name:      hc.Status.FixerJobName,
			Namespace: hc.Namespace,
		}
		if err := r.Get(ctx, jobKey, job); err == nil {
			logger.Info("Deleting fixer Job", "name", hc.Status.FixerJobName)
			if err := r.Delete(ctx, job); err != nil && !errors.IsNotFound(err) {
				logger.Error(err, "Failed to delete fixer Job during cleanup")
			}
		} else if !errors.IsNotFound(err) {
			logger.Error(err, "Failed to get fixer Job during cleanup")
		}
	}

	// Clean up VirtualMachine if it exists
	if hc.Status.VirtualMachineName != "" {
		vm := &unstructured.Unstructured{}
		vm.SetGroupVersionKind(schema.GroupVersionKind{
			Group:   "kubevirt.io",
			Version: "v1",
			Kind:    "VirtualMachine",
		})
		vmKey := types.NamespacedName{
			Name:      hc.Status.VirtualMachineName,
			Namespace: hc.Namespace,
		}
		if err := r.Get(ctx, vmKey, vm); err == nil {
			logger.Info("Deleting VirtualMachine", "name", hc.Status.VirtualMachineName)
			if err := r.Delete(ctx, vm); err != nil && !errors.IsNotFound(err) {
				logger.Error(err, "Failed to delete VirtualMachine during cleanup")
			}
		} else if !errors.IsNotFound(err) {
			logger.Error(err, "Failed to get VirtualMachine during cleanup")
		}
	}

	// Remove finalizer
	controllerutil.RemoveFinalizer(hc, hyperConversionFinalizer)
	if err := r.Update(ctx, hc); err != nil {
		return ctrl.Result{}, err
	}

	r.Recorder.Event(hc, corev1.EventTypeNormal, "Deleted", "HyperConversion resources cleaned up")
	logger.Info("Deletion cleanup complete", "name", hc.Name)
	return ctrl.Result{}, nil
}

// SetupWithManager sets up the controller with the Manager.
func (r *HyperConversionReconciler) SetupWithManager(mgr ctrl.Manager) error {
	// Watch DataVolumes owned by HyperConversion for event-driven reconciliation
	dvGVK := schema.GroupVersionKind{
		Group:   "cdi.kubevirt.io",
		Version: "v1beta1",
		Kind:    "DataVolume",
	}
	dvObj := &unstructured.Unstructured{}
	dvObj.SetGroupVersionKind(dvGVK)

	return ctrl.NewControllerManagedBy(mgr).
		For(&h2kvmv1.HyperConversion{}).
		Owns(&corev1.PersistentVolumeClaim{}).
		Owns(&batchv1.Job{}).
		Owns(dvObj).
		Complete(r)
}
