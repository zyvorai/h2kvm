// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"sort"
	"strings"
	"time"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
	"k8s.io/client-go/tools/clientcmd/api"
	"k8s.io/client-go/tools/portforward"
	"k8s.io/client-go/transport/spdy"
)

// GVRs for KubeVirt custom resources.
var (
	gvrKubeVirt      = schema.GroupVersionResource{Group: "kubevirt.io", Version: "v1", Resource: "kubevirts"}
	gvrCDI           = schema.GroupVersionResource{Group: "cdi.kubevirt.io", Version: "v1beta1", Resource: "cdis"}
	gvrVMI           = schema.GroupVersionResource{Group: "kubevirt.io", Version: "v1", Resource: "virtualmachineinstances"}
	gvrVM            = schema.GroupVersionResource{Group: "kubevirt.io", Version: "v1", Resource: "virtualmachines"}
	gvrVMIMigration  = schema.GroupVersionResource{Group: "kubevirt.io", Version: "v1", Resource: "virtualmachineinstancemigrations"}
)

// KubeClient wraps client-go for the TUI's Kubernetes operations.
type KubeClient struct {
	clientset   kubernetes.Interface
	dynClient   dynamic.Interface
	restConfig  *rest.Config
	rawConfig   api.Config
	contextName string
}

// KubeConfigAvailable returns whether a kubeconfig file can be found.
func KubeConfigAvailable() bool {
	rules := clientcmd.NewDefaultClientConfigLoadingRules()
	_, err := rules.Load()
	return err == nil
}

// NewKubeClient creates a KubeClient for the given context (empty string = current context).
func NewKubeClient(contextName string) (*KubeClient, error) {
	rules := clientcmd.NewDefaultClientConfigLoadingRules()
	overrides := &clientcmd.ConfigOverrides{}
	if contextName != "" {
		overrides.CurrentContext = contextName
	}

	loader := clientcmd.NewNonInteractiveDeferredLoadingClientConfig(rules, overrides)

	rawConfig, err := loader.RawConfig()
	if err != nil {
		return nil, fmt.Errorf("failed to load kubeconfig (check ~/.kube/config or KUBECONFIG env): %w", err)
	}

	restConfig, err := loader.ClientConfig()
	if err != nil {
		return nil, fmt.Errorf("invalid kubeconfig — the config may be malformed or the context may not exist: %w", err)
	}
	restConfig.Timeout = 10 * time.Second

	cs, err := kubernetes.NewForConfig(restConfig)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to Kubernetes cluster — check credentials and connectivity: %w", err)
	}

	dc, err := dynamic.NewForConfig(restConfig)
	if err != nil {
		return nil, fmt.Errorf("failed to create Kubernetes dynamic client: %w", err)
	}

	resolvedCtx := contextName
	if resolvedCtx == "" {
		resolvedCtx = rawConfig.CurrentContext
	}

	return &KubeClient{
		clientset:   cs,
		dynClient:   dc,
		restConfig:  restConfig,
		rawConfig:   rawConfig,
		contextName: resolvedCtx,
	}, nil
}

// ListContexts returns all configured kubeconfig contexts.
func (kc *KubeClient) ListContexts() []KubeContext {
	var contexts []KubeContext
	for name, ctx := range kc.rawConfig.Contexts {
		ns := ctx.Namespace
		if ns == "" {
			ns = "default"
		}
		contexts = append(contexts, KubeContext{
			Name:      name,
			Cluster:   ctx.Cluster,
			Namespace: ns,
			Current:   name == kc.rawConfig.CurrentContext,
		})
	}
	sort.Slice(contexts, func(i, j int) bool {
		return contexts[i].Name < contexts[j].Name
	})
	return contexts
}

// SwitchContext changes the current kubeconfig context and rebuilds clients.
func (kc *KubeClient) SwitchContext(name string) error {
	kc.rawConfig.CurrentContext = name
	if err := clientcmd.ModifyConfig(clientcmd.NewDefaultPathOptions(), kc.rawConfig, true); err != nil {
		return fmt.Errorf("failed to switch kubeconfig context to '%s': %w", name, err)
	}

	newClient, err := NewKubeClient(name)
	if err != nil {
		return fmt.Errorf("failed to connect after switching to context '%s': %w", name, err)
	}
	*kc = *newClient
	return nil
}

// GetKubeVirtStatus checks whether KubeVirt and CDI are installed.
func (kc *KubeClient) GetKubeVirtStatus(ctx context.Context) KubeVirtStatus {
	status := KubeVirtStatus{}

	kvList, err := kc.dynClient.Resource(gvrKubeVirt).List(ctx, metav1.ListOptions{})
	if err == nil && len(kvList.Items) > 0 {
		status.Installed = true
		ver, _, _ := unstructured.NestedString(kvList.Items[0].Object, "status", "observedKubeVirtVersion")
		status.Version = ver
	} else if err != nil && !isNoMatchError(err) {
		status.Error = fmt.Sprintf("kubevirt check: %v", err)
	}

	cdiList, err := kc.dynClient.Resource(gvrCDI).List(ctx, metav1.ListOptions{})
	if err == nil && len(cdiList.Items) > 0 {
		status.CDIInstalled = true
		ver, _, _ := unstructured.NestedString(cdiList.Items[0].Object, "status", "observedVersion")
		status.CDIVersion = ver
	}

	return status
}

// ListVMIs lists running VirtualMachineInstances.
func (kc *KubeClient) ListVMIs(ctx context.Context, namespace string) ([]KubeVirtVM, error) {
	var list *unstructured.UnstructuredList
	var err error

	if namespace == "" || namespace == "all" {
		list, err = kc.dynClient.Resource(gvrVMI).List(ctx, metav1.ListOptions{})
	} else {
		list, err = kc.dynClient.Resource(gvrVMI).Namespace(namespace).List(ctx, metav1.ListOptions{})
	}
	if err != nil {
		if isNoMatchError(err) {
			return nil, nil
		}
		return nil, err
	}

	var vms []KubeVirtVM
	for _, item := range list.Items {
		vm := KubeVirtVM{
			Name:      item.GetName(),
			Namespace: item.GetNamespace(),
		}
		vm.Status, _, _ = unstructured.NestedString(item.Object, "status", "phase")
		cores, found, _ := unstructured.NestedInt64(item.Object, "spec", "domain", "cpu", "cores")
		if found {
			vm.CPUs = int(cores)
		}
		vm.Memory, _, _ = unstructured.NestedString(item.Object, "spec", "domain", "resources", "requests", "memory")
		vm.Node, _, _ = unstructured.NestedString(item.Object, "status", "nodeName")

		// Extract first interface IP.
		ifaces, _, _ := unstructured.NestedSlice(item.Object, "status", "interfaces")
		if len(ifaces) > 0 {
			if ifMap, ok := ifaces[0].(map[string]interface{}); ok {
				if ip, ok := ifMap["ipAddress"].(string); ok {
					vm.IP = ip
				}
			}
		}

		// Guest OS info.
		vm.GuestOS, _, _ = unstructured.NestedString(item.Object, "status", "guestOSInfo", "name")

		// Conditions summary: join type names where status=="True".
		conds, _, _ := unstructured.NestedSlice(item.Object, "status", "conditions")
		var trueConditions []string
		for _, c := range conds {
			if cMap, ok := c.(map[string]interface{}); ok {
				if s, _ := cMap["status"].(string); s == "True" {
					if t, _ := cMap["type"].(string); t != "" {
						trueConditions = append(trueConditions, t)
					}
				}
			}
		}
		if len(trueConditions) > 0 {
			vm.Conditions = strings.Join(trueConditions, ", ")
		}

		// Creation time as human-readable age.
		ct := item.GetCreationTimestamp()
		if !ct.IsZero() {
			vm.CreationTime = formatAge(ct.Time)
		}

		vms = append(vms, vm)
	}
	return vms, nil
}

// ListVMs lists VirtualMachine objects (may not be running).
func (kc *KubeClient) ListVMs(ctx context.Context, namespace string) ([]KubeVirtVM, error) {
	var list *unstructured.UnstructuredList
	var err error

	if namespace == "" || namespace == "all" {
		list, err = kc.dynClient.Resource(gvrVM).List(ctx, metav1.ListOptions{})
	} else {
		list, err = kc.dynClient.Resource(gvrVM).Namespace(namespace).List(ctx, metav1.ListOptions{})
	}
	if err != nil {
		if isNoMatchError(err) {
			return nil, nil
		}
		return nil, err
	}

	var vms []KubeVirtVM
	for _, item := range list.Items {
		vm := KubeVirtVM{
			Name:      item.GetName(),
			Namespace: item.GetNamespace(),
		}
		vm.Status, _, _ = unstructured.NestedString(item.Object, "status", "printableStatus")
		cores, found, _ := unstructured.NestedInt64(item.Object, "spec", "template", "spec", "domain", "cpu", "cores")
		if found {
			vm.CPUs = int(cores)
		}
		vm.Memory, _, _ = unstructured.NestedString(item.Object, "spec", "template", "spec", "domain", "resources", "requests", "memory")
		vms = append(vms, vm)
	}
	return vms, nil
}

// ListKubeVirtVMs tries VMIs first, falls back to VMs.
func (kc *KubeClient) ListKubeVirtVMs(ctx context.Context, namespace string) ([]KubeVirtVM, error) {
	vms, err := kc.ListVMIs(ctx, namespace)
	if err == nil && len(vms) > 0 {
		return vms, nil
	}
	return kc.ListVMs(ctx, namespace)
}

// DeleteVM deletes a VirtualMachine by name and namespace.
func (kc *KubeClient) DeleteVM(ctx context.Context, name, namespace string) error {
	return kc.dynClient.Resource(gvrVM).Namespace(namespace).Delete(ctx, name, metav1.DeleteOptions{})
}

// ListPVCs returns PersistentVolumeClaims in the given namespace.
func (kc *KubeClient) ListPVCs(ctx context.Context, namespace string) ([]PVCInfo, error) {
	var list *corev1.PersistentVolumeClaimList
	var err error

	opts := metav1.ListOptions{}
	if namespace == "" || namespace == "all" {
		list, err = kc.clientset.CoreV1().PersistentVolumeClaims("").List(ctx, opts)
	} else {
		list, err = kc.clientset.CoreV1().PersistentVolumeClaims(namespace).List(ctx, opts)
	}
	if err != nil {
		return nil, fmt.Errorf("failed to list PVCs — check cluster permissions: %w", err)
	}

	var pvcs []PVCInfo
	for _, pvc := range list.Items {
		info := PVCInfo{
			Name:      pvc.Name,
			Namespace: pvc.Namespace,
			Status:    string(pvc.Status.Phase),
			Volume:    pvc.Spec.VolumeName,
		}

		if storage, ok := pvc.Status.Capacity[corev1.ResourceStorage]; ok {
			info.Capacity = storage.String()
		}
		if len(pvc.Spec.AccessModes) > 0 {
			info.AccessModes = string(pvc.Spec.AccessModes[0])
		}
		if pvc.Spec.StorageClassName != nil {
			info.StorageClass = *pvc.Spec.StorageClassName
		}
		if !pvc.CreationTimestamp.IsZero() {
			info.Age = formatAge(pvc.CreationTimestamp.Time)
		}

		pvcs = append(pvcs, info)
	}
	return pvcs, nil
}

// CreateVM creates a VirtualMachine with a containerDisk volume.
func (kc *KubeClient) CreateVM(ctx context.Context, name, namespace, image string, cpus int, memory string) error {
	vm := &unstructured.Unstructured{
		Object: map[string]interface{}{
			"apiVersion": "kubevirt.io/v1",
			"kind":       "VirtualMachine",
			"metadata": map[string]interface{}{
				"name":      name,
				"namespace": namespace,
			},
			"spec": map[string]interface{}{
				"runStrategy": "Always",
				"template": map[string]interface{}{
					"metadata": map[string]interface{}{
						"labels": map[string]interface{}{
							"kubevirt.io/domain": name,
						},
					},
					"spec": map[string]interface{}{
						"domain": map[string]interface{}{
							"cpu": map[string]interface{}{
								"cores": int64(cpus),
							},
							"devices": map[string]interface{}{
								"disks": []interface{}{
									map[string]interface{}{
										"name": "rootdisk",
										"disk": map[string]interface{}{
											"bus": "virtio",
										},
									},
								},
							},
							"resources": map[string]interface{}{
								"requests": map[string]interface{}{
									"memory": memory,
								},
							},
						},
						"volumes": []interface{}{
							map[string]interface{}{
								"name": "rootdisk",
								"containerDisk": map[string]interface{}{
									"image": image,
								},
							},
						},
					},
				},
			},
		},
	}

	_, err := kc.dynClient.Resource(gvrVM).Namespace(namespace).Create(ctx, vm, metav1.CreateOptions{})
	return err
}

// ListMigrations lists VirtualMachineInstanceMigrations.
func (kc *KubeClient) ListMigrations(ctx context.Context, namespace string) ([]MigrationInfo, error) {
	var list *unstructured.UnstructuredList
	var err error

	if namespace == "" || namespace == "all" {
		list, err = kc.dynClient.Resource(gvrVMIMigration).List(ctx, metav1.ListOptions{})
	} else {
		list, err = kc.dynClient.Resource(gvrVMIMigration).Namespace(namespace).List(ctx, metav1.ListOptions{})
	}
	if err != nil {
		if isNoMatchError(err) {
			return nil, nil
		}
		return nil, err
	}

	var migrations []MigrationInfo
	for _, item := range list.Items {
		m := MigrationInfo{
			Name:      item.GetName(),
			Namespace: item.GetNamespace(),
		}
		m.VMName, _, _ = unstructured.NestedString(item.Object, "spec", "vmiName")
		m.Phase, _, _ = unstructured.NestedString(item.Object, "status", "phase")

		ct := item.GetCreationTimestamp()
		if !ct.IsZero() {
			m.Created = formatAge(ct.Time)
		}

		migrations = append(migrations, m)
	}
	return migrations, nil
}

// PortForwardSSH sets up a port-forward to a VMI's SSH port (22) via its virt-launcher pod.
// Returns the local port, a stop channel, and any error.
func (kc *KubeClient) PortForwardSSH(ctx context.Context, name, namespace string) (int, chan struct{}, error) {
	// Find the virt-launcher pod for this VMI.
	pods, err := kc.clientset.CoreV1().Pods(namespace).List(ctx, metav1.ListOptions{
		LabelSelector: "kubevirt.io/domain=" + name,
	})
	if err != nil {
		return 0, nil, fmt.Errorf("failed to find virt-launcher pod for VM '%s' — check that the VM is running: %w", name, err)
	}
	if len(pods.Items) == 0 {
		return 0, nil, fmt.Errorf("no virt-launcher pod found for VM '%s' — the VM may not be running or may be in a different namespace", name)
	}

	podName := pods.Items[0].Name

	// Allocate a random local port.
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return 0, nil, fmt.Errorf("failed to allocate local port for SSH forwarding: %w", err)
	}
	localPort := listener.Addr().(*net.TCPAddr).Port
	listener.Close()

	// Build the port-forward request.
	req := kc.clientset.CoreV1().RESTClient().Post().
		Resource("pods").
		Namespace(namespace).
		Name(podName).
		SubResource("portforward")

	transport, upgrader, err := spdy.RoundTripperFor(kc.restConfig)
	if err != nil {
		return 0, nil, fmt.Errorf("failed to create SPDY transport for port-forward — check TLS configuration: %w", err)
	}

	dialer := spdy.NewDialer(upgrader, &http.Client{Transport: transport}, http.MethodPost, req.URL())

	stopChan := make(chan struct{}, 1)
	readyChan := make(chan struct{})

	ports := []string{fmt.Sprintf("%d:22", localPort)}
	fw, err := portforward.New(dialer, ports, stopChan, readyChan, nil, nil)
	if err != nil {
		return 0, nil, fmt.Errorf("failed to establish port-forward to VM: %w", err)
	}

	errChan := make(chan error, 1)
	// This goroutine runs until stopChan is closed (returned to caller for cleanup)
	// or the port-forward connection terminates naturally. Not a leak: the caller
	// owns stopChan and must close it to tear down the tunnel.
	go func() {
		errChan <- fw.ForwardPorts()
	}()

	select {
	case <-readyChan:
		return localPort, stopChan, nil
	case err := <-errChan:
		return 0, nil, fmt.Errorf("port-forward to VM failed: %w", err)
	case <-time.After(10 * time.Second):
		close(stopChan)
		return 0, nil, fmt.Errorf("SSH port-forward timed out after 10s — check that the VM has an SSH server and port 22 is accessible")
	}
}

// isNoMatchError returns true when the API server doesn't know the resource type.
func isNoMatchError(err error) bool {
	if errors.IsNotFound(err) {
		return true
	}
	return strings.Contains(err.Error(), "the server could not find the requested resource")
}

// formatAge returns a human-readable age string from a timestamp.
func formatAge(t time.Time) string {
	d := time.Since(t)
	switch {
	case d < time.Minute:
		return fmt.Sprintf("%ds", int(d.Seconds()))
	case d < time.Hour:
		return fmt.Sprintf("%dm", int(d.Minutes()))
	case d < 24*time.Hour:
		return fmt.Sprintf("%dh", int(d.Hours()))
	default:
		return fmt.Sprintf("%dd", int(d.Hours()/24))
	}
}
