# Windows Migration Troubleshooting Runbook

**Version**: v0.5.0+
**Last Updated**: 2026-03-29
**Audience**: System Administrators, Support Engineers

This runbook provides diagnostic procedures and solutions for common Windows VM migration issues with h2kvm.

---

## Table of Contents

1. [Quick Diagnostic Commands](#quick-diagnostic-commands)
2. [Boot and Startup Issues](#boot-and-startup-issues)
3. [Driver and Hardware Issues](#driver-and-hardware-issues)
4. [License Activation Issues](#license-activation-issues)
5. [Active Directory Issues](#active-directory-issues)
6. [Network Connectivity Issues](#network-connectivity-issues)
7. [Performance Issues](#performance-issues)
8. [Application Compatibility Issues](#application-compatibility-issues)
9. [Storage and Filesystem Issues](#storage-and-filesystem-issues)
10. [Security and Access Issues](#security-and-access-issues)

---

## Quick Diagnostic Commands

### Windows Guest Commands

```powershell
# System information
systeminfo | findstr /B /C:"OS Name" /C:"OS Version" /C:"System Type"

# Check activation status
slmgr.vbs /dli
slmgr.vbs /xpr

# Verify domain membership
Get-CimInstance Win32_ComputerSystem | Select-Object Name, Domain, PartOfDomain

# List VirtIO drivers
Get-WmiObject Win32_PnPSignedDriver | Where-Object {$_.DeviceName -like "*VirtIO*" -or $_.DeviceName -like "*Red Hat*"}

# Check network adapters
Get-NetAdapter | Select-Object Name, Status, LinkSpeed
Get-NetIPAddress

# Verify disk configuration
Get-Disk | Select-Object Number, PartitionStyle, Size, OperationalStatus
fsutil behavior query DisableDeleteNotification

# Check services
Get-Service | Where-Object {$_.Name -match "balloon|netkvm|viostor"}

# Review recent errors
Get-EventLog -LogName System -Newest 50 -EntryType Error
Get-EventLog -LogName Application -Newest 50 -EntryType Error
```

### KVM Host Commands

```bash
# Check VM status
virsh list --all

# View VM configuration
virsh dumpxml windows-server | less

# Check VM console (for boot issues)
virsh console windows-server

# View VM logs
journalctl -u libvirtd -f

# Monitor resource usage
virt-top

# Check disk configuration
virsh domblklist windows-server

# Check network configuration
virsh domiflist windows-server

# Verify VirtIO driver ISO at standard path (auto-discovered by h2kvm)
ls -lh /var/lib/h2kvm/virtio-win.iso

# Or check custom driver directory if using --virtio-drivers-dir override
ls -lh /opt/virtio-drivers/
```

---

## Boot and Startup Issues

### Issue: BSOD 0x0000007B - Inaccessible Boot Device

**Symptoms**:
- Blue screen during Windows boot
- Error code 0x0000007B
- "INACCESSIBLE_BOOT_DEVICE"

**Root Cause**:
VirtIO storage driver not properly injected or loaded

**Diagnostic Steps**:

1. Boot Windows in Safe Mode (if possible)
2. Check if VirtIO drivers are present:
   ```powershell
   Get-ChildItem C:\Windows\System32\drivers\vio*.sys
   ```

3. Check BCD (Boot Configuration Data):
   ```cmd
   bcdedit /enum
   ```

**Solutions**:

**Solution 1: Re-inject VirtIO Drivers**

First, ensure the VirtIO ISO is installed:
```bash
# Download to standard path (auto-discovered by h2kvm — no --virtio-drivers-dir needed)
sudo ./scripts/install-deps.sh --virtio-win
```

Then re-run the migration:
```bash
# On KVM host
virt-win-reg --merge windows-server.qcow2 \
  C:\Windows\System32\config\SYSTEM \
  viostor-injection.reg

# Or re-run migration with forced injection
# VirtIO ISO is auto-discovered at /var/lib/h2kvm/virtio-win.iso
h2kvm convert \
  --input source.vmdk \
  --output target-fixed.qcow2 \
  --force-virtio-injection
  # --virtio-drivers-dir /custom/path  # only needed to override the standard path
```

**Solution 2: Use IDE Controller Temporarily**
```bash
# Modify VM to use IDE instead of VirtIO temporarily
virsh edit windows-server

# Change:
#   <disk type='file' device='disk'>
#     <driver name='qemu' type='qcow2' cache='none'/>
#     <target dev='vda' bus='virtio'/>
#   </disk>

# To:
#   <disk type='file' device='disk'>
#     <driver name='qemu' type='qcow2' cache='none'/>
#     <target dev='hda' bus='ide'/>
#   </disk>

# Boot Windows, install VirtIO drivers manually, then switch back
```

**Solution 3: Manual Driver Injection**
```bash
# Mount Windows partition
guestmount -a windows-server.qcow2 -i /mnt/windows

# Extract and copy VirtIO drivers from the standard ISO path
# (or from /opt/virtio-drivers if using --virtio-drivers-dir override)
cp -r /opt/virtio-drivers/viostor/2k19/amd64/* /mnt/windows/Windows/System32/drivers/

# Unmount
guestunmount /mnt/windows

# Update registry (requires hivex tools)
virt-win-reg --merge windows-server.qcow2 viostor.reg
```

---

### Issue: Windows Boot Loop or Automatic Repair

**Symptoms**:
- Windows attempts automatic repair repeatedly
- "Your PC did not start correctly"
- Boot loop

**Diagnostic Steps**:

1. Check boot order and BCD configuration
2. Review System event logs (if accessible)
3. Boot into Safe Mode

**Solutions**:

**Solution 1: Repair BCD**
```cmd
# Boot from Windows installation media
# Select "Repair your computer" → "Troubleshoot" → "Command Prompt"

bootrec /fixmbr
bootrec /fixboot
bootrec /rebuildbcd

# Verify BCD
bcdedit /enum
```

**Solution 2: Reset BCD**
```cmd
# In WinRE command prompt
bcdedit /export C:\BCD_Backup
cd /d C:\boot
attrib bcd -s -h -r
ren c:\boot\bcd bcd.old
bootrec /rebuildbcd
```

**Solution 3: Restore from Snapshot**
```bash
# On KVM host
virsh snapshot-revert windows-server pre-migration
```

---

### Issue: Black Screen After Boot

**Symptoms**:
- Windows appears to boot (no BSOD)
- Black screen with or without cursor
- No login prompt

**Diagnostic Steps**:

1. Check if Ctrl+Alt+Delete shows login screen
2. Verify display driver loaded
3. Check graphics configuration

**Solutions**:

**Solution 1: Use SPICE or VNC**
```bash
# Ensure graphics are configured
virsh edit windows-server

# Verify graphics section:
<graphics type='spice' port='5900' autoport='yes'/>
# Or:
<graphics type='vnc' port='5900' autoport='yes' listen='0.0.0.0'/>
```

**Solution 2: Boot to Safe Mode**
```bash
# Force Safe Mode boot
virt-win-reg --merge windows-server.qcow2 \
  'HKLM\SYSTEM\CurrentControlSet\Control\SafeBoot\Minimal'
```

**Solution 3: Disable Fast Startup**
```powershell
# In Safe Mode or via registry
REG ADD "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power" /v HiberbootEnabled /t REG_DWORD /d 0 /f
```

---

## Driver and Hardware Issues

### Issue: Network Adapter Not Found

**Symptoms**:
- No network adapters in Device Manager
- "No connections are available"
- Network icon shows disconnected

**Diagnostic Steps**:

```powershell
# Check for network adapters
Get-NetAdapter -IncludeHidden

# Check Device Manager for unknown devices
Get-WmiObject Win32_PnPEntity | Where-Object {$_.ConfigManagerErrorCode -ne 0}

# Verify VirtIO network driver
Get-PnpDevice -FriendlyName "*ethernet*"
```

**Solutions**:

**Solution 1: Install VirtIO Network Driver**
```powershell
# From within Windows
pnputil /add-driver C:\virtio-drivers\NetKVM\2k19\amd64\*.inf /subdirs /install

# Rescan for hardware
pnputil /scan-devices
```

**Solution 2: Verify VM Network Configuration**
```bash
# On KVM host
virsh domiflist windows-server

# Should show virtio model:
# Model: virtio

# If not, edit:
virsh edit windows-server

# Ensure:
<interface type='network'>
  <source network='default'/>
  <model type='virtio'/>
</interface>
```

**Solution 3: Use E1000 Temporarily**
```bash
# Edit VM configuration
virsh edit windows-server

# Change model to e1000:
<model type='e1000'/>

# Boot Windows, install VirtIO drivers, then switch back
```

---

### Issue: Disk Performance Problems

**Symptoms**:
- Extremely slow disk I/O
- High disk latency
- Applications timeout

**Diagnostic Steps**:

```powershell
# Check disk performance
Get-PhysicalDisk | Select-Object FriendlyName, MediaType, BusType, HealthStatus

# Verify VirtIO storage driver
Get-PnpDevice -FriendlyName "*disk*" | Select-Object FriendlyName, Status

# Check disk usage
Get-Counter '\PhysicalDisk(*)\Avg. Disk Queue Length'
```

**Solutions**:

**Solution 1: Enable TRIM/Discard**
```powershell
# Enable TRIM
fsutil behavior set DisableDeleteNotification 0

# Verify
fsutil behavior query DisableDeleteNotification

# Run optimization
defrag C: /L /O
```

**Solution 2: Verify Disk Cache Settings**
```bash
# On KVM host
virsh dumpxml windows-server | grep -A 5 "<disk"

# Recommended cache mode for qcow2:
<driver name='qemu' type='qcow2' cache='none' io='native'/>

# Edit if needed:
virsh edit windows-server
```

**Solution 3: Check Host Storage Performance**
```bash
# Test host disk performance
dd if=/dev/zero of=/tmp/test bs=1M count=1024 conv=fdatasync
rm /tmp/test

# Check I/O scheduler
cat /sys/block/sda/queue/scheduler

# For SSDs, use mq-deadline or none:
echo mq-deadline > /sys/block/sda/queue/scheduler
```

---

### Issue: USB Devices Not Working

**Symptoms**:
- USB devices not detected
- USB passthrough fails
- Dongle not recognized

**Solutions**:

**Solution 1: Configure USB Passthrough**
```bash
# Find USB device
lsusb

# Output example:
# Bus 002 Device 003: ID 0529:0001 Aladdin Knowledge Systems HASP

# Edit VM configuration
virsh edit windows-server

# Add USB device:
<hostdev mode='subsystem' type='usb'>
  <source>
    <vendor id='0x0529'/>
    <product id='0x0001'/>
  </source>
</hostdev>
```

**Solution 2: Use USB Redirection**
```bash
# Enable SPICE USB redirection
virsh edit windows-server

# Add:
<redirdev bus='usb' type='spicevmc'/>
<redirdev bus='usb' type='spicevmc'/>
```

---

## License Activation Issues

### Issue: Windows Not Activated After Migration

**Symptoms**:
- "Windows is not activated"
- Watermark on desktop
- Activation error codes

**Diagnostic Steps**:

```powershell
# Check activation status
slmgr.vbs /dli
slmgr.vbs /dlv

# Check product key
slmgr.vbs /dpr

# View detailed activation info
cscript C:\Windows\System32\slmgr.vbs /dlv
```

**Solutions by License Type**:

**MAK License**:
```powershell
# Reactivate online
slmgr.vbs /ato

# If activation limit reached
slmgr.vbs /dti
# Call Microsoft Activation Center with Installation ID

# Phone activation
slmgr.vbs /dti
slmgr.vbs /atp <confirmation-id>
```

**KMS License**:
```powershell
# Verify KMS server connectivity
nslookup -type=srv _vlmcs._tcp.company.com

# Set KMS server (if not auto-discovered)
slmgr.vbs /skms kms.company.com:1688

# Activate
slmgr.vbs /ato

# Check KMS client status
slmgr.vbs /dlv
```

**Retail License**:
```powershell
# Online activation
slmgr.vbs /ato

# If hardware change too significant, use phone activation
slmgr.vbs /dti
# Call Microsoft and provide Installation ID

# Enter Confirmation ID
slmgr.vbs /atp <confirmation-id>
```

**OEM License**:
```powershell
# OEM keys typically won't reactivate on different hardware
# Options:
# 1. Purchase new license
# 2. Contact Microsoft support
# 3. Use Volume License if available
```

---

### Issue: Activation Error 0xC004F074

**Error**: "The Software Licensing Service reported that the computer could not be activated. No Key Management Service (KMS) could be contacted."

**Solutions**:

```powershell
# Verify DNS resolution
nslookup _vlmcs._tcp.company.com

# Set KMS server manually
slmgr.vbs /skms kms-server.company.com

# Clear KMS cache
slmgr.vbs /ckms
slmgr.vbs /skms kms-server.company.com

# Retry activation
slmgr.vbs /ato
```

---

## Active Directory Issues

### Issue: Cannot Join Domain After Migration

**Error Messages**:
- "The specified domain either does not exist or could not be contacted"
- "The account already exists"
- "Access is denied"

**Diagnostic Steps**:

```powershell
# Test domain connectivity
Test-ComputerSecureChannel -Verbose

# Test DNS resolution
nslookup company.com
nslookup _ldap._tcp.dc._msdcs.company.com

# Test domain controller connectivity
Test-NetConnection dc01.company.com -Port 389
Test-NetConnection dc01.company.com -Port 88

# Check current computer name
hostname
```

**Solutions**:

**Solution 1: DNS Configuration**
```powershell
# Verify DNS servers
Get-DnsClientServerAddress

# Set DNS servers to domain controllers
Set-DnsClientServerAddress -InterfaceAlias "Ethernet" -ServerAddresses 10.0.0.10,10.0.0.11

# Flush DNS cache
ipconfig /flushdns

# Test again
nslookup company.com
```

**Solution 2: Remove Existing Computer Account**
```powershell
# On domain controller or admin workstation
Import-Module ActiveDirectory

# Find old computer object
Get-ADComputer -Filter {Name -eq "OLD-SERVER-NAME"}

# Remove it
Remove-ADComputer -Identity "OLD-SERVER-NAME" -Confirm:$true

# Wait for AD replication (5-15 minutes)
# Then retry domain join
```

**Solution 3: Use Different Computer Name**
```powershell
# Rename computer before domain join
Rename-Computer -NewName "NEW-SERVER-NAME" -Restart

# After reboot, join domain
Add-Computer -DomainName company.com -Credential (Get-Credential) -Restart
```

**Solution 4: Reset Secure Channel**
```powershell
# If already domain-joined but broken trust
Test-ComputerSecureChannel -Repair -Credential (Get-Credential domain\admin)

# If repair fails, unjoin and rejoin
Remove-Computer -UnjoinDomainCredential (Get-Credential) -Force -Restart

# After reboot
Add-Computer -DomainName company.com -Credential (Get-Credential) -Restart
```

---

### Issue: Domain Join Succeeds But Cannot Login

**Symptoms**:
- Domain join appears successful
- Cannot login with domain credentials
- "There are currently no logon servers available"

**Solutions**:

```powershell
# Verify secure channel
Test-ComputerSecureChannel

# Check domain controller connectivity
nltest /dsgetdc:company.com

# Verify time synchronization (critical for Kerberos)
w32tm /query /status
w32tm /resync

# Check netlogon service
Get-Service Netlogon | Restart-Service

# Test login with local admin
# Then fix trust relationship
Test-ComputerSecureChannel -Repair -Credential (Get-Credential)
```

---

## Network Connectivity Issues

### Issue: No Network Connectivity

**Symptoms**:
- No network connection
- Cannot ping gateway
- DNS resolution fails

**Diagnostic Steps**:

```powershell
# Check adapter status
Get-NetAdapter

# Check IP configuration
Get-NetIPAddress
Get-NetIPConfiguration

# Test gateway connectivity
Test-NetConnection -ComputerName <gateway-ip>

# Test DNS
Resolve-DnsName google.com
nslookup google.com

# Check routing table
Get-NetRoute
```

**Solutions**:

**Solution 1: Reset Network Stack**
```powershell
# Reset TCP/IP stack
netsh int ip reset
netsh winsock reset

# Restart network adapter
Get-NetAdapter | Restart-NetAdapter

# Reboot if needed
Restart-Computer
```

**Solution 2: Reconfigure Network Adapter**
```powershell
# Release and renew DHCP
ipconfig /release
ipconfig /renew

# Or set static IP
New-NetIPAddress -InterfaceAlias "Ethernet" -IPAddress 192.168.1.100 -PrefixLength 24 -DefaultGateway 192.168.1.1
Set-DnsClientServerAddress -InterfaceAlias "Ethernet" -ServerAddresses 8.8.8.8,8.8.4.4
```

**Solution 3: Verify KVM Network Bridge**
```bash
# On KVM host
brctl show

# Check VM network
virsh domiflist windows-server

# Test host connectivity
ping <vm-ip>

# Check firewall
iptables -L -n -v
```

---

### Issue: Intermittent Network Drops

**Symptoms**:
- Network connection drops randomly
- RDP sessions disconnect
- High packet loss

**Solutions**:

**Solution 1: Disable Network Adapter Power Management**
```powershell
# Disable power saving
$Adapter = Get-NetAdapter | Where-Object {$_.Status -eq "Up"}
$Adapter | Set-NetAdapterPowerManagement -SelectiveSuspend Disabled

# Disable in Device Manager
$DeviceID = (Get-WmiObject Win32_NetworkAdapter | Where-Object {$_.NetEnabled -eq $true}).PNPDeviceID
$PowerMgmt = Get-WmiObject MSPower_DeviceEnable -Namespace root\wmi | Where-Object {$_.InstanceName -match [regex]::Escape($DeviceID)}
$PowerMgmt.Enable = $false
$PowerMgmt.Put()
```

**Solution 2: Enable MSI Interrupts**
```powershell
# Run MSI configuration script
C:\h2kvm\performance\msi-verify.ps1

# Or manually enable
$RegPath = "HKLM:\SYSTEM\CurrentControlSet\Services\netkvm\Parameters\InterruptManagement\MessageSignaledInterruptProperties"
Set-ItemProperty -Path $RegPath -Name "MSISupported" -Value 1 -Type DWord
Restart-Computer
```

**Solution 3: Adjust TX/RX Buffers**
```powershell
# Increase buffer sizes
Set-NetAdapterAdvancedProperty -Name "Ethernet" -DisplayName "Receive Buffers" -DisplayValue 2048
Set-NetAdapterAdvancedProperty -Name "Ethernet" -DisplayName "Transmit Buffers" -DisplayValue 2048
```

---

## Performance Issues

### Issue: High CPU Usage

**Diagnostic Steps**:

```powershell
# Check CPU usage
Get-Counter '\Processor(_Total)\% Processor Time'

# Find top processes
Get-Process | Sort-Object CPU -Descending | Select-Object -First 10 ProcessName, CPU, WS

# Check for specific issues
Get-Service | Where-Object {$_.Status -eq "Running" -and $_.Name -match "Windows Search|Windows Update"}
```

**Solutions**:

**Solution 1: Disable Unnecessary Services**
```powershell
# Disable Windows Search (if not needed)
Stop-Service WSearch
Set-Service WSearch -StartupType Disabled

# Disable Windows Update (temporarily)
Stop-Service wuauserv
Set-Service wuauserv -StartupType Manual
```

**Solution 2: Adjust CPU Affinity on Host**
```bash
# Pin VM vCPUs to specific host CPUs
virsh vcpupin windows-server 0 0-1
virsh vcpupin windows-server 1 2-3
```

---

### Issue: High Memory Usage

**Diagnostic Steps**:

```powershell
# Check memory usage
Get-Counter '\Memory\Available MBytes'
Get-Counter '\Memory\% Committed Bytes In Use'

# Find memory-hungry processes
Get-Process | Sort-Object WS -Descending | Select-Object -First 10 ProcessName, WS
```

**Solutions**:

**Solution 1: Configure VirtIO Balloon**
```powershell
# Verify balloon driver loaded
Get-Service balloon

# Check balloon configuration
Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\balloon\Parameters"

# On KVM host, adjust balloon
virsh qemu-monitor-command windows-server --hmp "info balloon"
virsh qemu-monitor-command windows-server --hmp "balloon 2048"
```

**Solution 2: Increase VM Memory**
```bash
# Shutdown VM
virsh shutdown windows-server

# Edit memory
virsh setmaxmem windows-server 8G --config
virsh setmem windows-server 8G --config

# Start VM
virsh start windows-server
```

---

## Application Compatibility Issues

### Issue: Application Fails to Start After Migration

**Diagnostic Steps**:

1. Review compatibility report:
   ```bash
   cat /data/kvm/compatibility-report.md
   ```

2. Check application event logs:
   ```powershell
   Get-EventLog -LogName Application -Source <AppName> -Newest 50
   ```

3. Verify dependencies:
   ```powershell
   # Check .NET Framework
   Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\NET Framework Setup\NDP' -Recurse

   # Check Visual C++ Redistributables
   Get-WmiObject Win32_Product | Where-Object {$_.Name -like "*Visual C++*"}
   ```

**Solutions by Application Type**:

**Hardware-Locked Applications (AutoCAD, SolidWorks, etc.)**:
1. Contact vendor for license transfer
2. Provide new hardware ID
3. Request license reactivation

**License Server Applications**:
```powershell
# Verify license server connectivity
Test-NetConnection license-server.company.com -Port 27000

# Reconfigure license server
# (Application-specific, check vendor documentation)
```

**SQL Server Issues**:
```powershell
# Run reconfiguration script
sqlcmd -S localhost -E -i C:\h2kvm\appcompat\sql-reconfigure.sql

# Update server name in SQL
sp_dropserver '<old-server-name>'
GO
sp_addserver '<new-server-name>', local
GO

# Restart SQL Server
Restart-Service MSSQLSERVER
```

**Hardware Dongle Applications**:
```bash
# On KVM host, attach USB dongle
lsusb  # Find dongle

# Configure USB passthrough (see USB Devices section above)
```

---

## Storage and Filesystem Issues

### Issue: Disk Space Missing After Migration

**Symptoms**:
- Available disk space less than expected
- Partition size doesn't match disk size

**Solutions**:

**Solution 1: Extend Partition**
```powershell
# Check disk configuration
Get-Partition
Get-Volume

# Extend partition
$Partition = Get-Partition -DriveLetter C
$MaxSize = (Get-PartitionSupportedSize -DiskNumber $Partition.DiskNumber -PartitionNumber $Partition.PartitionNumber).SizeMax
Resize-Partition -DiskNumber $Partition.DiskNumber -PartitionNumber $Partition.PartitionNumber -Size $MaxSize
```

**Solution 2: Expand qcow2 on Host**
```bash
# Expand qcow2 file
qemu-img resize windows-server.qcow2 +50G

# Boot Windows and extend partition (see Solution 1)
```

---

## Security and Access Issues

### Issue: Cannot Login - "User account is disabled"

**Solutions**:

```powershell
# Boot to Safe Mode or use local account

# Enable disabled user
Enable-LocalUser -Name "Administrator"

# Reset password if needed
Set-LocalUser -Name "Administrator" -Password (ConvertTo-SecureString "NewPassword123!" -AsPlainText -Force)
```

---

### Issue: BitLocker Recovery Required

**Symptoms**:
- BitLocker recovery key prompt on boot
- "Enter recovery key for this drive"

**Solutions**:

**Solution 1: Suspend BitLocker Before Migration**
```powershell
# On source VM before migration
Suspend-BitLocker -MountPoint "C:" -RebootCount 0
```

**Solution 2: Enter Recovery Key**
```powershell
# If you have the recovery key
# Enter at boot prompt

# Disable BitLocker after accessing
Disable-BitLocker -MountPoint "C:"
```

**Solution 3: Use Recovery Key from AD**
```powershell
# On domain controller
Get-ADObject -Filter {objectClass -eq 'msFVE-RecoveryInformation'} -SearchBase "<computer-dn>" -Properties msFVE-RecoveryPassword
```

---

## Escalation Procedures

When troubleshooting is unsuccessful:

1. **Collect diagnostic information**:
   ```bash
   # On Windows guest
   msinfo32 /report C:\systeminfo.txt
   Get-EventLog -LogName System -Newest 100 | Export-Csv C:\system-events.csv
   Get-EventLog -LogName Application -Newest 100 | Export-Csv C:\app-events.csv

   # On KVM host
   virsh dumpxml windows-server > vm-config.xml
   journalctl -u libvirtd -n 500 > libvirt-log.txt
   ```

2. **Create support bundle**:
   ```bash
   tar -czf support-$(date +%Y%m%d).tar.gz \
     /var/log/h2kvm/*.log \
     vm-config.xml \
     libvirt-log.txt \
     systeminfo.txt \
     *-events.csv
   ```

3. **Open support ticket** with collected logs

---

## Additional Resources

- [Windows Migration Guide](./windows-migration-guide.md)
- [Windows Configuration Schema](../reference/windows-configuration-schema.md)
- [Microsoft Support](https://support.microsoft.com)
- [Red Hat VirtIO Drivers](https://access.redhat.com/articles/2470791)
- **VirtIO ISO standard path**: `/var/lib/h2kvm/virtio-win.iso` (install with `sudo ./scripts/install-deps.sh --virtio-win`)

---

**Version**: v0.5.0
**Last Updated**: 2026-03-29
