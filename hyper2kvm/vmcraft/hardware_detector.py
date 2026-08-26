# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/hardware_detector.py
"""
Hardware detection and inventory for virtual machines.

Provides comprehensive hardware information extraction:
- CPU information (model, cores, features)
- Memory configuration
- Disk devices and partitions
- Network interfaces and MAC addresses
- PCI devices
- USB devices
- Virtual hardware detection (VMware, VirtualBox, KVM, Hyper-V)

Features:
- Parse /proc filesystem
- Parse /sys filesystem
- DMI/SMBIOS information
- lspci/lsusb equivalent data
- Virtual machine detection
- Hardware compatibility checks
"""

from __future__ import annotations

import contextlib
import re
from pathlib import Path
from typing import Any

from .base_analyzer import BaseAnalyzer


class HardwareDetector(BaseAnalyzer):
    """
    Hardware detection and inventory.

    Detects hardware configuration from offline VM disk.
    """

    def detect_hardware(self) -> dict[str, Any]:
        """
        Detect hardware configuration comprehensively.

        Returns:
            Hardware inventory dictionary
        """
        hardware: dict[str, Any] = {
            "cpu": {},
            "memory": {},
            "disks": [],
            "network": [],
            "pci_devices": [],
            "virtualization": {},
            "dmi": {},
        }

        # CPU information
        hardware["cpu"] = self._detect_cpu()

        # Memory information
        hardware["memory"] = self._detect_memory()

        # Disk devices
        hardware["disks"] = self._detect_disks()

        # Network interfaces
        hardware["network"] = self._detect_network_interfaces()

        # Virtualization detection
        hardware["virtualization"] = self._detect_virtualization()

        # DMI/SMBIOS information
        hardware["dmi"] = self._detect_dmi()

        return hardware

    def _detect_cpu(self) -> dict[str, Any]:
        """
        Detect CPU information from /proc/cpuinfo.

        Returns:
            CPU information dictionary
        """
        cpu_info: dict[str, Any] = {
            "model": None,
            "vendor": None,
            "cores": 0,
            "processors": 0,
            "features": [],
            "architecture": None,
        }

        # Note: /proc/cpuinfo is kernel-provided and won't exist in offline mount
        # Instead, check for saved cpuinfo or use alternative methods

        # Try to get CPU info from DMI
        if self.file_ops.exists("/sys/devices/virtual/dmi/id/processor_version"):
            with contextlib.suppress(Exception):
                cpu_info["model"] = self.file_ops.cat(
                    "/sys/devices/virtual/dmi/id/processor_version"
                ).strip()

        # Try to get CPU vendor from DMI
        if self.file_ops.exists("/sys/devices/virtual/dmi/id/processor_manufacturer"):
            with contextlib.suppress(Exception):
                cpu_info["vendor"] = self.file_ops.cat(
                    "/sys/devices/virtual/dmi/id/processor_manufacturer"
                ).strip()

        # Estimate cores from CPU directories in /sys
        if self.file_ops.is_dir("/sys/devices/system/cpu"):
            cpu_dirs = self.file_ops.ls("/sys/devices/system/cpu")
            cpu_count = sum(1 for d in cpu_dirs if re.match(r"^cpu\d+$", d))
            cpu_info["cores"] = cpu_count
            cpu_info["processors"] = cpu_count

        return cpu_info

    def _detect_memory(self) -> dict[str, Any]:
        """
        Detect memory configuration.

        Returns:
            Memory information dictionary
        """
        memory_info: dict[str, Any] = {
            "total_kb": None,
            "total_mb": None,
            "total_gb": None,
        }

        # Try DMI memory information
        if self.file_ops.is_dir("/sys/firmware/dmi/entries/17-0"):
            # Type 17 is Memory Device in SMBIOS
            try:
                # This is approximate - full parsing would require binary DMI parsing
                memory_info["note"] = "DMI memory information available but requires binary parsing"
            # best-effort DMI probe; memory_info is still returned without the note
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        return memory_info

    def _detect_disks(self) -> list[dict[str, Any]]:
        """
        Detect disk devices.

        Returns:
            List of disk devices
        """
        disks = []

        # Check /sys/block for block devices
        if self.file_ops.is_dir("/sys/block"):
            block_devices = self.file_ops.ls("/sys/block")

            for device in block_devices:
                # Skip loop and ram devices
                if device.startswith(("loop", "ram")):
                    continue

                disk_info: dict[str, Any] = {
                    "device": device,
                    "path": f"/dev/{device}",
                    "size": None,
                    "model": None,
                    "vendor": None,
                }

                # Try to read size
                size_path = f"/sys/block/{device}/size"
                if self.file_ops.exists(size_path):
                    try:
                        size_sectors = int(self.file_ops.cat(size_path).strip())
                        size_bytes = size_sectors * 512  # Assuming 512-byte sectors
                        disk_info["size"] = size_bytes
                        disk_info["size_gb"] = round(size_bytes / (1024**3), 2)
                    # best-effort sysfs read; disk_info is still returned without the size
                    except Exception:  # pylint: disable=broad-exception-caught
                        pass

                # Try to read model
                model_path = f"/sys/block/{device}/device/model"
                if self.file_ops.exists(model_path):
                    with contextlib.suppress(Exception):
                        disk_info["model"] = self.file_ops.cat(model_path).strip()

                # Try to read vendor
                vendor_path = f"/sys/block/{device}/device/vendor"
                if self.file_ops.exists(vendor_path):
                    with contextlib.suppress(Exception):
                        disk_info["vendor"] = self.file_ops.cat(vendor_path).strip()

                disks.append(disk_info)

        return disks

    def _detect_network_interfaces(self) -> list[dict[str, Any]]:
        """
        Detect network interfaces.

        Returns:
            List of network interfaces
        """
        interfaces = []

        # Check /sys/class/net for network interfaces
        if self.file_ops.is_dir("/sys/class/net"):
            net_devices = self.file_ops.ls("/sys/class/net")

            for device in net_devices:
                # Skip loopback
                if device == "lo":
                    continue

                iface_info: dict[str, Any] = {
                    "name": device,
                    "mac_address": None,
                    "driver": None,
                    "speed": None,
                }

                # Try to read MAC address
                mac_path = f"/sys/class/net/{device}/address"
                if self.file_ops.exists(mac_path):
                    with contextlib.suppress(Exception):
                        iface_info["mac_address"] = self.file_ops.cat(mac_path).strip()

                # Try to read driver
                driver_path = f"/sys/class/net/{device}/device/driver"
                if self.file_ops.exists(driver_path):
                    try:
                        # Driver is a symlink, get the basename
                        driver_link = self.file_ops.cat(driver_path).strip()
                        iface_info["driver"] = Path(driver_link).name
                    # best-effort sysfs read; iface_info is still returned without the driver name
                    except Exception:  # pylint: disable=broad-exception-caught
                        pass

                # Try to read speed
                speed_path = f"/sys/class/net/{device}/speed"
                if self.file_ops.exists(speed_path):
                    with contextlib.suppress(Exception):
                        iface_info["speed"] = self.file_ops.cat(speed_path).strip() + " Mbps"

                interfaces.append(iface_info)

        return interfaces

    # checks several DMI fields against several known hypervisor signatures;
    # the branches are simplest read as a flat lookup table inline
    # pylint: disable-next=too-many-branches
    def _detect_virtualization(self) -> dict[str, Any]:
        """
        Detect if running in a virtual machine and identify the hypervisor.

        Returns:
            Virtualization information
        """
        virt_info: dict[str, Any] = {
            "is_virtual": False,
            "hypervisor": None,
            "vendor": None,
            "product": None,
        }

        # Check DMI system information
        if self.file_ops.exists("/sys/devices/virtual/dmi/id/sys_vendor"):
            try:
                vendor = self.file_ops.cat("/sys/devices/virtual/dmi/id/sys_vendor").strip()
                virt_info["vendor"] = vendor

                # Identify hypervisor by vendor
                if "VMware" in vendor:
                    virt_info["is_virtual"] = True
                    virt_info["hypervisor"] = "vmware"
                elif "QEMU" in vendor or "Red Hat" in vendor:
                    virt_info["is_virtual"] = True
                    virt_info["hypervisor"] = "kvm"
                elif "Microsoft Corporation" in vendor:
                    virt_info["is_virtual"] = True
                    virt_info["hypervisor"] = "hyperv"
                elif "innotek" in vendor or "VirtualBox" in vendor:
                    virt_info["is_virtual"] = True
                    virt_info["hypervisor"] = "virtualbox"
                elif "Xen" in vendor:
                    virt_info["is_virtual"] = True
                    virt_info["hypervisor"] = "xen"

            # best-effort DMI probe; virt_info is still returned without vendor-based detection
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        # Check product name
        if self.file_ops.exists("/sys/devices/virtual/dmi/id/product_name"):
            try:
                product = self.file_ops.cat("/sys/devices/virtual/dmi/id/product_name").strip()
                virt_info["product"] = product

                # Additional hypervisor detection from product name
                if "VMware" in product:
                    virt_info["is_virtual"] = True
                    virt_info["hypervisor"] = "vmware"
                elif "VirtualBox" in product:
                    virt_info["is_virtual"] = True
                    virt_info["hypervisor"] = "virtualbox"
                elif "KVM" in product or "RHEV" in product:
                    virt_info["is_virtual"] = True
                    virt_info["hypervisor"] = "kvm"

            # best-effort DMI probe; virt_info is still returned without product-based detection
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        # Check for VMware-specific files
        if self.file_ops.exists("/usr/bin/vmware-toolbox-cmd") or self.file_ops.exists(
            "/usr/sbin/vmware-guestd"
        ):
            virt_info["is_virtual"] = True
            virt_info["hypervisor"] = "vmware"

        # Check for VirtualBox-specific files
        if self.file_ops.exists("/usr/sbin/VBoxService"):
            virt_info["is_virtual"] = True
            virt_info["hypervisor"] = "virtualbox"

        return virt_info

    def _detect_dmi(self) -> dict[str, Any]:
        """
        Detect DMI/SMBIOS information.

        Returns:
            DMI information dictionary
        """
        dmi_info: dict[str, Any] = {
            "bios_vendor": None,
            "bios_version": None,
            "bios_date": None,
            "system_manufacturer": None,
            "system_product": None,
            "system_version": None,
            "system_serial": None,
            "system_uuid": None,
            "baseboard_manufacturer": None,
            "baseboard_product": None,
            "baseboard_version": None,
            "chassis_type": None,
        }

        # Map of DMI files to keys
        dmi_mappings = {
            "bios_vendor": "/sys/devices/virtual/dmi/id/bios_vendor",
            "bios_version": "/sys/devices/virtual/dmi/id/bios_version",
            "bios_date": "/sys/devices/virtual/dmi/id/bios_date",
            "system_manufacturer": "/sys/devices/virtual/dmi/id/sys_vendor",
            "system_product": "/sys/devices/virtual/dmi/id/product_name",
            "system_version": "/sys/devices/virtual/dmi/id/product_version",
            "system_serial": "/sys/devices/virtual/dmi/id/product_serial",
            "system_uuid": "/sys/devices/virtual/dmi/id/product_uuid",
            "baseboard_manufacturer": "/sys/devices/virtual/dmi/id/board_vendor",
            "baseboard_product": "/sys/devices/virtual/dmi/id/board_name",
            "baseboard_version": "/sys/devices/virtual/dmi/id/board_version",
            "chassis_type": "/sys/devices/virtual/dmi/id/chassis_type",
        }

        for key, path in dmi_mappings.items():
            if self.file_ops.exists(path):
                with contextlib.suppress(Exception):
                    dmi_info[key] = self.file_ops.cat(path).strip()

        return dmi_info

    def is_virtual_machine(self, hardware: dict[str, Any]) -> bool:
        """Check if the system is a virtual machine."""
        return hardware.get("virtualization", {}).get("is_virtual", False)

    def get_hypervisor(self, hardware: dict[str, Any]) -> str | None:
        """Get the hypervisor type."""
        return hardware.get("virtualization", {}).get("hypervisor")

    def get_total_memory_mb(self, hardware: dict[str, Any]) -> float | None:
        """Get total memory in MB."""
        return hardware.get("memory", {}).get("total_mb")

    def get_disk_count(self, hardware: dict[str, Any]) -> int:
        """Get number of disk devices."""
        return len(hardware.get("disks", []))

    def get_network_interface_count(self, hardware: dict[str, Any]) -> int:
        """Get number of network interfaces."""
        return len(hardware.get("network", []))

    def get_hardware_summary(self, hardware: dict[str, Any]) -> dict[str, Any]:
        """
        Get hardware summary.

        Returns:
            Summary dictionary
        """
        cpu_info = hardware.get("cpu", {})
        virt_info = hardware.get("virtualization", {})
        dmi_info = hardware.get("dmi", {})

        return {
            "is_virtual": virt_info.get("is_virtual", False),
            "hypervisor": virt_info.get("hypervisor"),
            "cpu_model": cpu_info.get("model"),
            "cpu_cores": cpu_info.get("cores", 0),
            "disk_count": self.get_disk_count(hardware),
            "network_interfaces": self.get_network_interface_count(hardware),
            "manufacturer": dmi_info.get("system_manufacturer"),
            "product": dmi_info.get("system_product"),
        }
