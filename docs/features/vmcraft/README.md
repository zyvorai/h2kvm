# VMCraft Documentation

VMCraft is the core VM manipulation library.

## Documentation

### Core Guides

- **[Complete Guide](complete-guide.md)** - Comprehensive VMCraft guide
- **[Advanced Features](advanced-features.md)** - Advanced VMCraft features
- **[OS Detection](os-detection.md)** - Operating system detection
- **[Windows Support](windows-support.md)** - Windows VM support

### Specialized Guides (v9.1+)

- **[Performance Guide](../vmcraft-performance-guide.md)** - Performance optimization and tuning
  - Parallel mount operations (2-3x speedup)
  - Intelligent caching (30-40% reduction in system calls)
  - NBD retry logic and mount fallback strategies
  - Benchmarks and troubleshooting

- **[Partition Management](../vmcraft-partition-management.md)** - Partition table manipulation
  - GPT and MBR partition tables
  - Creating, deleting, and modifying partitions
  - MBR to GPT conversion
  - Enterprise partition layouts

- **[LVM Guide](../vmcraft-lvm-guide.md)** - Logical Volume Manager
  - LVM stack creation (PV, VG, LV)
  - Volume resizing and management
  - Multi-disk spanning
  - Enterprise storage layouts

- **[Augeas Configuration Management](../vmcraft-augeas-guide.md)** - Programmatic config editing
  - fstab, SSH, systemd-networkd manipulation
  - Batch configuration updates
  - Security hardening workflows
  - 100+ supported file formats

## See Also

- [VMCraft API Reference](../../reference/api/vmcraft.md)
- [VMCraft Examples](../../../examples/)
