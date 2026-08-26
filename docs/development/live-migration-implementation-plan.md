# Live Migration - Implementation Plan (HyperSDK Integration)

**Feature**: Live Migration with HyperSDK Integration
**Priority**: P0 (High Priority)
**Timeline**: 4-6 months (reduced from 6-8 due to HyperSDK)
**Complexity**: Medium-High (HyperSDK handles heavy lifting)
**Business Impact**: Very High (enables 24/7 production migrations)

---

## Executive Summary

**Key Insight**: HyperSDK already provides multi-cloud provider support and live migration primitives.

**h2kvm's Role**: Orchestrate live migration workflow and integrate with existing offline fixer pipeline.

**Architecture**:
```
┌─────────────────────────────────────────────────────────┐
│                     h2kvm                           │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Live Migration Orchestrator                    │   │
│  │  - Pre-migration analysis                        │   │
│  │  - Live migration decision engine               │   │
│  │  - Fallback to offline migration                │   │
│  └─────────────────────────────────────────────────┘   │
│                         │                               │
│                         ▼                               │
│  ┌─────────────────────────────────────────────────┐   │
│  │  HyperSDK Integration Layer                     │   │
│  │  - Provider abstraction (VMware, Hyper-V, etc.) │   │
│  │  - Live migration API calls                     │   │
│  │  - Progress monitoring                          │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                     HyperSDK                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Multi-Cloud Provider Support                   │   │
│  │  - VMware vSphere API (vMotion)                 │   │
│  │  - Hyper-V Live Migration API                   │   │
│  │  - libvirt/KVM migration API                    │   │
│  │  - Cloud provider APIs (AWS, Azure, GCP)        │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## h2kvm Focus Areas

Since HyperSDK handles the provider layer, h2kvm focuses on:

### 1. **Live Migration Decision Engine** (2 weeks)

Determine if VM is suitable for live migration or needs offline approach.

```python
# h2kvm/migration/live_migration_analyzer.py

class LiveMigrationAnalyzer:
    """Analyzes VMs to determine if live migration is feasible."""

    def can_migrate_live(self, vm_info: dict) -> dict:
        """
        Analyze if VM can be migrated live.

        Returns:
            {
                'feasible': True/False,
                'method': 'live' | 'offline' | 'hybrid',
                'estimated_downtime': 2.5,  # seconds
                'blockers': [],
                'recommendations': []
            }
        """

        blockers = []
        recommendations = []

        # Check 1: VM is powered on
        if not vm_info.get('power_state') == 'on':
            blockers.append("VM must be powered on for live migration")

        # Check 2: OS supports live migration
        os_type = vm_info.get('os_type', '').lower()
        if 'windows' in os_type:
            # Windows Server 2012+ supports live migration well
            windows_version = self._parse_windows_version(vm_info.get('os_version', ''))
            if windows_version < 2012:
                blockers.append(f"Windows version {windows_version} may not support live migration reliably")

        # Check 3: Memory size (very large VMs take longer)
        memory_gb = vm_info.get('memory_mb', 0) / 1024
        if memory_gb > 128:
            recommendations.append(f"Large memory ({memory_gb}GB) may increase downtime to 10-30s")

        # Check 4: Network bandwidth
        if not self._check_network_bandwidth():
            recommendations.append("Low network bandwidth detected - live migration may be slow")

        # Check 5: Storage type
        if vm_info.get('storage_type') == 'local':
            blockers.append("Local storage requires storage migration (use hybrid approach)")

        # Check 6: Snapshots
        if vm_info.get('has_snapshots'):
            blockers.append("VM has snapshots - must consolidate before live migration")

        # Determine feasibility
        feasible = len(blockers) == 0

        # Estimate downtime
        downtime = self._estimate_downtime(vm_info)

        return {
            'feasible': feasible,
            'method': 'live' if feasible else 'offline',
            'estimated_downtime': downtime,
            'blockers': blockers,
            'recommendations': recommendations
        }

    def _estimate_downtime(self, vm_info: dict) -> float:
        """
        Estimate live migration downtime in seconds.

        Factors:
        - Memory size (more memory = more sync time)
        - Memory change rate (high churn = more iterations)
        - Network bandwidth
        - CPU load
        """

        memory_gb = vm_info.get('memory_mb', 0) / 1024

        # Base downtime (switchover time)
        base_downtime = 0.5  # 500ms minimum

        # Memory factor (larger VMs need more switchover time)
        memory_factor = memory_gb * 0.01  # ~10ms per GB

        # Network factor
        bandwidth_mbps = vm_info.get('network_bandwidth', 1000)  # Default 1Gbps
        if bandwidth_mbps < 1000:
            network_factor = 1.0  # Slower network = +1s
        else:
            network_factor = 0.0

        total_downtime = base_downtime + memory_factor + network_factor

        return round(total_downtime, 2)
```

---

### 2. **HyperSDK Integration** (3-4 weeks)

Integrate with HyperSDK's provider abstraction.

```python
# h2kvm/migration/live_migration_manager.py

from hypersdk import HyperSDK  # Assuming HyperSDK is installed

class LiveMigrationManager:
    """Manages live migration orchestration via HyperSDK."""

    def __init__(self, source_provider: str, target_provider: str = "kvm"):
        """
        Initialize live migration manager.

        Args:
            source_provider: Source hypervisor (vmware, hyperv, kvm, aws, azure, gcp)
            target_provider: Target (usually kvm)
        """
        self.hypersdk = HyperSDK()
        self.source_provider = source_provider
        self.target_provider = target_provider

    async def migrate_live(self,
                           vm_id: str,
                           target_host: str,
                           pre_migration_fixes: bool = True,
                           fallback_to_offline: bool = True) -> dict:
        """
        Perform live migration with h2kvm enhancements.

        Workflow:
        1. Pre-migration analysis (h2kvm)
        2. Optional pre-migration fixes (h2kvm)
        3. Live migration (HyperSDK)
        4. Post-migration validation (h2kvm)
        5. Fallback to offline if live fails

        Args:
            vm_id: Source VM identifier
            target_host: Target KVM host
            pre_migration_fixes: Apply offline fixes before live migration
            fallback_to_offline: Automatically fallback to offline migration if live fails

        Returns:
            Migration result with status, downtime, errors
        """

        result = {
            'success': False,
            'method': 'live',
            'downtime_seconds': None,
            'errors': []
        }

        try:
            # Step 1: Analyze VM for live migration feasibility
            logger.info("🔍 Analyzing VM for live migration...")
            analyzer = LiveMigrationAnalyzer()
            vm_info = await self.hypersdk.get_vm_info(self.source_provider, vm_id)
            analysis = analyzer.can_migrate_live(vm_info)

            if not analysis['feasible']:
                logger.warning(f"⚠ Live migration not feasible: {analysis['blockers']}")

                if fallback_to_offline:
                    logger.info("📴 Falling back to offline migration...")
                    return await self._fallback_to_offline(vm_id, target_host)
                else:
                    result['errors'] = analysis['blockers']
                    return result

            logger.info(f"✓ Live migration feasible. Estimated downtime: {analysis['estimated_downtime']}s")

            # Step 2: Pre-migration fixes (optional)
            if pre_migration_fixes:
                logger.info("🔧 Applying pre-migration fixes...")
                await self._apply_pre_migration_fixes(vm_id)

            # Step 3: Initiate live migration via HyperSDK
            logger.info("🚀 Starting live migration...")
            migration_task = await self.hypersdk.migrate_live(
                source_provider=self.source_provider,
                target_provider=self.target_provider,
                vm_id=vm_id,
                target_host=target_host,
                options={
                    'max_downtime_ms': int(analysis['estimated_downtime'] * 1000),
                    'bandwidth_limit_mbps': 1000,  # 1 Gbps
                    'compression': True,
                    'auto_converge': True  # Throttle VM if migration isn't converging
                }
            )

            # Step 4: Monitor progress
            async for progress in self.hypersdk.monitor_migration(migration_task.id):
                logger.info(f"⏳ Migration progress: {progress['percent']}% "
                          f"(transferred: {progress['transferred_mb']}MB, "
                          f"remaining: {progress['remaining_mb']}MB)")

                if progress['status'] == 'completed':
                    logger.info("✅ Live migration completed!")
                    result['success'] = True
                    result['downtime_seconds'] = progress.get('actual_downtime_ms', 0) / 1000
                    break

                elif progress['status'] == 'failed':
                    logger.error(f"❌ Live migration failed: {progress.get('error')}")
                    result['errors'].append(progress.get('error'))

                    if fallback_to_offline:
                        logger.info("📴 Falling back to offline migration...")
                        return await self._fallback_to_offline(vm_id, target_host)

                    break

            # Step 5: Post-migration validation
            if result['success']:
                logger.info("🔍 Running post-migration validation...")
                await self._post_migration_validation(vm_id, target_host)

        except Exception as e:
            logger.error(f"❌ Live migration error: {e}")
            result['errors'].append(str(e))

            if fallback_to_offline:
                logger.info("📴 Falling back to offline migration...")
                return await self._fallback_to_offline(vm_id, target_host)

        return result

    async def _apply_pre_migration_fixes(self, vm_id: str):
        """
        Apply lightweight fixes before live migration.

        These are non-invasive fixes that don't require downtime:
        - Install VirtIO drivers (in background)
        - Update network config (doesn't affect running VM)
        - Prepare boot loader (doesn't require reboot yet)
        """

        logger.info("Installing VirtIO drivers in background...")
        # Use hypersdk to install drivers while VM is running

        logger.info("Preparing network configuration...")
        # Stage network config changes (will apply after migration)

    async def _fallback_to_offline(self, vm_id: str, target_host: str) -> dict:
        """
        Fallback to traditional offline migration.

        Uses h2kvm's existing offline migration pipeline.
        """

        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info("  FALLBACK: Offline Migration")
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # Power off VM
        logger.info("Powering off VM...")
        await self.hypersdk.power_off_vm(self.source_provider, vm_id)

        # Use existing h2kvm offline migration
        from h2kvm.migration.offline_migration import OfflineMigrationManager

        offline_mgr = OfflineMigrationManager()
        result = await offline_mgr.migrate(vm_id, target_host)

        result['method'] = 'offline_fallback'
        return result

    async def _post_migration_validation(self, vm_id: str, target_host: str):
        """
        Validate VM after live migration.

        Checks:
        - VM is running on target
        - Network connectivity
        - Disk I/O
        - Application health
        """

        logger.info("Checking VM status on target...")
        target_vm = await self.hypersdk.get_vm_info(self.target_provider, vm_id)

        if target_vm['power_state'] != 'on':
            raise Exception("VM is not running on target!")

        logger.info("✓ VM is running on target")

        # Test network connectivity
        logger.info("Testing network connectivity...")
        # Ping test, port checks, etc.

        logger.info("✓ Post-migration validation passed")
```

---

### 3. **Hybrid Migration Mode** (2-3 weeks)

Combine live migration (for memory/CPU state) with offline fixes (for disk modifications).

```python
class HybridMigrationManager:
    """
    Hybrid migration: Live migrate first, then apply offline fixes.

    Use case: Migrate production VM with minimal downtime, then apply
    complex bootloader/driver fixes during a short maintenance window.
    """

    async def migrate_hybrid(self, vm_id: str, target_host: str) -> dict:
        """
        Hybrid migration workflow:

        1. Live migrate VM to target KVM (downtime: 1-5 seconds)
        2. VM runs on target (users can continue working)
        3. Schedule maintenance window (e.g., overnight)
        4. During maintenance: Power off, apply offline fixes, reboot
        5. Total user-facing downtime: 1-5 seconds (live) + 10-15 min (maintenance)

        vs Pure Offline Migration:
        - Pure offline: 30-60 minutes downtime
        - Hybrid: 1-5 seconds initial downtime + scheduled 15 min maintenance

        Benefits:
        - Move VM to target immediately (urgent migrations)
        - Apply complex fixes during planned maintenance
        - Minimize business disruption
        """

        result = {}

        # Phase 1: Live migration (minimal downtime)
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info("  PHASE 1: Live Migration")
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        live_mgr = LiveMigrationManager(source_provider="vmware", target_provider="kvm")
        live_result = await live_mgr.migrate_live(
            vm_id=vm_id,
            target_host=target_host,
            pre_migration_fixes=False,  # Skip fixes for speed
            fallback_to_offline=False
        )

        if not live_result['success']:
            logger.error("Live migration failed, cannot proceed with hybrid mode")
            return live_result

        logger.info(f"✅ Phase 1 complete. Downtime: {live_result['downtime_seconds']}s")
        logger.info("VM is now running on target KVM host")

        # Phase 2: Schedule offline fixes
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info("  PHASE 2: Scheduled Offline Fixes")
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        logger.info("Offline fixes will be applied during next maintenance window")
        logger.info("To apply fixes now, run: h2kvm fix --vm-id {vm_id}")

        # Create maintenance task
        maintenance_task = {
            'vm_id': vm_id,
            'target_host': target_host,
            'fixes_required': [
                'initramfs_regen',
                'grub_fixes',
                'virtio_drivers',
                'fstab_fixes'
            ],
            'estimated_downtime': '10-15 minutes',
            'scheduled_time': None  # User will schedule
        }

        result['live_migration'] = live_result
        result['maintenance_task'] = maintenance_task
        result['method'] = 'hybrid'

        return result
```

---

### 4. **CLI Integration** (1-2 weeks)

Add live migration commands to h2kvm CLI.

```bash
# Live migration commands

# Analyze if VM can be migrated live
h2kvm analyze-live --vm-id vm-123 --provider vmware

# Perform live migration
h2kvm migrate --vm-id vm-123 --target-host kvm01.company.local --mode live

# Hybrid migration (live + scheduled offline fixes)
h2kvm migrate --vm-id vm-123 --target-host kvm01.company.local --mode hybrid

# Fallback to offline if live fails
h2kvm migrate --vm-id vm-123 --target-host kvm01.company.local --mode live --fallback-offline

# Monitor live migration progress
h2kvm status --migration-id mig-456
```

**YAML Configuration**:

```yaml
# config/live-migration-example.yaml

cmd: live  # New command type

# Source VM (HyperSDK provider)
source_provider: vmware
vm_id: vm-123
source_host: vcenter.company.local

# Target
target_provider: kvm
target_host: kvm01.company.local

# Live migration options
live_migration:
  enabled: true
  max_downtime_ms: 5000  # 5 seconds max acceptable downtime
  bandwidth_limit_mbps: 1000  # 1 Gbps
  compression: true
  auto_converge: true
  fallback_to_offline: true  # Auto-fallback if live fails

# Pre-migration fixes (optional, applied before live migration)
pre_migration_fixes:
  install_virtio_drivers: true  # Install while VM is running
  prepare_network_config: true

# Post-migration fixes (applied after live migration, may require brief reboot)
post_migration_fixes:
  initramfs_regen: true
  grub_fixes: true
  fstab_fixes: true

# Hybrid mode (live migrate, then schedule offline fixes)
hybrid_mode:
  enabled: false
  maintenance_window: "2026-02-01T02:00:00Z"  # Optional scheduled time
```

---

## Integration with Existing Pipeline

Live migration integrates seamlessly with existing h2kvm features:

```python
# h2kvm/migration/orchestrator.py

class MigrationOrchestrator:
    """Unified orchestrator for all migration modes."""

    async def migrate(self, config: dict) -> dict:
        """
        Intelligent migration dispatcher.

        Automatically chooses best migration method based on:
        - VM state (powered on/off)
        - Configuration preferences
        - Feasibility analysis
        """

        mode = config.get('cmd', 'auto')

        if mode == 'live':
            # User explicitly requested live migration
            mgr = LiveMigrationManager(
                source_provider=config['source_provider'],
                target_provider=config.get('target_provider', 'kvm')
            )
            return await mgr.migrate_live(
                vm_id=config['vm_id'],
                target_host=config['target_host'],
                fallback_to_offline=config.get('live_migration', {}).get('fallback_to_offline', True)
            )

        elif mode == 'hybrid':
            # Hybrid mode
            mgr = HybridMigrationManager()
            return await mgr.migrate_hybrid(
                vm_id=config['vm_id'],
                target_host=config['target_host']
            )

        elif mode == 'offline' or mode == 'local':
            # Traditional offline migration
            mgr = OfflineMigrationManager()
            return await mgr.migrate(config)

        elif mode == 'auto':
            # Intelligent decision
            analyzer = LiveMigrationAnalyzer()
            vm_info = await hypersdk.get_vm_info(config['source_provider'], config['vm_id'])
            analysis = analyzer.can_migrate_live(vm_info)

            if analysis['feasible'] and vm_info['power_state'] == 'on':
                logger.info("✓ Auto-selected: Live Migration")
                return await self.migrate({**config, 'cmd': 'live'})
            else:
                logger.info("✓ Auto-selected: Offline Migration")
                return await self.migrate({**config, 'cmd': 'offline'})
```

---

## Testing Strategy

### Test Scenarios

| Scenario | Source | Target | Expected Result |
|----------|--------|--------|-----------------|
| Simple live migration | VMware (running VM) | KVM | Success, <5s downtime |
| Live migration with fallback | VMware (complex VM) | KVM | Fallback to offline |
| Hybrid migration | VMware (production) | KVM | Live + scheduled fixes |
| Offline migration | VMware (powered off) | KVM | Traditional offline |
| Auto-detect mode | VMware (running) | KVM | Auto-select live |

---

## Success Metrics

- ✅ <5s downtime for 90% of live migrations
- ✅ 100% fallback success rate (no data loss)
- ✅ 95% hybrid migration adoption for production VMs
- ✅ Zero manual intervention for standard scenarios

---

## HyperSDK Dependencies

Required HyperSDK features:
- ✅ Multi-provider support (VMware, Hyper-V, KVM, AWS, Azure, GCP)
- ✅ Live migration API (async/await interface)
- ✅ Progress monitoring
- ✅ VM power state control
- ✅ Network bandwidth control

---

## Future Enhancements

1. **Storage live migration**: Migrate storage while VM runs (DRBD, NBD)
2. **Multi-hop migration**: VMware → temporary KVM → final KVM (for complex scenarios)
3. **Live migration scheduling**: Calendar integration for planned migrations
4. **AI-powered optimization**: Learn optimal migration parameters from history
