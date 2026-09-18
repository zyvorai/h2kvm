// Copyright (c) 2026 ZyvorAI Labs Private Limited.
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
// https://zyvor.dev · info@zyvor.dev


package domain

import "testing"

func TestValidateDeployExclusive(t *testing.T) {
	t.Parallel()

	c := &MigrationConfig{DeployK8s: true, DeployOpenStack: true}
	if err := c.ValidateDeployExclusive(); err == nil {
		t.Fatal("expected error for k8s+openstack")
	}

	c = &MigrationConfig{DeployOpenStack: true, EmitDomainXML: true}
	if err := c.ValidateDeployExclusive(); err == nil {
		t.Fatal("expected error for openstack+libvirt")
	}

	c = &MigrationConfig{DeployOpenStack: true}
	if err := c.ValidateDeployExclusive(); err != nil {
		t.Fatalf("expected ok: %v", err)
	}
}
