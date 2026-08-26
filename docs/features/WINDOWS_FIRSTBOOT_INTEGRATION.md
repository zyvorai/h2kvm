# Windows Enterprise Firstboot Integration

**Enterprise-grade first-boot initialization for Windows VMs converted from VMware to KVM/QEMU**

## Overview

The Windows firstboot integration provides **automatic post-conversion initialization** for Windows VMs, matching the Linux systemd firstboot implementation with enterprise features comparable to Azure Migrate and AWS VM Import.

### Key Features

1. **VMware Tools Complete Removal** - Registry, services, drivers, and files
2. **QEMU Guest Agent Installation** - KVM/QEMU integration
3. **Enhanced VirtIO Driver Installation** - Multiple installation methods
4. **Network Reconfiguration** - MAC address changes and adapter reset
5. **RDP Enablement** - Remote access configuration
6. **Windows Event Log Integration** - Enterprise observability (matches systemd journal)
7. **Health Verification** - Post-conversion validation
8. **Conversion Metadata** - Tracking and auditing

## Architecture

### Windows Service-Based Execution

Unlike RunOnce registry entries (fragile across logon/autologon scenarios), hyper2kvm uses a **Windows Service** for reliable first-boot execution:

```
Boot Sequence:
1. Windows kernel loads
2. Service Control Manager (SCM) starts
3. hyper2kvm-firstboot service executes (LocalSystem)
4. 8-step enterprise initialization
5. Detailed logging to:
   - C:\Windows\Temp\hyper2kvm-firstboot.log
   - Windows Event Log (Application → hyper2kvm → Event ID 1000)
6. Service self-deletes
7. Completion marker written (C:\hyper2kvm\firstboot.done)
```

### Service Configuration

```
Service Name:    hyper2kvm-firstboot
Display Name:    hyper2kvm First Boot Driver Installer
Service Type:    Win32 Own Process
Start Type:      Automatic (2)
Account:         LocalSystem
ImagePath:       %SystemRoot%\System32\cmd.exe /c "C:\hyper2kvm\firstboot.cmd"
Description:     One-shot first boot installer for hyper2kvm staged drivers
```

## Enterprise Initialization (8 Steps)

### 1. QEMU Guest Agent Installation

```powershell
Location: C:\hyper2kvm\drivers\virtio\guest-agent\qemu-ga-x86_64.msi
Method:   Silent MSI installation (msiexec /i /qn /norestart)
Service:  QEMU-GA (Automatic start)
Purpose:  - VM state monitoring
          - Graceful shutdown/reboot
          - File/command execution from host
          - Network/IP address reporting
```

**Verification:**
```cmd
sc query QEMU-GA
Get-Service QEMU-GA | Select Name, Status, StartType
```

### 2. Enhanced VirtIO Driver Installation

**Method 1: Staged INF Files**
```cmd
pnputil /add-driver C:\hyper2kvm\drivers\virtio\*.inf /install
```

**Method 2: DriverStore Search**
```powershell
$driverStore = "C:\Windows\System32\DriverStore\FileRepository"
Get-ChildItem $driverStore -Filter *.inf -Recurse |
  Where-Object { $_.FullName -match 'virtio|redhat' } |
  ForEach-Object { pnputil /add-driver $_.FullName /install }
```

**Method 3: Hardware Scan**
```cmd
pnputil /scan-devices
```

**Method 4: Device Enablement**
```powershell
Get-WmiObject Win32_PnPEntity |
  Where-Object { $_.Name -match 'VirtIO' -and $_.ConfigManagerErrorCode -ne 0 } |
  ForEach-Object { $_.Enable() }
```

**Installed Drivers:**
- `viostor` - VirtIO SCSI Controller
- `vioscsi` - VirtIO SCSI pass-through
- `netkvm` - VirtIO Ethernet Adapter
- `balloon` - VirtIO Balloon Driver
- `vioserial` - VirtIO Serial Driver
- `viorng` - VirtIO RNG Device

### 3. SID Regeneration (Informational)

```
Status: Informational only (not executed automatically)
Reason: SID regeneration via sysprep /generalize resets Windows activation
Action: Logs sysprep location for manual execution if required
```

**Manual SID regeneration (if needed):**
```cmd
C:\Windows\System32\Sysprep\sysprep.exe /generalize /oobe /reboot
```

### 4. Network Reconfiguration

**VMware Adapter Cleanup:**
```powershell
Get-NetAdapter | Where-Object { $_.InterfaceDescription -match 'VMware' } |
  Disable-NetAdapter -Confirm:$false
```

**VirtIO Adapter Reset:**
```powershell
Get-NetAdapter | Where-Object { $_.InterfaceDescription -match 'VirtIO|Red Hat' } |
  Restart-NetAdapter
```

**DHCP Renewal:**
```cmd
ipconfig /release
ipconfig /renew
```

### 5. RDP Enablement

```powershell
# Enable RDP
Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' `
                 -Name fDenyTSConnections -Value 0

# Enable firewall rules
Enable-NetFirewallRule -DisplayGroup 'Remote Desktop'
```

**Verification:**
```cmd
reg query "HKLM\System\CurrentControlSet\Control\Terminal Server" /v fDenyTSConnections
netsh advfirewall firewall show rule name="Remote Desktop - User Mode (TCP-In)"
```

### 6. Windows Event Log Integration

**Event Source Registration:**
```powershell
[System.Diagnostics.EventLog]::CreateEventSource('hyper2kvm', 'Application')
```

**Completion Event:**
```
Log:        Application
Source:     hyper2kvm
Event ID:   1000
Type:       Information
Message:    Hyper2KVM first boot initialization completed successfully.
            VMware to KVM conversion finalized.
```

**View Events:**
```powershell
Get-EventLog -LogName Application -Source hyper2kvm -Newest 10
```

### 7. Health Verification

**Checks Performed:**
1. **QEMU Guest Agent** - Service running status
2. **Network Connectivity** - Adapters UP status
3. **VirtIO Devices** - Device detection and status
4. **System Disk** - Mount status and free space
5. **Failed Services** - Automatic services that failed to start

**Output Example:**
```
=== Health Check Summary ===
OK: QEMU Guest Agent is running
OK: 1 network adapter(s) UP
OK: 6 VirtIO device(s) detected
OK: System drive mounted (C:)
  Free: 45.23 GB / 127.00 GB
OK: No failed services detected
Health check: PASS
```

### 8. Conversion Metadata

**File:** `C:\hyper2kvm\metadata.json`

**Content:**
```json
{
  "conversion_tool": "hyper2kvm",
  "conversion_version": "enterprise-1.0",
  "conversion_date": "2026-02-14T20:15:30Z",
  "source_platform": "VMware",
  "target_platform": "KVM/QEMU",
  "features_applied": [
    "VMware Tools removal",
    "VirtIO driver installation",
    "QEMU Guest Agent installation",
    "Network reconfiguration",
    "RDP enablement",
    "Windows Event Log integration"
  ],
  "firstboot_completed": "2026-02-14T20:17:45Z",
  "computer_name": "WIN-SERVER2022",
  "os_version": "10.0.20348.0"
}
```

## VMware Tools Complete Removal

### Comprehensive Removal Process

**1. Registry-Based Uninstall:**
```powershell
$keys = @(
  'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
$apps = Get-ItemProperty $keys | Where-Object {
  ($_.DisplayName -match 'VMware Tools') -or ($_.Publisher -match 'VMware')
}
foreach($app in $apps) {
  $uninstall = $app.QuietUninstallString
  if($uninstall -match 'msiexec') {
    $uninstall += ' /qn /norestart'
  }
  Start-Process cmd.exe -ArgumentList "/c $uninstall" -Wait
}
```

**2. Services Stop/Delete:**
```cmd
sc stop VMTools && sc delete VMTools
sc stop VGAuthService && sc delete VGAuthService
sc stop vmvss && sc delete vmvss
sc stop vmware-aliases && sc delete vmware-aliases
sc stop vmtoolsd && sc delete vmtoolsd
```

**3. Driver Services Removal:**
```cmd
# Stop and delete driver services
for %D in (vm3dmp vmmouse vmusbmouse vmxnet3 vmxnet vmhgfs vmci vmscsi pvscsi vmmemctl vsock vmrawdsk) do (
  sc stop %D
  sc delete %D
  reg delete "HKLM\SYSTEM\CurrentControlSet\Services\%D" /f
)
```

**4. Driver Files Deletion:**
```cmd
del /f /q C:\Windows\System32\drivers\vm3dmp.sys
del /f /q C:\Windows\System32\drivers\vmmouse.sys
del /f /q C:\Windows\System32\drivers\vmxnet3.sys
del /f /q C:\Windows\System32\drivers\pvscsi.sys
del /f /q C:\Windows\System32\drivers\vmmemctl.sys
```

**5. PnP Driver Removal:**
```cmd
pnputil /enum-drivers | findstr /i "vmware" > vmware_drivers.txt
for /f "tokens=1" %I in (vmware_drivers.txt) do (
  pnputil /delete-driver %I /uninstall /force
)
```

**6. Device Manager Cleanup:**
```powershell
Get-WmiObject Win32_PnPEntity |
  Where-Object { $_.Name -match 'VMware' -or $_.Manufacturer -match 'VMware' } |
  ForEach-Object { $_.Delete() }
```

**7. Directory Removal:**
```cmd
takeown /f "C:\Program Files\VMware\VMware Tools" /r /d y
icacls "C:\Program Files\VMware\VMware Tools" /grant Administrators:F /t
rmdir /s /q "C:\Program Files\VMware\VMware Tools"
```

## File Locations

### Staging Directory
```
C:\hyper2kvm\drivers\virtio\     (guestfs: /hyper2kvm/drivers/virtio/)
├── viostor\              - SCSI controller drivers
├── vioscsi\              - SCSI pass-through drivers
├── netkvm\               - Network drivers
├── balloon\              - Balloon driver
├── vioserial\            - Serial driver
├── viorng\               - RNG driver
└── guest-agent\          - QEMU Guest Agent MSI
    └── qemu-ga-x86_64.msi
```

### Logs and Markers
```
C:\Windows\Temp\hyper2kvm-firstboot.log   (guestfs: /Windows/Temp/hyper2kvm-firstboot.log)
C:\hyper2kvm\firstboot.done               (guestfs: /hyper2kvm/firstboot.done)
C:\hyper2kvm\metadata.json                (guestfs: /hyper2kvm/metadata.json)
```

### Script Location
```
C:\hyper2kvm\firstboot.cmd                (guestfs: /hyper2kvm/firstboot.cmd)
```

## Verification After First Boot

### 1. Check Firstboot Execution

**View log file:**
```cmd
type C:\Windows\Temp\hyper2kvm-firstboot.log
```

**Check completion marker:**
```cmd
dir C:\hyper2kvm\firstboot.done
```

### 2. Verify Windows Event Log

```powershell
Get-EventLog -LogName Application -Source hyper2kvm -Newest 1
```

**Expected output:**
```
Index Time          EntryType   Source    InstanceID Message
----- ----          ---------   ------    ---------- -------
12345 Feb 14 20:17  Information hyper2kvm       1000 Hyper2KVM first boot initialization...
```

### 3. Check QEMU Guest Agent

```powershell
Get-Service QEMU-GA | Select Name, Status, StartType
sc query QEMU-GA
```

**Expected:**
```
Name    Status  StartType
----    ------  ---------
QEMU-GA Running Automatic
```

### 4. Verify VirtIO Drivers

```powershell
Get-WmiObject Win32_PnPEntity | Where-Object { $_.Name -match 'VirtIO' } |
  Select Name, Status | Format-Table
```

**Expected output:**
```
Name                                Status
----                                ------
Red Hat VirtIO Ethernet Adapter     OK
VirtIO Balloon Driver               OK
VirtIO SCSI Controller              OK
```

### 5. Check Network Connectivity

```powershell
Get-NetAdapter | Where-Object { $_.Status -eq 'Up' } |
  Select Name, InterfaceDescription, MacAddress, Status
```

### 6. Verify Conversion Metadata

```powershell
Get-Content C:\hyper2kvm\metadata.json | ConvertFrom-Json | Format-List
```

### 7. Check for Failed Services

```powershell
Get-Service | Where-Object { $_.Status -eq 'Stopped' -and $_.StartType -eq 'Automatic' } |
  Select Name, DisplayName, Status
```

### 8. Verify VMware Removal

```cmd
# Check services
sc query | findstr VMware

# Check drivers
driverquery | findstr /i vmware

# Check PnP drivers
pnputil /enum-drivers | findstr /i vmware

# Check installed programs
wmic product where "name like '%VMware%'" get name
```

**Expected:** All commands should return empty (no VMware components found)

## Integration with hyper2kvm Pipeline

### Automatic Provisioning

The Windows enterprise firstboot is **automatically provisioned** during VM conversion when using `inject_virtio_drivers()`:

```python
from hyper2kvm.fixers.windows import inject_virtio_drivers

result = inject_virtio_drivers(g)
# Firstboot service automatically created with:
# - VMware Tools removal
# - QEMU Guest Agent installation
# - Enhanced VirtIO installation
# - Network reconfiguration
# - RDP enablement
# - Event Log integration
# - Health verification
# - Metadata creation
```

### Manual Provisioning

For custom scenarios, use the provisioning function directly:

```python
from hyper2kvm.fixers.windows.registry.firstboot import provision_firstboot_payload_and_service

fb_result = provision_firstboot_payload_and_service(
    fixer_instance,
    guestfs_instance,
    system_hive_path="/Windows/System32/config/SYSTEM",
    service_name="hyper2kvm-firstboot",
    remove_vmware_tools=True,
    install_qemu_guest_agent=True,
    enhanced_virtio_install=True,
    network_reconfiguration=True,
    enable_rdp=True,
    event_log_integration=True,
    health_verification=True,
    create_metadata=True,
)

print(fb_result["notes"])
```

### Disable Specific Features

```python
fb_result = provision_firstboot_payload_and_service(
    fixer_instance,
    guestfs_instance,
    remove_vmware_tools=True,
    install_qemu_guest_agent=True,
    enhanced_virtio_install=True,
    network_reconfiguration=False,  # Disable network reconfig
    enable_rdp=False,                # Keep RDP disabled
    event_log_integration=True,
    health_verification=True,
    create_metadata=True,
)
```

## Comparison with Linux Systemd Firstboot

| Feature | Linux (systemd) | Windows (Service) |
|---------|----------------|-------------------|
| **Execution Mechanism** | systemd-generator + oneshot service | Windows Service (Auto start) |
| **Logging** | systemd journal (`journalctl`) | Windows Event Log + text log |
| **Machine Identity** | `/etc/machine-id` reset | SID (informational) |
| **Driver Installation** | dracut virtio injection | pnputil + DriverStore |
| **Guest Agent** | qemu-guest-agent (yum/apt) | QEMU-GA MSI installer |
| **Network Reset** | NetworkManager + udev | Disable VMware, reset VirtIO |
| **Idempotency** | `/etc/hyper2kvm/converted` flag | `C:\hyper2kvm\firstboot.done` |
| **Self-Cleanup** | Service disables itself | Service deletes itself |
| **Metadata** | `/etc/hyper2kvm/metadata.json` | `C:\hyper2kvm\metadata.json` |
| **Observability** | Structured journal logs | Event Log (ID 1000) |

## Troubleshooting

### Firstboot Didn't Run

**Check service status:**
```cmd
sc query hyper2kvm-firstboot
```

**If service exists but didn't run:**
```cmd
# Check service configuration
sc qc hyper2kvm-firstboot

# Check service start type (should be 2 = AUTO_START)
reg query "HKLM\SYSTEM\CurrentControlSet\Services\hyper2kvm-firstboot" /v Start
```

**Manual trigger (if needed):**
```cmd
sc start hyper2kvm-firstboot
```

### QEMU Guest Agent Not Running

**Check installation logs:**
```cmd
type C:\Windows\Temp\qemu-ga-install.log
```

**Manual installation:**
```cmd
msiexec /i C:\hyper2kvm\drivers\virtio\guest-agent\qemu-ga-x86_64.msi /qn /norestart /l*v C:\qemu-ga-manual.log
```

### VirtIO Drivers Not Installed

**Check driver staging:**
```cmd
dir /s /b C:\hyper2kvm\drivers\virtio\*.inf
```

**Manual driver installation:**
```cmd
pnputil /add-driver C:\hyper2kvm\drivers\virtio\viostor\*.inf /install
pnputil /add-driver C:\hyper2kvm\drivers\virtio\netkvm\*.inf /install
pnputil /scan-devices
```

### Network Not Working

**Check network adapters:**
```powershell
Get-NetAdapter | Select Name, InterfaceDescription, Status, MacAddress
```

**Reset network stack:**
```cmd
netsh winsock reset
netsh int ip reset
ipconfig /flushdns
ipconfig /release
ipconfig /renew
```

### VMware Tools Still Present

**Check manually:**
```cmd
sc query | findstr VMware
driverquery | findstr /i vmware
dir "C:\Program Files\VMware"
```

**Manual removal:**
```cmd
# Uninstall via Programs and Features
appwiz.cpl

# Or use MSI
wmic product where "name like '%VMware Tools%'" call uninstall
```

## Best Practices

1. **Always stage QEMU Guest Agent MSI** in `C:\hyper2kvm\drivers\virtio\guest-agent\qemu-ga-x86_64.msi`

2. **Enable all enterprise features** for production migrations:
   ```python
   remove_vmware_tools=True,
   install_qemu_guest_agent=True,
   enhanced_virtio_install=True,
   network_reconfiguration=True,
   enable_rdp=True,
   event_log_integration=True,
   health_verification=True,
   create_metadata=True
   ```

3. **Review logs after first boot** - Check `C:\Windows\Temp\hyper2kvm-firstboot.log` and Windows Event Log

4. **Verify health status** - Run health verification commands to ensure all components are working

5. **Document metadata** - Save `C:\hyper2kvm\metadata.json` for audit trails

## Production Readiness

The Windows enterprise firstboot integration is **production-ready** and provides:

✅ **Comprehensive VMware cleanup** - All components removed
✅ **Complete VirtIO integration** - Multiple installation methods
✅ **Enterprise observability** - Event Log + detailed text logs
✅ **Health verification** - Automated post-conversion checks
✅ **Metadata tracking** - Audit trail and compliance
✅ **Idempotency** - Safe to reboot during/after execution
✅ **Self-cleaning** - Service removes itself after completion

**Deployment Status:** ✅ READY FOR PRODUCTION USE

---

**For more information:**
- [Windows VirtIO Driver Installation](./windows-virtio-drivers.md)
- [Linux Systemd Firstboot Integration](./SYSTEMD_FIRSTBOOT_INTEGRATION.md)
- [VMware to KVM Migration Guide](../guides/windows-migration-guide.md)
