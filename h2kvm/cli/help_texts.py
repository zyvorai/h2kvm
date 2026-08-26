# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
CLI help text and configuration examples.

Pure help/documentation text used by argparse epilog rendering.
"""

# h2kvm/cli/help_texts.py
from __future__ import annotations

YAML_EXAMPLE = r"""# h2kvm configuration examples (YAML)
#
# Run:
# sudo ./h2kvm.py --config example.yaml <command>
#
# Merge multiple configs (later overrides earlier):
# sudo ./h2kvm.py --config base.yaml --config overrides.yaml <command>
#
# NOTE: Required CLI args can come from YAML because h2kvm uses a 2-phase parse:
# Phase 0: reads only --config / logging
# Phase 1: loads+merges YAML and applies defaults to argparse
# Phase 2: parses full args (so required args can be satisfied by config)
#
# Common keys (apply to ALL modes)
# output_dir: ./out
# workdir: ./out/work
# dry_run: false # preview changes, don't modify guest/outputs
# verbose: 0|1|2 # or CLI: -v/-vv
# log_file: ./h2kvm.log
# report: report.md # relative to output_dir if not absolute
# checksum: true # SHA256 output
# enable_recovery: true # checkpoints for long ops
# parallel_processing: true # batch mode concurrency
#
# Fix policy:
# fstab_mode: stabilize-all # stabilize-all | bypath-only | noop
# print_fstab: true
# no_backup: false # keep backups in guest unless explicitly disabled
# no_grub: false # set true to skip grub root=/device.map cleanup
# regen_initramfs: true # best-effort initramfs+grub regen
# initramfs_add_drivers: "nvme e1000e" # additional drivers for initramfs (Linux)
# remove_vmware_tools: true # linux guests only
# enable_rdp: true # Windows: firstboot enables RDP (TermService, firewall, registry); default true when guest_os=windows
#
# Convert policy:
# flatten: true
# flatten_format: qcow2 # qcow2|raw
# to_output: final.qcow2
# out_format: qcow2 # qcow2|raw|vdi
# compress: true
# compress_level: 6 # 1-9
# resize: +10G # enlarge only: +10G or set total: 50G
#
# Linux driver injection (initramfs customization):
# initramfs_add_drivers: "nvme e1000e mlx5_core" # space-separated module names
# # OR use YAML list:
# initramfs_add_drivers:
#   - nvme
#   - e1000e
#   - mlx5_core
#   - ixgbe
# # Default includes: virtio, virtio_ring, virtio_blk, virtio_scsi, virtio_net,
# # virtio_pci, nvme, ahci, sd_mod, dm_mod, dm_crypt, xts
# # Use initramfs_add_drivers to add hardware-specific drivers like:
# #   - Network: e1000e, ixgbe, mlx5_core, i40e, bnx2x
# #   - Storage: megaraid_sas, mpt3sas, hpsa, aacraid
# #   - RAID: md_mod, raid0, raid1, raid10, raid456
# #   - Filesystem: ext4, xfs, btrfs
#
# Windows extras:
# virtio_drivers_dir: /path/to/virtio-win.iso  # override; auto-discovered at /var/lib/h2kvm/virtio-win.iso
# # Install the standard ISO: ./scripts/install-deps.sh --virtio-win
#
# Windows driver mapping + PNP IDs (YAML-driven; recommended)
# Motivation:
#   - Different vendors may use different PNP IDs for VirtIO devices.
#   - New Windows versions appear; mapping should be data, not code.
#
# Recommended keys (your orchestrator can map these into WindowsVirtioPlan):
# windows_virtio:
#   # Defaults: if omitted, code may use safe defaults (Win11 favored).
#   default_os_bucket: win11
#
#   # OS bucket selection can be based on build numbers (not major/minor).
#   # Example structure (working theory; keep flexible):
#   os_buckets:
#     win11:
#       min_build: 22000
#     win10:
#       min_build: 10240
#       max_build: 21999
#     win2019:
#       min_build: 17763
#       max_build: 17763
#
#   # List of driver "roles" that h2kvm knows how to apply.
#   # Each role points to where the INF(s) live under virtio-win tree and
#   # which PNP IDs should be written into CriticalDeviceDatabase.
#   roles:
#     storage_virtio_scsi:
#       inf_globs: ["vioscsi\\**\\*.inf"]
#       pnp_ids:
#         - "PCI\\VEN_1AF4&DEV_1004"   # Red Hat vioscsi (example)
#     storage_virtio_blk:
#       inf_globs: ["viostor\\**\\*.inf"]
#       pnp_ids:
#         - "PCI\\VEN_1AF4&DEV_1001"   # Red Hat viostor (example)
#     net_virtio:
#       inf_globs: ["NetKVM\\**\\*.inf"]
#       pnp_ids:
#         - "PCI\\VEN_1AF4&DEV_1000"   # Red Hat NetKVM (example)
#
#   # Optional: vendor overrides (OEMs sometimes ship custom IDs)
#   vendors:
#     acme:
#       roles:
#         net_virtio:
#           pnp_ids:
#             - "PCI\\VEN_1AF4&DEV_0001&SUBSYS_12345678"
#
# Windows network configuration (YAML-driven; recommended)
# You already support:
#   - win_net_override: path to JSON file on host
#   - win_net_json: inline JSON string
#
# Add a YAML-native variant for sanity and systemd embedding:
# win_net:                      # YAML object (preferred)
#   schema: 1
#   mode: dhcp                  # dhcp | static
#   dhcp:
#     dns_servers: ["10.0.0.53"]
#   static:
#     address: "192.168.1.50/24"
#     gateway: "192.168.1.1"
#     dns_servers: ["1.1.1.1", "8.8.8.8"]
#
# Your orchestrator can materialize this YAML object to JSON under workdir and
# set args.win_net_override automatically (similar to win_net_json behavior).
#
# Internal converters and fixers:
# Note: h2kvm uses only internal migration tools
#
# Tests:
# libvirt_test: true
# qemu_test: true
# vm_name: my-test-vm
# memory: 4096
# vcpus: 4
# uefi: true
# timeout: 90
# keep_domain: false
# headless: true
#
# Libvirt: emit domain XML / deploy into libvirt (define/start)
# This section is additive. If the orchestrator doesn't recognize these keys yet,
# it will ignore them.
#
# Emit domain XML after pipeline:
# emit_domain_xml: true        # write <vm_name>.xml (relative to output_dir unless absolute)
# libvirt_xml_dir: ./libvirt   # directory for emitted XML (optional)
# libvirt_xml_name: null       # override filename (optional)
#
# Deploy actions:
# virsh_define: true           # virsh define <xml>
# virsh_start: false           # virsh start <vm_name> (optional)
# virsh_autostart: false       # virsh autostart <vm_name> (optional)
#
# Storage safety (recommended when defining):
# copy_to_libvirt_images: true
# libvirt_images_dir: /var/lib/libvirt/images
# overwrite_disk_copy: false
#
# Template selection hint:
# guest_os: linux              # linux | windows
#
# Domain knobs used by emitter:
# machine: q35                 # q35|pc
# disk_bus: virtio
# disk_dev: vda
# disk_cache: none             # or null to omit
# net_model: virtio
# libvirt_network: default
#
# Graphics knobs (ignored if headless:true => graphics=none):
# graphics: spice              # none|vnc|spice
# graphics_listen: 127.0.0.1
# video: virtio                # virtio|vga|qxl
# usb_tablet: true
#
# Linux clock policy:
# clock: utc                   # utc|localtime
#
# UEFI knobs (used only if uefi:true):
# ovmf_code: /usr/share/edk2/ovmf/OVMF_CODE.fd
# nvram_vars: null
# ovmf_vars_template: null
#
# Optional: attach cloud-init seed ISO in the emitted XML:
# cloudinit_iso: null
# cloudinit_seed_iso: null
#
# Windows-only emission knobs (ignored unless guest_os=windows):
# win_stage: bootstrap          # bootstrap | final
# win_driver_iso: null          # path to virtio-win.iso
# virtio_win_iso: null          # alias
# driver_iso: null              # alias
# win_localtime_clock: true
# win_hyperv: true
#
# Example: "deploy" after conversion:
# emit_domain_xml: true
# virsh_define: true
# virsh_start: true
# copy_to_libvirt_images: true
#
# 1) LOCAL (offline local VMDK conversion)
# Basic local mode config: fix + flatten + convert to qcow2 (Linux guest)
# command: local
# vmdk: /path/to/vm.vmdk
# output_dir: ./out
# workdir: ./out/work
# flatten: true
# flatten_format: qcow2
# to_output: vm-fixed.qcow2
# out_format: qcow2
# compress: true
# compress_level: 6
# fstab_mode: stabilize-all
# print_fstab: true
# regen_initramfs: true
# remove_vmware_tools: true
# checksum: true
# report: local-report.md
# verbose: 1
#
# --- Local: "minimal safe" dry-run preview (no changes performed) ---
# command: local
# vmdk: /path/to/vm.vmdk
# dry_run: true
# print_fstab: true
# fstab_mode: stabilize-all
# regen_initramfs: false
# flatten: false
# verbose: 2
#
# --- Local: Windows virtio injection + BCD scan + convert ---
# # Note: virtio_drivers_dir is optional if virtio-win.iso is at /var/lib/h2kvm/virtio-win.iso
# command: local
# vmdk: /path/to/windows-vm.vmdk
# virtio_drivers_dir: /path/to/virtio-win  # override; omit to use standard path
# windows_virtio:                    # YAML-driven driver/PnP mapping (see top)
#   default_os_bucket: win11
# flatten: true
# to_output: windows-kvm.qcow2
# out_format: qcow2
# compress: true
# checksum: true
# report: windows-report.md
# verbose: 2
#
# --- Local: disk growth + cloud-init injection (Linux) ---
# command: local
# vmdk: /path/to/linux-vm.vmdk
# resize: +20G
# cloud_init_config: /path/to/cloud-config.yaml
# fstab_mode: stabilize-all
# regen_initramfs: true
# flatten: true
# to_output: linux-grown.qcow2
# out_format: qcow2
# compress: true
#
# --- Local: produce RAW image for dd or imaging pipelines ---
# command: local
# vmdk: /path/to/vm.vmdk
# flatten: true
# flatten_format: raw
# to_output: vm.raw
# out_format: raw
# compress: false
#
# --- Local: batch multiple VMs (shared defaults + per-VM overrides) ---
# vms:
# - vmdk: /path/to/vm1.vmdk
#   to_output: vm1.qcow2
#   resize: +10G
# - vmdk: /path/to/vm2.vmdk
#   to_output: vm2.qcow2
#   remove_vmware_tools: false
# flatten: true
# out_format: qcow2
# compress: true
# parallel_processing: true
# enable_recovery: true
#
# Run:
# sudo ./h2kvm.py --config batch.yaml local
#
# 1b) VHD (Azure/Hyper-V style disks: plain .vhd OR .vhd.tar.gz)
# command: vhd
# vhd: ./fedora-azure-43.0.x86_64.vhd
# output_dir: ./out
# flatten: true
# flatten_format: qcow2
# to_output: fedora-azure-43.0.qcow2
# out_format: qcow2
# compress: true
# compress_level: 6
# fstab_mode: stabilize-all
# print_fstab: true
# regen_initramfs: true
# remove_vmware_tools: false
# qemu_test: true
# headless: true
# uefi: true
# memory: 2048
# vcpus: 2
# timeout: 90
# checksum: true
# report: fedora-azure-report.md
# verbose: 1
#
# tarball containing VHD:
# command: vhd
# vhd: ./fedora-azure-43.x86_64.vhd.tar.gz
# output_dir: ./out
# flatten: true
# flatten_format: qcow2
# to_output: fedora-azure-43.0.qcow2
# out_format: qcow2
# compress: true
# compress_level: 6
# regen_initramfs: true
# qemu_test: true
# headless: true
# uefi: true
#
# 1c) AMI / Generic Cloud Image Tarball (tar/tar.gz/tgz/tar.xz)
# command: ami
# ami: ./some-linux-cloud-image.tar.gz
# output_dir: ./out
# flatten: true
# flatten_format: qcow2
# to_output: cloud-image-fixed.qcow2
# out_format: qcow2
# compress: true
# compress_level: 6
# fstab_mode: stabilize-all
# print_fstab: true
# regen_initramfs: true
# checksum: true
# report: cloud-image-report.md
# verbose: 1
#
# tar-in-tar:
# command: ami
# ami: ./vendor-bundle.tar.gz
# extract_nested_tar: true
# convert_payload_to_qcow2: true
# verbose: 2
#
# 2) LIVE-FIX (apply fixes to a running VM via SSH)
# command: live-fix
# host: 192.168.1.100
# user: root
# port: 22
# sudo: true
# print_fstab: true
# fstab_mode: stabilize-all
# regen_initramfs: true
# remove_vmware_tools: true
# no_backup: false
# verbose: 2
#
# --- Live-fix: custom identity and SSH options, skip grub updates ---
# command: live-fix
# host: vm.example.com
# user: admin
# identity: ~/.ssh/custom_key
# ssh_opt:
# - "-o StrictHostKeyChecking=no"
# - "-o ConnectTimeout=30"
# sudo: true
# no_grub: true
# fstab_mode: bypath-only
# dry_run: true
# log_file: live-fix.log
#
# 3) FETCH-AND-FIX (fetch from ESXi over SSH/SCP and fix offline)
# command: fetch-and-fix
# host: esxi.example.com
# user: root
# port: 22
# remote: /vmfs/volumes/datastore1/vm/vm.vmdk
# fetch_dir: ./downloads
# flatten: true
# to_output: esxi-vm-fixed.qcow2
# out_format: qcow2
# compress: true
# verbose: 1
#
# full snapshot chain:
# command: fetch-and-fix
# host: esxi-host
# identity: ~/.ssh/esxi_key
# remote: /path/to/snapshot-vm.vmdk
# fetch_all: true
# flatten: true
# resize: 50G
# regen_initramfs: true
# libvirt_test: true
# vm_name: esxi-test-vm
# uefi: true
# timeout: 90
# report: esxi-report.md
#
# 4) OVA / OVF (offline extract/parse)
# command: ova
# ova: /path/to/appliance.ova
# flatten: true
# to_output: appliance.qcow2
#
# command: ovf
# ovf: /path/to/appliance.ovf
# flatten: true
# to_output: appliance.qcow2
#
# 5) DAEMON (watch directory)
# command: daemon
# daemon: true
# watch_dir: /incoming
# output_dir: /out
#
# 6) vSphere/vCenter – discovery, downloads, export
# vSphere has multiple pathways:
#
#   (A) pyvmomi control-plane + /folder HTTP downloads
#       - good for listing, metadata, and raw datastore pulls
#
#   (B) govc export (control+data plane via govc)
#       - “just export it” OVF/OVA; govc manages HttpNfcLease internally
#
#   (C) OVF Tool export/deploy (control+data plane via ovftool)
#       - proprietary, optional
#
#   (D) Direct vSphere export (experimental)
#
# 6a) pyvmomi mode (list/download/CBT)
# command: vsphere
# vcenter: vcenter.example.com
# vc_user: administrator@vsphere.local
# vc_password_env: VC_PASSWORD
# vc_insecure: true
# vs_action: list_vm_names
# json: true
#
# get VM details:
# command: vsphere
# vcenter: vcenter.example.com
# vc_user: administrator@vsphere.local
# vc_password_env: VC_PASSWORD
# vc_insecure: true
# vs_action: get_vm_by_name
# name: myVM
# json: true
#
# download datastore file:
# command: vsphere
# vcenter: vcenter.example.com
# vc_user: administrator@vsphere.local
# vc_password_env: VC_PASSWORD
# vc_insecure: true
# dc_name: ha-datacenter
# vs_action: download_datastore_file
# datastore: datastore1
# ds_path: "[datastore1] myVM/myVM.vmdk"
# local_path: ./downloads/myVM.vmdk
# chunk_size: 1048576
#
# download-only VM folder pull (NO inspection):
# command: vsphere
# vcenter: vcenter.example.com
# vc_user: administrator@vsphere.local
# vc_password_env: VC_PASSWORD
# vc_insecure: true
# vs_action: download_only_vm
# vm_name: myVM
# output_dir: ./downloads/myVM-folder
# include_glob: ["*"]
# exclude_glob: ["*.lck", "*.log", "*.vswp", "*.vmem", "*.vmsn"]
# concurrency: 4
#
# 6b) govc export (recommended “just export it” path)
# govc is open source (govmomi). It manages HttpNfcLease + keepalive internally,
# and produces OVF or OVA packages.
#
# Common govc settings (either env GOVC_* or YAML keys):
# vs_control_plane: govc
# govc_url: "https://vcenter.example.com/sdk"
# govc_password_env: VC_PASSWORD
# govc_insecure: true
# govc_datacenter: ha-datacenter
#
# --- govc export OVA ---
# command: vsphere
# vs_control_plane: govc
# govc_url: "https://vcenter.example.com/sdk"
# govc_password_env: VC_PASSWORD
# govc_insecure: true
# govc_datacenter: ha-datacenter
# vs_action: export_vm
# export_mode: ova_export
# vm_name: myVM
# output_dir: ./downloads/govc
# govc_export_remove_cdroms: true
# govc_export_shutdown: true
# govc_export_power_off: true
# govc_export_shutdown_timeout_s: 600
# checksum: true
# verbose: 1
#
# Result:
#   ./downloads/govc/myVM.ova
#
# --- govc export OVF (directory) ---
# command: vsphere
# vs_control_plane: govc
# govc_url: "https://vcenter.example.com/sdk"
# govc_password_env: VC_PASSWORD
# govc_insecure: true
# govc_datacenter: ha-datacenter
# vs_action: export_vm
# export_mode: ovf_export
# vm_name: myVM
# output_dir: ./downloads/govc
# govc_export_remove_cdroms: true
# govc_export_shutdown: true
# govc_export_power_off: true
# checksum: true
# verbose: 1
#
# Result:
#   ./downloads/govc/myVM/ (contains .ovf + .vmdk + .mf)
#
# Chain export -> offline parse/convert:
# command: ovf
# ovf: ./downloads/govc/myVM/myVM.ovf
# flatten: true
# to_output: myVM.qcow2
# out_format: qcow2
# compress: true
# verbose: 1
#
# 6c) OVF Tool (ovftool) export/deploy (optional)
# ovftool is proprietary VMware/Broadcom tooling.
# Install:
#   https://developer.broadcom.com/tools/open-virtualization-format-ovf-tool/latest
#
# Typical install:
#   chmod +x VMware-ovftool-*.bundle
#   sudo ./VMware-ovftool-*.bundle
# Verify:
#   ovftool --version
#
# Common ovftool settings:
# ovftool_path: /usr/bin/ovftool
# ovftool_no_ssl_verify: true
# ovftool_accept_all_eulas: true
# ovftool_disk_mode: thin
# ovftool_overwrite: true
# ovftool_retries: 2
# ovftool_retry_backoff_s: 2.0
#
# --- ovftool export (OVA or OVF) ---
# command: vsphere
# vs_action: ovftool_export
# vcenter: vcenter.example.com
# vc_user: administrator@vsphere.local
# vc_password_env: VC_PASSWORD
# vc_insecure: true
# vm_name: myVM
# output_dir: ./downloads/ovftool
# # optional knobs:
# ovftool_path: /usr/bin/ovftool
# ovftool_no_ssl_verify: true
# ovftool_accept_all_eulas: true
# ovftool_overwrite: true
# # wrapper policy knobs (if supported by your vsphere_client/workflow):
# govc_export_remove_cdroms: true   # reuse same policy knobs if you unify them
# govc_export_shutdown: true
# govc_export_power_off: true
# verbose: 1
#
# Result:
#   OVA: ./downloads/ovftool/myVM.ova
#   OVF: ./downloads/ovftool/myVM/...
#
# --- ovftool deploy (upload OVA/OVF to vCenter) ---
# command: vsphere
# vs_action: ovftool_deploy
# vcenter: vcenter.example.com
# vc_user: administrator@vsphere.local
# vc_password_env: VC_PASSWORD
# vc_insecure: true
# source_path: ./appliance.ova
# # optional targeting:
# ovftool_target_folder: "Prod/Linux"
# ovftool_target_resource_pool: "/Datacenter/host/Cluster/Resources/Pool"
# ovftool_network_map: "VM Network:KVM-Bridge"
# ovftool_power_on: true
# ovftool_vm_name: "appliance-restored"
# ovftool_datastore: "datastore1"
#
# 6d) Direct vSphere export (EXPERIMENTAL)
# command: vsphere
# vcenter: vcenter.example.com
# vc_user: administrator@vsphere.local
# vc_password_env: VC_PASSWORD
# vc_insecure: true
# vs_export: true
# vm_name: myVM
# out_format: qcow2
# compress: true
# vs_datacenter: ha-datacenter
# vs_transport: vddk
# vs_vddk_libdir: /opt/vmware-vix-disklib-distrib
# vs_download_only: true
# vs_export_concurrency: 1
#
# 7) CLI examples (copy/paste)
#
# Local conversion (offline):
# sudo ./h2kvm.py --output-dir ./out local --vmdk /path/to/vm.vmdk --flatten --to-output vm.qcow2 --compress --regen-initramfs --print-fstab --fstab-mode stabilize-all --libvirt-test
#
# Fetch from ESXi and fix+test:
# sudo ./h2kvm.py --output-dir ./out fetch-and-fix --host esxi.example.com --user root --remote /vmfs/volumes/datastore1/vm/vm.vmdk --fetch-all --flatten --to-output esxi-vm.qcow2 --compress --regen-initramfs --libvirt-test --vm-name esxi-test --memory 4096 --vcpus 4 --uefi --timeout 90
#
# vSphere list VMs:
# sudo ./h2kvm.py --cmd vsphere --vcenter vcenter.example.com --vc-user administrator@vsphere.local --vc-password-env VC_PASSWORD --vc-insecure --vs-action list_vm_names --json
#
# govc export OVA:
# sudo ./h2kvm.py --cmd vsphere --vs-action export_vm --export-mode ova_export --vm_name myVM --govc-url https://vcenter.example.com/sdk --govc-password-env VC_PASSWORD --govc-insecure
#
# ovftool export:
# sudo ./h2kvm.py --cmd vsphere --vs-action ovftool_export --vm_name myVM --ovftool-path /usr/bin/ovftool --vc-password-env VC_PASSWORD --vc-insecure
#
"""

FEATURE_SUMMARY = """ • Inputs: local VMDK/VHD, remote ESXi fetch, OVA/OVF extract, AMI/cloud tarball extract, \
live SSH fix, vSphere\n
 • Snapshot: flatten convert, recursive parent descriptor fetch, vSphere snapshots/CBT hooks\n
 • Fixes: fstab UUID/PARTUUID/LABEL, btrfs canonicalization, grub root=, crypttab, mdraid checks\n
 • Windows: virtio injection, registry services + CriticalDeviceDatabase, YAML-driven driver/PNP mapping, YAML/JSON network override staging\n
 • Cloud: cloud-init injection\n
 • Outputs: qcow2/raw/vdi, compression levels, validation, checksums\n
 • Tests: libvirt and qemu smoke tests, BIOS/UEFI modes\n
 • Safety: dry-run, backups, report generation, verbose logs, recovery checkpoints\n
 • Performance: parallel batch processing\n
 • vSphere export (recommended): govc OVF/OVA export (control+data plane)\n
 • vSphere export (optional): OVF Tool (ovftool) export/deploy (control+data plane)\n
 • vSphere download-only: VM folder file pull via /folder (no inspection)\n
 • vSphere VDDK raw: single disk direct pull via VDDK client (no inspection)\n
 • vSphere NFC: pyvmomi NFC lease streaming (useful when /folder is blocked)\n
 • vSphere -> direct export: experimental export hook\n
"""

# If you already embed SYSTEMD_UNIT_TEMPLATE elsewhere, keep this as extra human text.
SYSTEMD_EXAMPLE = ""  # Optional extra systemd text beyond SYSTEMD_UNIT_TEMPLATE
