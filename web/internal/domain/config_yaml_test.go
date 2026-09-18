// Copyright (c) 2026 ZyvorAI Labs Private Limited.
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
// https://zyvor.dev · info@zyvor.dev

package domain

import (
	"reflect"
	"testing"

	"gopkg.in/yaml.v3"
)

// h2kvmctl reads its YAML keys as argparse destinations, so the generated
// config must use those names, not the names the dashboard's JSON uses.
func marshalToMap(t *testing.T, cfg MigrationConfig) map[string]any {
	t.Helper()
	b, err := yaml.Marshal(&cfg)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	out := map[string]any{}
	if err := yaml.Unmarshal(b, &out); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	return out
}

func TestMigrationConfigYAMLUsesH2kvmctlKeys(t *testing.T) {
	got := marshalToMap(t, MigrationConfig{
		Command:         "vsphere",
		VSphereHost:     "vc.example.com",
		VSphereUsername: "admin",
		VSpherePassword: "secret",
		VSphereInsecure: true,
		VMPath:          "web-01",
		Datacenter:      "dc1",
		Namespace:       "vms",
		ClevisUnlock:    true,
	})

	want := map[string]any{
		"command":       "vsphere",
		"vcenter":       "vc.example.com",
		"vc_user":       "admin",
		"vc_password":   "secret",
		"vc_insecure":   true,
		"vs_vm":         "web-01",
		"vs_datacenter": "dc1",
		"k8s_namespace": "vms",
		"luks_clevis":   true,
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("yaml keys:\n got  %v\n want %v", got, want)
	}
}

func TestMigrationConfigYAMLAzureVMNameBecomesList(t *testing.T) {
	got := marshalToMap(t, MigrationConfig{
		Command:             "azure",
		AzureSubscriptionID: "sub-1",
		AzureResourceGroup:  "rg",
		AzureVMName:         "vm1",
	})

	want := map[string]any{
		"command":              "azure",
		"azure_subscription":   "sub-1",
		"azure_resource_group": "rg",
		"azure_vm_names":       []any{"vm1"},
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("yaml keys:\n got  %v\n want %v", got, want)
	}
}

func TestMigrationConfigYAMLKeepsExplicitAzureVMNames(t *testing.T) {
	got := marshalToMap(t, MigrationConfig{
		Command:      "azure",
		AzureVMName:  "ignored",
		AzureVMNames: []string{"a", "b"},
	})
	if !reflect.DeepEqual(got["azure_vm_names"], []any{"a", "b"}) {
		t.Fatalf("azure_vm_names = %v", got["azure_vm_names"])
	}
}

// Fields h2kvmctl has no option for must not reach the YAML, and the JSON
// keys the dashboard sends must be unchanged.
func TestMigrationConfigDropsOptionsWithoutACounterpart(t *testing.T) {
	got := marshalToMap(t, MigrationConfig{Command: "local", UpdateGrub: true, WinTPM: true})
	for _, k := range []string{"update_grub", "win_tpm", "no_grub"} {
		if _, ok := got[k]; ok {
			t.Errorf("unexpected key %q in generated yaml", k)
		}
	}
}
