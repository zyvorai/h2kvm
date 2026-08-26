// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package controllers

import (
	"context"
	"time"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"

	hyper2kvmv1 "github.com/hyper2kvm/operator/api/v1"
)

var _ = Describe("Validation Controller", func() {
	const (
		timeout  = time.Second * 10
		interval = time.Millisecond * 250
	)

	Context("When creating a Validation resource", func() {
		It("Should create a validation pod", func() {
			ctx := context.Background()

			validation := &hyper2kvmv1.Validation{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-validation",
					Namespace: "default",
				},
				Spec: hyper2kvmv1.ValidationSpec{
					Image:  "/images/test.qcow2",
					Memory: 2048,
					CPUs:   2,
				},
			}

			Expect(k8sClient.Create(ctx, validation)).Should(Succeed())

			// Check that validation pod is created
			Eventually(func() bool {
				podList := &corev1.PodList{}
				err := k8sClient.List(ctx, podList)
				if err != nil {
					return false
				}
				for _, pod := range podList.Items {
					if pod.Labels["hyper2kvm.io/validation"] == "test-validation" {
						return true
					}
				}
				return false
			}, timeout, interval).Should(BeTrue())

			// Cleanup
			Expect(k8sClient.Delete(ctx, validation)).Should(Succeed())
		})

		It("Should update status to Running", func() {
			ctx := context.Background()

			validation := &hyper2kvmv1.Validation{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-validation-status",
					Namespace: "default",
				},
				Spec: hyper2kvmv1.ValidationSpec{
					Image:  "/images/test.qcow2",
					Memory: 2048,
					CPUs:   2,
				},
			}

			Expect(k8sClient.Create(ctx, validation)).Should(Succeed())

			// Check that status is updated to Running
			Eventually(func() hyper2kvmv1.ValidationPhase {
				v := &hyper2kvmv1.Validation{}
				err := k8sClient.Get(ctx, types.NamespacedName{
					Name:      "test-validation-status",
					Namespace: "default",
				}, v)
				if err != nil {
					return ""
				}
				return v.Status.Phase
			}, timeout, interval).Should(Equal(hyper2kvmv1.PhaseRunning))

			// Cleanup
			Expect(k8sClient.Delete(ctx, validation)).Should(Succeed())
		})

		It("Should handle timeout correctly", func() {
			ctx := context.Background()

			validation := &hyper2kvmv1.Validation{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-validation-timeout",
					Namespace: "default",
				},
				Spec: hyper2kvmv1.ValidationSpec{
					Image:   "/images/test.qcow2",
					Memory:  2048,
					CPUs:    2,
					Timeout: 1, // Very short timeout
				},
			}

			Expect(k8sClient.Create(ctx, validation)).Should(Succeed())

			// Eventually should timeout and fail
			Eventually(func() hyper2kvmv1.ValidationPhase {
				v := &hyper2kvmv1.Validation{}
				err := k8sClient.Get(ctx, types.NamespacedName{
					Name:      "test-validation-timeout",
					Namespace: "default",
				}, v)
				if err != nil {
					return ""
				}
				return v.Status.Phase
			}, timeout*2, interval).Should(Equal(hyper2kvmv1.PhaseFailed))

			// Cleanup
			Expect(k8sClient.Delete(ctx, validation)).Should(Succeed())
		})

		It("Should clean up validation pod on completion", func() {
			ctx := context.Background()

			validation := &hyper2kvmv1.Validation{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-validation-cleanup",
					Namespace: "default",
				},
				Spec: hyper2kvmv1.ValidationSpec{
					Image:  "/images/test.qcow2",
					Memory: 2048,
					CPUs:   2,
				},
			}

			Expect(k8sClient.Create(ctx, validation)).Should(Succeed())

			// Wait for validation to complete/fail
			time.Sleep(time.Second * 5)

			// Simulate pod completion
			podList := &corev1.PodList{}
			err := k8sClient.List(ctx, podList)
			Expect(err).NotTo(HaveOccurred())

			for _, pod := range podList.Items {
				if pod.Labels["hyper2kvm.io/validation"] == "test-validation-cleanup" {
					pod.Status.Phase = corev1.PodSucceeded
					Expect(k8sClient.Status().Update(ctx, &pod)).Should(Succeed())
				}
			}

			// Check that pod is cleaned up
			Eventually(func() int {
				podList := &corev1.PodList{}
				err := k8sClient.List(ctx, podList)
				if err != nil {
					return -1
				}
				count := 0
				for _, pod := range podList.Items {
					if pod.Labels["hyper2kvm.io/validation"] == "test-validation-cleanup" {
						count++
					}
				}
				return count
			}, timeout, interval).Should(Equal(0))

			// Cleanup
			Expect(k8sClient.Delete(ctx, validation)).Should(Succeed())
		})
	})

	Context("When validation succeeds", func() {
		It("Should update checks and mark as validated", func() {
			ctx := context.Background()

			validation := &hyper2kvmv1.Validation{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-validation-success",
					Namespace: "default",
				},
				Spec: hyper2kvmv1.ValidationSpec{
					Image:  "/images/test.qcow2",
					Memory: 2048,
					CPUs:   2,
				},
			}

			Expect(k8sClient.Create(ctx, validation)).Should(Succeed())

			// Simulate successful validation
			time.Sleep(time.Second * 2)

			podList := &corev1.PodList{}
			err := k8sClient.List(ctx, podList)
			Expect(err).NotTo(HaveOccurred())

			for _, pod := range podList.Items {
				if pod.Labels["hyper2kvm.io/validation"] == "test-validation-success" {
					pod.Status.Phase = corev1.PodSucceeded
					Expect(k8sClient.Status().Update(ctx, &pod)).Should(Succeed())
				}
			}

			// Check that validation is marked as successful
			Eventually(func() bool {
				v := &hyper2kvmv1.Validation{}
				err := k8sClient.Get(ctx, types.NamespacedName{
					Name:      "test-validation-success",
					Namespace: "default",
				}, v)
				if err != nil {
					return false
				}
				return v.Status.Validated
			}, timeout, interval).Should(BeTrue())

			// Cleanup
			Expect(k8sClient.Delete(ctx, validation)).Should(Succeed())
		})
	})

	Context("When KubeVirt VM creation is requested", func() {
		It("Should create KubeVirt VM after successful validation", func() {
			ctx := context.Background()

			validation := &hyper2kvmv1.Validation{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-validation-kubevirt",
					Namespace: "default",
				},
				Spec: hyper2kvmv1.ValidationSpec{
					Image:            "test-pvc-disk",
					Memory:           2048,
					CPUs:             2,
					CreateKubeVirtVM: true,
				},
			}

			Expect(k8sClient.Create(ctx, validation)).Should(Succeed())

			// Simulate successful validation
			time.Sleep(time.Second * 2)

			podList := &corev1.PodList{}
			err := k8sClient.List(ctx, podList)
			Expect(err).NotTo(HaveOccurred())

			for _, pod := range podList.Items {
				if pod.Labels["hyper2kvm.io/validation"] == "test-validation-kubevirt" {
					pod.Status.Phase = corev1.PodSucceeded
					Expect(k8sClient.Status().Update(ctx, &pod)).Should(Succeed())
				}
			}

			// Check that KubeVirt VM name is set in status
			Eventually(func() string {
				v := &hyper2kvmv1.Validation{}
				err := k8sClient.Get(ctx, types.NamespacedName{
					Name:      "test-validation-kubevirt",
					Namespace: "default",
				}, v)
				if err != nil {
					return ""
				}
				return v.Status.KubeVirtVM
			}, timeout, interval).ShouldNot(BeEmpty())

			// Cleanup
			Expect(k8sClient.Delete(ctx, validation)).Should(Succeed())
		})
	})
})
