# h2kvm Roadmap

This directory contains detailed implementation plans for future h2kvm features and enhancements.

## Active Roadmaps

### [Advanced Windows Support](./Advanced-Windows-Support.md)
**Status**: Draft - Pending Implementation
**Target**: v0.3.0 or v1.0.0
**Estimated Effort**: 23-32 engineering days

Comprehensive Windows migration enhancements for enterprise environments:

#### Phase 1: Core Enterprise Features (2-3 weeks)
- ✅ License key extraction and preservation (OEM, Retail, MAK, KMS)
- ✅ Automated license reactivation with slmgr.vbs integration
- ✅ Active Directory domain rejoin automation
- ✅ Offline domain join support (djoin.exe)
- ✅ KMS server configuration updates

#### Phase 2: Application Compatibility (2-3 weeks)
- ✅ Hardware-dependent application detection
- ✅ License server identification (FlexLM, RLM, Sentinel HASP)
- ✅ SQL Server instance detection and reconfiguration
- ✅ Application compatibility report generation
- ✅ Mitigation guidance for detected issues

#### Phase 3: Performance Optimization (1 week)
- ✅ VirtIO balloon driver auto-configuration
- ✅ TRIM/discard enablement for SSDs
- ✅ MSI interrupt configuration for lower latency
- ✅ Performance validation scripts

#### Phase 4: Cleanup & Polish (1 week)
- ✅ Hyper-V enlightenments removal (for Hyper-V → KVM migrations)
- ✅ AD computer object cleanup scripts
- ✅ Comprehensive documentation
- ✅ Migration best practices guide

**Business Value**: Very High - Windows dominates enterprise VM environments
**Implementation Complexity**: High - Enterprise features require extensive testing

---

## Future Roadmap Ideas

### 1. Enhanced Linux Support
**Target**: v0.3.0
**Estimated Effort**: 2-3 weeks

- Advanced systemd service management
- UEFI Secure Boot handling
- Custom initramfs generation
- Network bonding and bridging migration
- SELinux/AppArmor policy preservation
- LVM snapshot-based migrations

### 2. Cloud Provider Integrations
**Target**: v0.4.0
**Estimated Effort**: 4-6 weeks

- AWS Direct Connect for low-latency transfers
- Azure ExpressRoute integration
- GCP interconnect support
- Multi-cloud batch migrations
- Cloud-native backup integration (AWS Backup, Azure Backup)
- Cost estimation and optimization

### 3. Advanced Networking
**Target**: v0.5.0
**Estimated Effort**: 3-4 weeks

- SR-IOV network configuration
- DPDK-enabled VirtIO
- Complex VLAN topologies
- Network QoS preservation
- Multi-NIC bonding configurations
- IPv6 full support

### 4. Kubernetes Operator Enhancements
**Target**: v0.3.0
**Estimated Effort**: 2-3 weeks

- GitOps integration (FluxCD, ArgoCD)
- Horizontal Pod Autoscaling based on queue depth
- Multi-tenancy with namespace isolation
- Custom Resource Definitions for complex workflows
- Prometheus metrics and Grafana dashboards
- Admission webhooks for validation

### 5. Performance & Scalability
**Target**: v0.4.0
**Estimated Effort**: 3-4 weeks

- Parallel disk conversion pipeline
- Delta migration support (incremental sync)
- Compression optimization (zstd tuning)
- Memory-mapped I/O for large VMs
- GPU passthrough preparation
- NUMA topology preservation

### 6. Security & Compliance
**Target**: v0.5.0
**Estimated Effort**: 2-3 weeks

- FIPS 140-2 compliance mode
- Encryption at rest for staged artifacts
- LUKS key escrow integration
- Audit logging with SIEM integration
- SOC 2 compliance features
- PCI-DSS migration workflows

### 7. Advanced Validation
**Target**: v0.3.0
**Estimated Effort**: 2 weeks

- Automated smoke testing (boot validation)
- Application-level health checks
- Performance regression detection
- Filesystem integrity verification
- Network connectivity validation
- Database connection testing (SQL Server, Oracle, PostgreSQL)

### 8. Disaster Recovery
**Target**: v0.4.0
**Estimated Effort**: 2-3 weeks

- Checkpoint/snapshot support during migration
- Automated rollback on failure
- Point-in-time recovery
- Multi-site replication
- Disaster recovery orchestration
- RTO/RPO monitoring

### 9. Multi-Hypervisor Support Expansion
**Target**: v0.5.0
**Estimated Effort**: 4-5 weeks

- XenServer/Citrix Hypervisor support
- Proxmox VE integration
- Oracle VM VirtualBox support
- Nutanix AHV support
- OpenStack integration enhancements
- VMware Cloud Foundation compatibility

### 10. Enterprise Integrations
**Target**: v0.6.0
**Estimated Effort**: 3-4 weeks

- ServiceNow integration (change management)
- Jira ticket automation
- Slack/Teams notifications
- Webhook-based event streaming
- CMDB synchronization
- License management system integration

---

## Prioritization Criteria

Features are prioritized based on:

1. **Business Value**: Impact on user productivity and enterprise adoption
2. **User Demand**: Community requests and customer feedback
3. **Implementation Complexity**: Development effort and testing requirements
4. **Dependencies**: Required infrastructure or external integrations
5. **Strategic Fit**: Alignment with product vision and roadmap

## Contributing to the Roadmap

We welcome community input on roadmap priorities:

- 🐛 **Report Issues**: [GitHub Issues](https://github.com/anthropics/h2kvm/issues)
- 💡 **Feature Requests**: [GitHub Discussions](https://github.com/anthropics/h2kvm/discussions)
- 🗳️ **Vote on Features**: Upvote issues/discussions you care about
- 📝 **Submit Proposals**: Create detailed feature proposals in `docs/roadmap/`

## Versioning Strategy

- **v0.x.x**: Active development, breaking changes possible
- **v1.0.0**: Production-ready, stable API, backward compatibility guarantees
- **v1.x.x**: Minor releases with new features, backward compatible
- **v2.0.0+**: Major releases with breaking changes, migration guides provided

---

**Last Updated**: 2026-03-29
**Roadmap Maintainers**: h2kvm core team
