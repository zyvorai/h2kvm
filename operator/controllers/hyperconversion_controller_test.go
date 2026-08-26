// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package controllers

import (
	"context"
	"time"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/types"

	h2kvmv1alpha1 "github.com/h2kvm/operator/api/v1alpha1"
)

var _ = Describe("HyperConversion Controller", func() {
	const (
		timeout  = time.Second * 30
		interval = time.Millisecond * 250
	)

	Context("TestHyperConversionReconcile_Pending", func() {
		It("Should create a DataVolume when a HyperConversion resource is created", func() {
			ctx := context.Background()
			hcName := "test-hc-pending"
			ns := "default"
			storageSize := resource.MustParse("20Gi")

			hc := &h2kvmv1alpha1.HyperConversion{
				ObjectMeta: metav1.ObjectMeta{
					Name:      hcName,
					Namespace: ns,
				},
				Spec: h2kvmv1alpha1.HyperConversionSpec{
					Source: h2kvmv1alpha1.SourceSpec{
						URL:    "https://example.com/disk.qcow2",
						Format: "qcow2",
					},
					Storage: h2kvmv1alpha1.StorageSpec{
						Size:       &storageSize,
						AccessMode: "ReadWriteOnce",
					},
				},
			}

			Expect(k8sClient.Create(ctx, hc)).Should(Succeed())

			// The controller should transition to Uploading and create a DataVolume.
			// Verify that the status reports the DataVolume name.
			Eventually(func(g Gomega) {
				fetched := &h2kvmv1alpha1.HyperConversion{}
				g.Expect(k8sClient.Get(ctx, types.NamespacedName{Name: hcName, Namespace: ns}, fetched)).To(Succeed())
				g.Expect(fetched.Status.DataVolumeName).ToNot(BeEmpty())
				g.Expect(fetched.Status.Phase).To(Equal(h2kvmv1alpha1.PhaseUploading))
			}, timeout, interval).Should(Succeed())

			// Verify the DataVolume object was created in the API server.
			dv := &unstructured.Unstructured{}
			dv.SetGroupVersionKind(schema.GroupVersionKind{
				Group:   "cdi.kubevirt.io",
				Version: "v1beta1",
				Kind:    "DataVolume",
			})
			dvName := hcName + "-dv"
			Eventually(func() error {
				return k8sClient.Get(ctx, types.NamespacedName{Name: dvName, Namespace: ns}, dv)
			}, timeout, interval).Should(Succeed())

			// Verify DataVolume labels
			labels := dv.GetLabels()
			Expect(labels).To(HaveKeyWithValue("h2kvm.io/hyperconversion", hcName))

			// Cleanup
			Expect(k8sClient.Delete(ctx, hc)).Should(Succeed())
		})
	})

	Context("TestHyperConversionReconcile_Ready", func() {
		It("Should create a VirtualMachine when the DataVolume import succeeds", func() {
			ctx := context.Background()
			hcName := "test-hc-ready"
			ns := "default"
			storageSize := resource.MustParse("20Gi")
			vmMemory := resource.MustParse("4Gi")

			hc := &h2kvmv1alpha1.HyperConversion{
				ObjectMeta: metav1.ObjectMeta{
					Name:      hcName,
					Namespace: ns,
				},
				Spec: h2kvmv1alpha1.HyperConversionSpec{
					Source: h2kvmv1alpha1.SourceSpec{
						URL:    "https://example.com/disk.qcow2",
						Format: "qcow2",
					},
					Storage: h2kvmv1alpha1.StorageSpec{
						Size:       &storageSize,
						AccessMode: "ReadWriteOnce",
					},
					VM: &h2kvmv1alpha1.VMSpec{
						CPU: h2kvmv1alpha1.CPUSpec{
							Cores:   2,
							Sockets: 1,
							Threads: 1,
						},
						Memory:      vmMemory,
						Firmware:    "bios",
						RunStrategy: "Always",
					},
				},
			}

			Expect(k8sClient.Create(ctx, hc)).Should(Succeed())

			// Wait for the DataVolume to be created and the status to be Uploading.
			dvName := hcName + "-dv"
			Eventually(func(g Gomega) {
				fetched := &h2kvmv1alpha1.HyperConversion{}
				g.Expect(k8sClient.Get(ctx, types.NamespacedName{Name: hcName, Namespace: ns}, fetched)).To(Succeed())
				g.Expect(fetched.Status.DataVolumeName).To(Equal(dvName))
			}, timeout, interval).Should(Succeed())

			// Simulate the DataVolume completing by setting its status.phase to Succeeded.
			dv := &unstructured.Unstructured{}
			dv.SetGroupVersionKind(schema.GroupVersionKind{
				Group:   "cdi.kubevirt.io",
				Version: "v1beta1",
				Kind:    "DataVolume",
			})
			Eventually(func() error {
				return k8sClient.Get(ctx, types.NamespacedName{Name: dvName, Namespace: ns}, dv)
			}, timeout, interval).Should(Succeed())

			// Patch the DataVolume status to Succeeded.
			dv.Object["status"] = map[string]interface{}{
				"phase": "Succeeded",
			}
			Expect(k8sClient.Status().Update(ctx, dv)).Should(Succeed())

			// The controller should detect Succeeded, transition through Converting
			// and CreatingVM, and eventually reach Ready with a VirtualMachine created.
			Eventually(func(g Gomega) {
				fetched := &h2kvmv1alpha1.HyperConversion{}
				g.Expect(k8sClient.Get(ctx, types.NamespacedName{Name: hcName, Namespace: ns}, fetched)).To(Succeed())
				g.Expect(fetched.Status.Phase).To(Equal(h2kvmv1alpha1.PhaseReady))
				g.Expect(fetched.Status.VirtualMachineName).ToNot(BeEmpty())
				g.Expect(fetched.Status.Progress).To(Equal(int32(100)))
			}, timeout, interval).Should(Succeed())

			// Verify the VirtualMachine object was created.
			vm := &unstructured.Unstructured{}
			vm.SetGroupVersionKind(schema.GroupVersionKind{
				Group:   "kubevirt.io",
				Version: "v1",
				Kind:    "VirtualMachine",
			})
			Eventually(func() error {
				return k8sClient.Get(ctx, types.NamespacedName{Name: hcName, Namespace: ns}, vm)
			}, timeout, interval).Should(Succeed())

			vmLabels := vm.GetLabels()
			Expect(vmLabels).To(HaveKeyWithValue("h2kvm.io/hyperconversion", hcName))

			// Cleanup
			Expect(k8sClient.Delete(ctx, hc)).Should(Succeed())
		})
	})

	Context("TestHyperConversionReconcile_Deletion", func() {
		It("Should clean up DataVolume and VirtualMachine on deletion", func() {
			ctx := context.Background()
			hcName := "test-hc-deletion"
			ns := "default"
			storageSize := resource.MustParse("20Gi")
			vmMemory := resource.MustParse("4Gi")

			hc := &h2kvmv1alpha1.HyperConversion{
				ObjectMeta: metav1.ObjectMeta{
					Name:      hcName,
					Namespace: ns,
				},
				Spec: h2kvmv1alpha1.HyperConversionSpec{
					Source: h2kvmv1alpha1.SourceSpec{
						URL:    "https://example.com/disk.qcow2",
						Format: "qcow2",
					},
					Storage: h2kvmv1alpha1.StorageSpec{
						Size:       &storageSize,
						AccessMode: "ReadWriteOnce",
					},
					VM: &h2kvmv1alpha1.VMSpec{
						CPU: h2kvmv1alpha1.CPUSpec{
							Cores:   2,
							Sockets: 1,
							Threads: 1,
						},
						Memory:      vmMemory,
						Firmware:    "bios",
						RunStrategy: "Always",
					},
				},
			}

			Expect(k8sClient.Create(ctx, hc)).Should(Succeed())

			// Wait for DataVolume creation.
			dvName := hcName + "-dv"
			Eventually(func(g Gomega) {
				fetched := &h2kvmv1alpha1.HyperConversion{}
				g.Expect(k8sClient.Get(ctx, types.NamespacedName{Name: hcName, Namespace: ns}, fetched)).To(Succeed())
				g.Expect(fetched.Status.DataVolumeName).To(Equal(dvName))
			}, timeout, interval).Should(Succeed())

			// Simulate DataVolume success.
			dv := &unstructured.Unstructured{}
			dv.SetGroupVersionKind(schema.GroupVersionKind{
				Group:   "cdi.kubevirt.io",
				Version: "v1beta1",
				Kind:    "DataVolume",
			})
			Eventually(func() error {
				return k8sClient.Get(ctx, types.NamespacedName{Name: dvName, Namespace: ns}, dv)
			}, timeout, interval).Should(Succeed())

			dv.Object["status"] = map[string]interface{}{
				"phase": "Succeeded",
			}
			Expect(k8sClient.Status().Update(ctx, dv)).Should(Succeed())

			// Wait until Ready with VM created.
			Eventually(func(g Gomega) {
				fetched := &h2kvmv1alpha1.HyperConversion{}
				g.Expect(k8sClient.Get(ctx, types.NamespacedName{Name: hcName, Namespace: ns}, fetched)).To(Succeed())
				g.Expect(fetched.Status.Phase).To(Equal(h2kvmv1alpha1.PhaseReady))
				g.Expect(fetched.Status.VirtualMachineName).ToNot(BeEmpty())
			}, timeout, interval).Should(Succeed())

			// Now delete the HyperConversion resource.
			Expect(k8sClient.Delete(ctx, hc)).Should(Succeed())

			// The finalizer should clean up the DataVolume and VirtualMachine,
			// then remove the finalizer so the HyperConversion is fully deleted.
			Eventually(func() bool {
				err := k8sClient.Get(ctx, types.NamespacedName{Name: hcName, Namespace: ns}, &h2kvmv1alpha1.HyperConversion{})
				return err != nil // Should be NotFound
			}, timeout, interval).Should(BeTrue())

			// Verify the DataVolume was deleted.
			deletedDV := &unstructured.Unstructured{}
			deletedDV.SetGroupVersionKind(schema.GroupVersionKind{
				Group:   "cdi.kubevirt.io",
				Version: "v1beta1",
				Kind:    "DataVolume",
			})
			Eventually(func() bool {
				err := k8sClient.Get(ctx, types.NamespacedName{Name: dvName, Namespace: ns}, deletedDV)
				return err != nil
			}, timeout, interval).Should(BeTrue())

			// Verify the VirtualMachine was deleted.
			deletedVM := &unstructured.Unstructured{}
			deletedVM.SetGroupVersionKind(schema.GroupVersionKind{
				Group:   "kubevirt.io",
				Version: "v1",
				Kind:    "VirtualMachine",
			})
			Eventually(func() bool {
				err := k8sClient.Get(ctx, types.NamespacedName{Name: hcName, Namespace: ns}, deletedVM)
				return err != nil
			}, timeout, interval).Should(BeTrue())
		})
	})
})
