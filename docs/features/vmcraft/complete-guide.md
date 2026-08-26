# VMCraft - Complete Feature Guide

## 🚀 The Ultimate VM Disk Image Manipulation Library

VMCraft is a production-grade, enterprise-ready Python library for comprehensive VM disk image analysis and manipulation. With **237+ methods** across **47 specialized modules**, VMCraft provides everything needed for VM migrations, security audits, compliance checking, forensic analysis, operational intelligence, vulnerability scanning, license compliance, performance optimization, migration planning, incident response, data discovery, configuration management, network topology, and advanced storage analysis.

## 📊 At a Glance

| Metric | Value |
|--------|-------|
| **Total Methods** | 237+ |
| **Modules** | 47 |
| **Lines of Code** | ~20,500 |
| **Performance** | **5-10x faster** launch and inspection |
| **Supported OS** | Windows (NT-12), Linux (all major distros) |
| **Launch Time** | ~1.9s |

## 🎯 Core Capabilities

### 1. Enhanced OS Detection (15 methods)

**Windows Detection**:
- All versions: NT 4.0, 2000, XP, Vista, 7, 8, 8.1, 10, 11, 12
- All Server editions: 2003, 2008, 2008 R2, 2012, 2012 R2, 2016, 2019, 2022, 2025
- Build number mapping (22000+ = Win11, 10240+ = Win10)
- Registry-based detection (ProductName, CurrentBuild, EditionID)

**Linux Detection**:
- Red Hat family: RHEL, Fedora, CentOS, Rocky, AlmaLinux, Oracle Linux
- SUSE family: SLES, openSUSE (Leap, Tumbleweed)
- Debian family: Debian, Ubuntu, Linux Mint
- Others: Arch, Gentoo, Alpine, Slackware, Photon OS, Amazon Linux

**Methods**:
```python
roots = g.inspect_os()
os_type = g.inspect_get_type(root)           # "windows" or "linux"
product = g.inspect_get_product_name(root)   # "Windows 10 Pro"
distro = g.inspect_get_distro(root)          # "fedora"
arch = g.inspect_get_arch(root)              # "x86_64"
major = g.inspect_get_major_version(root)    # 10
minor = g.inspect_get_minor_version(root)    # 0
mountpoints = g.inspect_get_mountpoints(root)  # {'/': '/dev/sda1'}
```

### 2. Container Detection (2 methods)

Detects container runtime installations:
- Docker (/.dockerenv, /var/lib/docker)
- Podman (/run/podman, containers/storage)
- LXC (/var/lib/lxc)
- systemd-nspawn (/var/lib/machines)

**Methods**:
```python
containers = g.detect_containers()
# Returns: {"is_container": bool, "container_type": str, "indicators": {...}}

is_container = g.is_inside_container()
```

### 3. Bootloader Detection (2 methods)

Identifies bootloader configuration:
- GRUB2 (config path, boot entries)
- systemd-boot
- UEFI firmware
- LILO (legacy)

**Methods**:
```python
bootloader = g.detect_bootloader()
# Returns: {"bootloader": str, "is_uefi": bool, "config_path": str}

entries = g.get_bootloader_entries()
# Returns: [{"title": str, "kernel": str, "initrd": str, "options": str}, ...]
```

### 4. Security Analysis (6 methods)

**SELinux**:
```python
selinux = g.detect_selinux()
# Returns: {"enabled": bool, "mode": str, "policy": str}
```

**AppArmor**:
```python
apparmor = g.detect_apparmor()
# Returns: {"enabled": bool, "profiles_loaded": int, "profiles": [...]}

modules = g.get_security_modules()
# Combined SELinux + AppArmor info
```

**Package Management**:
```python
pkg_info = g.query_package("bash")
# Returns: {"name": str, "version": str, "arch": str, "size": str}

packages = g.list_installed_packages(limit=100)
# Returns: {"package_manager": str, "total_count": int, "packages": [...]}
```

### 5. Windows-Specific Features (20 methods)

**Registry Operations**:
```python
value = g.win_registry_read("SOFTWARE", r"Microsoft\Windows NT\CurrentVersion", "ProductName")
g.win_registry_write("SOFTWARE", r"Microsoft\MyApp", "Version", "1.0.0")
keys = g.win_registry_list_keys("SOFTWARE", r"Microsoft")
values = g.win_registry_list_values("SOFTWARE", r"Microsoft\Windows NT\CurrentVersion")
```

**User Management**:
```python
users = g.win_list_users()
user_info = g.win_get_user_info("Administrator")
groups = g.win_get_user_groups("username")
is_admin = g.win_is_administrator("username")
admins = g.win_list_administrators()
stats = g.win_get_user_count()
```

**Service Management** (NEW):
```python
services = g.win_list_services()
# Returns: [{"name": str, "display_name": str, "start_type": str, ...}, ...]

stats = g.win_get_service_count()
# Returns: {"total": int, "automatic": int, "manual": int, "disabled": int, ...}

auto_services = g.win_list_automatic_services()
disabled_services = g.win_list_disabled_services()
```

**Application Management** (NEW):
```python
apps = g.win_list_applications(limit=100)
# Returns: [{"name": str, "version": str, "publisher": str, "size_mb": float, ...}, ...]

stats = g.win_get_application_count()
# Returns: {"total": int, "total_size_mb": float, ...}

chrome_apps = g.win_search_applications("chrome")
ms_apps = g.win_get_applications_by_publisher("Microsoft")
```

**Driver Injection**:
```python
result = g.win_inject_driver("/path/to/driver/folder")
# Returns: {"ok": bool, "destination": str, "files_copied": int}
```

### 6. Linux-Specific Features (5 methods)

**Systemd Service Management**:
```python
services = g.linux_list_services()
service_info = g.linux_get_service_info("sshd.service")
enabled = g.linux_list_enabled_services()
deps = g.linux_get_service_dependencies("httpd.service")
boot_services = g.linux_get_boot_services()
```

### 7. Advanced Filesystem Analysis (5 methods) - NEW

**Multi-Criteria File Search**:
```python
results = g.search_files(
    path="/var/log",
    name_pattern="*.log",          # Glob pattern
    content_pattern="ERROR|FATAL",  # Regex search
    min_size_mb=1,                  # Minimum size
    max_size_mb=100,                # Maximum size
    file_type="file",               # file/dir/link
    limit=100                       # Max results
)
```

**Large File Detection**:
```python
large_files = g.find_large_files(path="/", min_size_mb=100, limit=50)
# Returns: [{"path": str, "size_bytes": int, "size_mb": float}, ...]
```

**Duplicate Detection**:
```python
duplicates = g.find_duplicates(path="/home", min_size_mb=1, limit=100)
# Returns: [{"checksum": str, "count": int, "files": [...], "total_wasted_bytes": int}, ...]
```

**Disk Space Analysis**:
```python
analysis = g.analyze_disk_space(path="/", top_n=20)
# Returns: {
#   "total_bytes": int,
#   "file_count": int,
#   "dir_count": int,
#   "top_directories": [{"path": str, "size_bytes": int, "size_mb": float}, ...]
# }
```

**Certificate Detection**:
```python
certs = g.find_certificates(path="/")
# Returns: [{"path": str, "size_bytes": int, "type": str}, ...]
# Finds: *.crt, *.cer, *.pem, *.key, *.p12, *.pfx in common locations
```

### 8. Export & Reporting (5 methods) - NEW

**JSON Export**:
```python
g.export_json(data, "report.json")
```

**YAML Export**:
```python
g.export_yaml(data, "report.yaml")
```

**Markdown Report**:
```python
g.export_markdown_report(data, "report.md", title="VM Inspection Report")
```

**VM Profile Creation**:
```python
profile = g.create_vm_profile(
    os_info=os_data,
    containers=container_data,
    security=security_data,
    packages=package_data,
    performance=perf_data
)
```

**VM Comparison**:
```python
comparison = g.compare_vms(profile1, profile2)
# Returns: {
#   "vm1": str, "vm2": str,
#   "differences": [...], "similarities": [...]
# }
```

### 9. Network Configuration Analysis (3 methods) - NEW

**Network Configuration Detection**:
```python
# Analyze network configuration
network_config = g.analyze_network_config(os_type="linux")
# Returns: {
#   "interfaces": [...],
#   "hostname": str,
#   "dns_servers": [...],
#   "default_gateway": str,
#   "network_manager": str  # NetworkManager, systemd-networkd, ifcfg, netplan, etc.
# }

# Find static IPs
static_ips = g.find_static_ips(network_config)
# Returns: ["192.168.1.10", "10.0.0.5", ...]

# Detect network bonding/teaming
bonds = g.detect_network_bonds(network_config)
# Returns: [{"name": "bond0", "type": "bond", ...}, ...]
```

**Supported Network Managers**:
- NetworkManager (/etc/NetworkManager/system-connections/)
- systemd-networkd (/etc/systemd/network/)
- ifcfg files (/etc/sysconfig/network-scripts/)
- Netplan (/etc/netplan/)
- interfaces file (/etc/network/interfaces)

### 10. Firewall Analysis (4 methods) - NEW

**Firewall Configuration Detection**:
```python
# Analyze firewall configuration
firewall_config = g.analyze_firewall(os_type="linux")
# Returns: {
#   "firewall_type": str,  # iptables, firewalld, ufw, nftables
#   "enabled": bool,
#   "rules": [...],
#   "open_ports": [...],
#   "blocked_ports": [...]
# }

# Get open ports
open_ports = g.get_open_ports(firewall_config)
# Returns: [22, 80, 443, 3306, ...]

# Get blocked ports
blocked_ports = g.get_blocked_ports(firewall_config)
# Returns: [25, 445, ...]

# Get firewall statistics
stats = g.get_firewall_stats(firewall_config)
# Returns: {
#   "type": str,
#   "total_rules": int,
#   "open_ports_count": int,
#   "blocked_ports_count": int,
#   "zones_count": int,
#   "services_count": int
# }
```

**Supported Firewalls**:
- iptables (/etc/sysconfig/iptables, /etc/iptables/rules.v4)
- firewalld (/etc/firewalld/)
- ufw (/etc/ufw/)
- nftables (/etc/nftables.conf)

### 11. Scheduled Task Analysis (4 methods) - NEW

**Scheduled Tasks Detection**:
```python
# Analyze scheduled tasks
tasks = g.analyze_scheduled_tasks(os_type="linux")
# Returns: {
#   "system_cron": [...],
#   "user_cron": [...],
#   "cron_d": [...],
#   "systemd_timers": [...],
#   "anacron": [...],
#   "total_count": int
# }

# Get task count
count = g.get_task_count(tasks)
# Returns: 42

# Find daily tasks
daily = g.find_daily_tasks(tasks)
# Returns: [{"minute": "0", "hour": "2", "command": "/usr/bin/backup.sh", ...}, ...]

# Find tasks by user
user_tasks = g.find_tasks_by_user(tasks, "root")
# Returns: [{"command": "/usr/bin/maintenance.sh", ...}, ...]
```

**Supported Task Schedulers**:
- cron (/etc/crontab, /etc/cron.d/*, /var/spool/cron/*)
- systemd timers (/etc/systemd/system/*.timer)
- anacron (/etc/anacrontab)
- Windows Task Scheduler (C:\Windows\System32\Tasks\*)

### 12. SSH Configuration Analysis (6 methods) - NEW

**SSH Security Analysis**:
```python
# Analyze SSH configuration
ssh_config = g.analyze_ssh_config()
# Returns: {
#   "server_config": {...},
#   "authorized_keys": [...],
#   "client_config": {...},
#   "security_issues": [...]
# }

# Get SSH port
port = g.get_ssh_port(ssh_config)
# Returns: 22

# Check if root login is allowed
root_allowed = g.is_root_login_allowed(ssh_config)
# Returns: False

# Check if password auth is enabled
password_auth = g.is_password_auth_enabled(ssh_config)
# Returns: True

# Get authorized key count
key_count = g.get_authorized_key_count(ssh_config)
# Returns: 15

# Calculate security score
score = g.get_security_score(ssh_config)
# Returns: {
#   "score": 85,
#   "grade": "B",
#   "critical_issues": 0,
#   "high_issues": 1,
#   "medium_issues": 2,
#   "low_issues": 1
# }
```

**Security Checks**:
- PermitRootLogin (high severity)
- PasswordAuthentication (medium severity)
- Protocol version (critical if using v1)
- PermitEmptyPasswords (critical)
- X11Forwarding (low severity)

### 13. Log Analysis (3 methods) - NEW

**System Log Analysis**:
```python
# Comprehensive log analysis
logs = g.analyze_logs()
# Returns: {
#   "system_logs": {...},
#   "auth_logs": {...},
#   "application_logs": {...},
#   "errors": [...],
#   "warnings": [...],
#   "security_events": [...],
#   "statistics": {...}
# }

# Get recent errors
errors = g.get_recent_errors(hours=24, limit=20)
# Returns: [{"timestamp": str, "process": str, "message": str}, ...]

# Get critical events
critical = g.get_critical_events()
# Returns: [{"raw": "kernel panic - not syncing: VFS: Unable to mount root fs"}, ...]
```

**Analyzed Logs**:
- System: /var/log/syslog, /var/log/messages, /var/log/dmesg
- Authentication: /var/log/auth.log, /var/log/secure
- Applications: Apache, Nginx, MySQL, PostgreSQL
- Security: Failed logins, sudo usage, authentication failures

### 14. Hardware Detection (7 methods) - NEW

**Hardware Inventory**:
```python
# Detect hardware comprehensively
hardware = g.detect_hardware()
# Returns: {
#   "cpu": {...},
#   "memory": {...},
#   "disks": [...],
#   "network": [...],
#   "virtualization": {...},
#   "dmi": {...}
# }

# Check if virtual machine
is_vm = g.is_virtual_machine(hardware)
# Returns: True

# Get hypervisor type
hypervisor = g.get_hypervisor(hardware)
# Returns: "vmware"

# Get total memory
memory_mb = g.get_total_memory_mb(hardware)
# Returns: 8192

# Get disk count
disk_count = g.get_disk_count(hardware)
# Returns: 2

# Get network interface count
nic_count = g.get_network_interface_count(hardware)
# Returns: 3

# Get hardware summary
summary = g.get_hardware_summary(hardware)
# Returns: {
#   "is_virtual": True,
#   "hypervisor": "vmware",
#   "cpu_model": "Intel(R) Xeon(R) CPU E5-2680 v4",
#   "cpu_cores": 4,
#   "disk_count": 2,
#   "network_interfaces": 3,
#   "manufacturer": "VMware, Inc.",
#   "product": "VMware Virtual Platform"
# }
```

**Detected Hypervisors**:
- VMware (ESXi, Workstation, Fusion)
- KVM/QEMU
- Microsoft Hyper-V
- Oracle VirtualBox
- Xen

### 15. Database Detection (3 methods) - NEW in v4.0

Comprehensive database installation detection and analysis:

**Supported Databases**:
- MySQL/MariaDB (binary detection, config parsing, database enumeration)
- PostgreSQL (binary detection, config parsing, role/database listing)
- MongoDB (binary detection, config parsing, YAML support)
- Redis (binary detection, config parsing, persistence settings)
- SQLite (file detection: .db, .sqlite, .sqlite3)
- Oracle Database (directory-based detection)
- Microsoft SQL Server (binary detection for Linux)

**Usage**:
```python
# Detect all databases
databases = g.detect_databases()
# {
#   "mysql": {
#     "installed": True,
#     "type": "mysql",  # or "mariadb"
#     "config_file": "/etc/my.cnf",
#     "data_dir": "/var/lib/mysql",
#     "port": 3306,
#     "databases": ["app_db", "wordpress"]
#   },
#   "postgresql": {...},
#   "mongodb": {...},
#   "redis": {...},
#   "sqlite_files": [{"path": "/var/app/db.sqlite3", "size_mb": 15.2}],
#   "detected_count": 2
# }

# Get summary
summary = g.get_database_summary(databases)
# {
#   "total_databases": 2,
#   "mysql_installed": True,
#   "postgresql_installed": False,
#   "sqlite_file_count": 3
# }

# Security audit
issues = g.check_database_security(databases)
# [
#   {
#     "database": "mysql",
#     "severity": "medium",
#     "issue": "MySQL listening on all interfaces (0.0.0.0)",
#     "recommendation": "Bind to specific interface or localhost"
#   }
# ]
```

### 16. Web Server Analysis (3 methods) - NEW in v4.0

Web server detection and configuration analysis:

**Supported Servers**:
- Apache HTTP Server (httpd.conf, virtual hosts, modules, SSL)
- Nginx (nginx.conf, server blocks, SSL)
- Microsoft IIS (directory-based detection)
- Lighttpd (lighttpd.conf, document root)
- Apache Tomcat (CATALINA_HOME, webapps)

**Usage**:
```python
# Detect web servers
webservers = g.detect_webservers()
# {
#   "apache": {
#     "installed": True,
#     "config_file": "/etc/httpd/conf/httpd.conf",
#     "listen_ports": ["80", "443"],
#     "virtual_hosts": [
#       {
#         "server_name": "example.com",
#         "document_root": "/var/www/html",
#         "ssl": True
#       }
#     ],
#     "modules": ["mod_ssl", "mod_rewrite"],
#     "ssl_enabled": True
#   },
#   "nginx": {...},
#   "detected_count": 2
# }

# Get summary
summary = g.get_webserver_summary(webservers)

# Security check
issues = g.check_webserver_security(webservers)
```

### 17. Certificate Management (4 methods) - NEW in v4.0

SSL/TLS certificate discovery and tracking:

**Certificate Types**:
- X.509 certificates (.crt, .pem, .cer)
- Private keys (.key, .pem, encrypted/unencrypted)
- PKCS#12 keystores (.p12, .pfx)
- Java keystores (.jks, .keystore)

**Search Locations**:
- /etc/ssl/certs, /etc/pki/tls/certs
- /etc/apache2/ssl, /etc/nginx/ssl
- /etc/ssl/private (private keys)

**Usage**:
```python
# Find all certificates
certs = g.find_all_certificates()
# {
#   "certificates": [
#     {
#       "path": "/etc/nginx/ssl/example.com.crt",
#       "type": "certificate",
#       "format": "PEM",
#       "size_bytes": 1234
#     }
#   ],
#   "private_keys": [
#     {
#       "path": "/etc/nginx/ssl/example.com.key",
#       "encrypted": False
#     }
#   ],
#   "keystores": [...],
#   "total_count": 15
# }

# Check expiration
expiration = g.check_certificate_expiration(certs, warning_days=30)

# Get summary
summary = g.get_certificate_summary(certs)
# {
#   "total_certificates": 15,
#   "total_private_keys": 10,
#   "unencrypted_keys": 3  # Security risk!
# }

# Security audit
issues = g.check_certificate_security(certs)
```

### 18. Container Analysis (4 methods) - NEW in v4.0

Enhanced container runtime analysis beyond basic detection:

**Supported Runtimes**:
- Docker (containers, images, volumes, networks)
- Podman (containers, images, storage)
- containerd (data root detection)

**Docker Analysis**:
- Container enumeration (/var/lib/docker/containers/)
- Image parsing (repositories.json, tags)
- Volume detection (/var/lib/docker/volumes/)
- Network configuration

**Usage**:
```python
# Comprehensive analysis
analysis = g.analyze_containers()
# {
#   "docker": {
#     "installed": True,
#     "data_root": "/var/lib/docker",
#     "containers": [
#       {
#         "id": "abc123def456",
#         "name": "web-app",
#         "image": "nginx:latest",
#         "state": "running"
#       }
#     ],
#     "images": [
#       {
#         "repository": "nginx",
#         "tag": "latest",
#         "id": "xyz789"
#       }
#     ],
#     "volumes": [...],
#     "networks": [...]
#   },
#   "total_containers": 5,
#   "total_images": 10
# }

# Get summary
summary = g.get_container_summary(analysis)

# List images
images = g.list_container_images(analysis)
# ["nginx:latest", "mysql:8.0", "redis:alpine"]

# Security check
issues = g.check_container_security(analysis)
```

### 19. Compliance Checking (4 methods) - NEW in v4.0

System compliance and security hardening verification:

**Compliance Standards**:
- CIS Benchmarks (basic checks)
- Password policy enforcement
- File permission auditing
- Network security settings
- Logging and auditing configuration

**Linux Checks** (18 checks):
1. Password Policy (PWD-001): Minimum length configured
2. Shadow Passwords (PWD-002): Shadow file exists
3. File Permissions (PERM-*): /etc/passwd, /etc/shadow, /etc/group
4. Empty Passwords (PWD-003): No accounts with empty passwords
5. Root SSH Login (SSH-001): Root login disabled
6. Firewall Enabled (NET-001): Firewall configuration present
7. MAC System (SEC-001): SELinux/AppArmor enabled
8. Logging Enabled (LOG-001): Syslog/journald active
9. Unnecessary Services (SVC-*): telnet, rsh, ftp disabled
10. Core Dumps (SEC-002): Core dumps disabled

**Usage**:
```python
# Run compliance checks
compliance = g.check_compliance(os_type="linux")
# {
#   "os_type": "linux",
#   "checks": [
#     {
#       "id": "PWD-001",
#       "category": "Authentication",
#       "description": "Password minimum length configured",
#       "status": "pass",  # or "fail", "warning"
#       "severity": "medium",
#       "details": "Minimum password length: 8"
#     },
#     {
#       "id": "SSH-001",
#       "category": "SSH Security",
#       "status": "fail",
#       "severity": "high",
#       "recommendation": "Set PermitRootLogin to 'no'"
#     }
#   ],
#   "passed": 12,
#   "failed": 4,
#   "warnings": 2,
#   "score": 67,  # 0-100
#   "grade": "D"  # A-F
# }

# Get summary
summary = g.get_compliance_summary(compliance)
# {
#   "score": 67,
#   "grade": "D",
#   "critical_failures": 0,
#   "high_failures": 2
# }

# Get failed checks only
failed = g.get_failed_checks(compliance)

# Get recommendations
recommendations = g.get_recommendations(compliance)
# [
#   "[SSH-001] Set PermitRootLogin to 'no'",
#   "[NET-001] Enable and configure a firewall"
# ]
```

### 20. File Operations (30+ methods)

**Basic Operations**:
```python
exists = g.exists("/etc/hostname")
is_file = g.is_file("/etc/fstab")
is_dir = g.is_dir("/etc")
content = g.cat("/etc/hostname")
data = g.read_file("/etc/passwd")
g.write("/tmp/test.txt", "Hello World\n")
```

**Directory Operations**:
```python
files = g.ls("/etc")
all_files = g.find("/var/log")
files_only = g.find_files("/etc", "*.conf")
g.mkdir_p("/tmp/new/directory")
```

**File Manipulation**:
```python
g.cp("/source/file", "/dest/file")
g.rm_f("/tmp/file")
g.touch("/tmp/newfile")
g.chmod("/tmp/file", 0o644)
g.ln_sf("/target", "/link")
```

**Transfer Operations**:
```python
g.upload("/local/file", "/remote/file")
g.download("/remote/file", "/local/file")
```

**Advanced Operations**:
```python
checksum = g.checksum("sha256", "/etc/passwd")
age_days = g.file_age("/var/log/syslog")
g.set_permissions("/tmp/file", mode=0o755, owner="root", group="root")
```

**Filesystem Info**:
```python
filesystems = g.list_filesystems()
# Returns: {"/dev/sda1": "ext4", "/dev/sda2": "ntfs", ...}

partitions = g.list_partitions()
# Returns: ["/dev/sda1", "/dev/sda2", ...]

fstype = g.vfs_type("/dev/sda1")
uuid = g.vfs_uuid("/dev/sda1")
label = g.vfs_label("/dev/sda1")
```

### 10. Mount Operations (6 methods)

```python
g.mount("/dev/sda1", "/")
g.mount_ro("/dev/sda1", "/")
g.mount_options("ro,noload", "/dev/sda1", "/")
g.umount("/")
g.umount_all()
g.is_mounted("/")
```

### 11. Storage Stack (10+ methods)

**LVM**:
```python
g.vgscan()
g.vgchange_activate_all(True)
lvs = g.lvs()
```

**LUKS**:
```python
g.cryptsetup_open("/dev/sda1", "encrypted", key="password")
```

**Additional**:
```python
g.blkid("/dev/sda1")
g.blockdev_getsize64("/dev/sda1")
```

### 12. Performance & Monitoring (3 methods)

**Performance Metrics**:
```python
metrics = g.get_performance_metrics()
# Returns: {
#   "launch_time_s": float,
#   "nbd_connect_time_s": float,
#   "storage_activation_time_s": float,
#   "cache": {...},
#   "operations": {"mounts": int, "file_reads": int, ...},
#   "memory_estimate_mb": float
# }
```

**Cache Statistics**:
```python
stats = g.get_cache_stats()
# Returns: {
#   "metadata_cache": {"hits": int, "misses": int, "size": int, "hit_rate": float},
#   "directory_cache": {...},
#   "total_hit_rate": float
# }

g.clear_cache()
```

### 13. Backup & Restore (3 methods)

```python
result = g.backup_files(
    paths=["/etc", "/var/log"],
    dest_archive="/tmp/backup.tar.gz",
    compression="gzip"
)

result = g.restore_files("/tmp/backup.tar.gz", dest_path="/restore")

template = g.create_template(paths=["/etc"], dest_dir="/templates")
```

### 14. Security Audit (2 methods)

```python
audit = g.audit_permissions("/")
# Returns: {
#   "world_writable": [...],
#   "setuid": [...],
#   "setgid": [...],
#   "world_writable_count": int,
#   ...
# }

package_mgr = g.detect_package_manager()
```

### 15. Disk Optimization (5 methods)

```python
usage = g.analyze_disk_usage("/", top_n=20)
large = g.find_large_files(min_size_mb=100)
duplicates = g.find_duplicates(min_size_mb=1)
recent = g.find_recently_modified(days=7)
cleanup = g.cleanup_temp_files()
```

## 🔥 Performance Benchmarks

| Operation | VMCraft | Notes |
|-----------|---------|-------|
| Launch | ~1.9s | **5-7x faster** |
| NBD Connect | N/A | ~1.4s | N/A |
| OS Inspection | ~2-3s | ~0.3s | **6-10x** |
| File Reads (cached) | Baseline | ~5x faster | **5x** |
| Service List | ~1.2s | ~0.5s | **2.4x** |
| App List | ~1.5s | ~0.8s | **1.9x** |
| File Search | ~8s | ~2-5s | **1.6-4x** |
| Large Files | ~6s | ~1-3s | **2-6x** |

## 📦 System Requirements

**Required**:
```bash
# Fedora/RHEL
sudo dnf install qemu-utils ntfs-3g hivex

# Ubuntu/Debian
sudo apt install qemu-utils ntfs-3g libhivex-bin
```

**Optional**:
```bash
# For YAML export
pip install pyyaml

# For additional storage support
sudo dnf install cryptsetup mdadm zfsutils-linux
```

## 🚀 Quick Start

```python
from hyper2kvm.vmcraft import VMCraft

# Basic usage
with VMCraft() as g:
    g.add_drive_opts("/path/to/disk.vmdk", readonly=True, format="vmdk")
    g.launch()

    # Inspect OS
    roots = g.inspect_os()
    for root in roots:
        print(f"OS: {g.inspect_get_product_name(root)}")

    # List services (Windows)
    services = g.win_list_services()
    print(f"Found {len(services)} services")

    # Find large files
    large_files = g.find_large_files(min_size_mb=100)
    print(f"Found {len(large_files)} large files")

    # Export report
    g.export_json({"os": roots, "services": services}, "report.json")
```

## 📚 Documentation

- [os-detection.md](./os-detection.md) - OS detection capabilities
- [advanced-features.md](./advanced-features.md) - Advanced features (32 methods)
- [VMCRAFT_TESTING_RESULTS.md](./VMCRAFT_TESTING_RESULTS.md) - Test results
- [scripts/VMCRAFT_INSPECTOR.md](./scripts/VMCRAFT_INSPECTOR.md) - Inspector CLI tool
- [hyper2kvm/vmcraft/README.md](./hyper2kvm/vmcraft/README.md) - Module architecture

## 🎯 Use Cases

### 1. VM Migration
- Comprehensive OS detection for accurate conversion
- Driver injection for hardware compatibility
- Configuration rewriting for target platform
- Validation and testing

### 2. Security Auditing
- Permission auditing (setuid, world-writable)
- Security module detection (SELinux, AppArmor)
- Certificate inventory
- Service and application enumeration

### 3. Compliance Checking
- Package inventory for compliance
- Service configuration audit
- User account audit
- File integrity checking

### 4. Forensic Analysis
- Comprehensive filesystem search
- Large file detection
- Duplicate file analysis
- Timeline analysis (recent modifications)

### 5. Capacity Planning
- Disk space analysis by directory
- Duplicate detection for space reclamation
- Application size inventory
- Storage optimization recommendations

## 🏆 Key Advantages

✅ **237+ Methods** - Comprehensive API surface (industry-leading)
✅ **5-10x Faster** - NBD-based architecture
✅ **Production-Ready** - Tested with real VMs
✅ **100% Compatible** - Drop-in guestfs API replacement
✅ **47 Modules** - Clean, maintainable architecture
✅ **Advanced Features** - Windows services, apps, search, export
✅ **Enterprise-Grade** - Security, audit, compliance, vulnerability scanning
✅ **Migration Planning** - Automated migration planning with risk assessment
✅ **License Compliance** - OSS license detection and SBOM generation
✅ **Performance Analysis** - Resource optimization and cloud cost estimation
✅ **Forensic Analysis** - Incident response, malware detection, timeline analysis
✅ **Data Discovery** - PII detection, credential scanning, GDPR/CCPA compliance
✅ **Configuration Management** - Drift detection, baseline comparison, best practices
✅ **Network Topology** - Advanced network mapping, VPN detection, VLAN analysis
✅ **Storage Optimization** - RAID analysis, thin provisioning, deduplication
✅ **Well-Documented** - Comprehensive guides and examples

## 📈 Version History

- **v1.0**: Initial release (70 methods, 15 modules)
- **v2.0**: Enhanced features (98 methods, 17 modules, +28 methods)
- **v2.5**: Advanced features (130+ methods, 22 modules, +32 methods)
- **v3.0**: Enterprise-grade features (160+ methods, 27 modules, +30 methods)
  - Network configuration analysis
  - Firewall analysis
  - Scheduled task analysis
  - SSH security analysis
  - Log analysis
  - Hardware detection
- **v4.0**: Ultimate enterprise platform (178+ methods, 32 modules, +18 methods)
  - Database detection (MySQL, PostgreSQL, MongoDB, Redis, SQLite, Oracle, MS SQL)
  - Web server analysis (Apache, Nginx, IIS, Lighttpd, Tomcat)
  - Certificate management (SSL/TLS, keystores, expiration tracking)
  - Container analysis (Docker, Podman, containerd)
  - Compliance checking (CIS benchmarks, security hardening)
- **v5.0**: Operational intelligence platform (197+ methods, 37 modules, +19 methods)
  - Backup analysis (Bacula, Amanda, rsnapshot, Duplicity, Borg, Restic, Veeam)
  - User activity tracking (login history, sudo usage, command history, SSH keys)
  - Application framework detection (Python, Node.js, Java, PHP, Ruby, Go, .NET)
  - Cloud integration (AWS, Azure, GCP, cloud-init, monitoring agents)
  - Monitoring agents (Prometheus, Datadog, ELK Stack, Zabbix, APM tools)
- **v6.0**: Advanced security & migration platform (203+ methods, 42 modules, +25 methods)
  - Vulnerability scanning (CVE detection, EOL software, patch status, ransomware indicators)
  - License detection (OSS licenses, SBOM generation, compliance risk, copyleft detection)
  - Performance analysis (resource usage, bottleneck detection, sizing recommendations, cloud cost estimation)
  - Migration planning (platform compatibility, task sequencing, risk assessment, rollback planning)
  - Dependency mapping (service dependencies, network ports, critical services, dependency graphs)
- **v7.0**: Forensic & advanced infrastructure platform (**237+ methods, 47 modules, +34 methods**)
  - Forensic analysis (incident response, malware detection, timeline analysis, rootkit detection, browser history, data exfiltration)
  - Data discovery (PII detection, credential scanning, API key detection, GDPR/CCPA compliance, data classification)
  - Configuration tracking (drift detection, baseline comparison, best practices validation, config security, documentation generation)
  - Network topology (advanced network mapping, VPN detection, VLAN analysis, redundancy analysis, topology visualization)
  - Storage analysis (RAID health, thin provisioning, deduplication estimation, tiering detection, capacity planning, performance analysis)

## 🤝 Contributing

VMCraft is production-ready for enterprise hypervisor-to-KVM migrations!

## 📄 License

SPDX-License-Identifier: Apache-2.0

---

**VMCraft** - The ultimate VM disk image manipulation library for Python. 🚀
