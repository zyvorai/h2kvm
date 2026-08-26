// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package domain

import "fmt"

// ValidateDeployExclusive rejects migration configs that combine incompatible deploy targets.
func (c *MigrationConfig) ValidateDeployExclusive() error {
	if c == nil {
		return nil
	}
	libvirtOn := c.EmitDomainXML || c.VirshDefine || c.LibvirtTest
	if c.DeployK8s && c.DeployOpenStack {
		return fmt.Errorf("deploy_k8s and deploy_openstack are mutually exclusive")
	}
	if c.DeployK8s && libvirtOn {
		return fmt.Errorf(
			"deploy_k8s cannot be combined with emit_domain_xml, virsh_define, or libvirt_test",
		)
	}
	if c.DeployOpenStack && libvirtOn {
		return fmt.Errorf(
			"deploy_openstack cannot be combined with emit_domain_xml, virsh_define, or libvirt_test",
		)
	}
	return nil
}
