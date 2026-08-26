#  Installation Guide (Fedora)

This document describes a **clean, RPM-first installation** on Fedora for VMware → KVM workflows, covering both:

 **Control plane**

* vSphere APIs, inventory, orchestration
* `pyvmomi`, `govc`, optional `ovftool`

 **Data plane**

* High-performance disk access via **VMware VDDK**
* `libvixDiskLib.so`

---

###  Philosophy

This project is intentionally **not** “click migrate and pray”.

The goals:

*  keep Python **boring and deterministic** (Fedora RPMs)
*  install **system compatibility libraries first**
*  isolate **proprietary VMware tooling** under `/opt`
*  avoid runtime surprises, ABI mismatches, and loader errors

If something *can* fail at runtime, we make it impossible to reach that state.

---

## 🧩 1. Supported Platform

* 🐧 Fedora **43+** (tested on Fedora 43)
* 🐍 Python **3.x** (system Python)
* 🔐 Root access for system installs
* 🛡️ SELinux enforcing (supported)
* 📦 libguestfs + Python bindings (recommended — auto-used for LVM/LUKS disks)
  * Fedora/RHEL: `sudo dnf install libguestfs-tools python3-libguestfs`
  * Ubuntu/Debian: `sudo apt install libguestfs-tools python3-guestfs`

---

##  2. Required System Compatibility Libraries (Install First)

Modern Fedora intentionally removes legacy libraries that
⚠️ **VMware-provided binaries still depend on**.

Install these **before any VMware tooling**:

```bash
sudo dnf install -y \
  libxcrypt-compat \
  libnsl
```

### Why this matters

These packages provide:

* `libcrypt.so.1` → required by `ovftool.bin`
* legacy NSS / RPC symbols used by VMware tools

Installing them up front ensures you **never see** errors like:

```text
error while loading shared libraries: libcrypt.so.1: cannot open shared object file
```

Optional sanity check:

```bash
ldconfig -p | grep libcrypt.so.1
```

🟢 If it shows up, you’re future-proofed.

---

## 🐍 3. Python Dependencies (Fedora RPMs – Recommended)

All required Python libraries are available as **official Fedora RPMs**
and should be installed system-wide.

###  Install

```bash
sudo dnf install -y \
  python3-rich \
  python3-termcolor \
  python3-watchdog \
  python3-pyyaml \
  python3-requests \
  python3-pyvmomi
```

###  What gets installed

* `python3-rich` – structured logging, progress bars, TUI output
* `python3-termcolor` – ANSI color helpers
* `python3-watchdog` – filesystem event monitoring (inotify)
* `python3-PyYAML` – YAML parsing
* `python3-requests` – HTTP client
* `python3-pyvmomi` – VMware vSphere API SDK

Fedora automatically pulls safe dependencies such as:

* `python3-markdown-it-py`, `python3-mdurl`
* `python3-pygments`

🚫 No `pip`.
🚫 No wheels.
🚫 No ABI drift.

---

## ✅ 4. Verify Python Installation (System Python)

Run the following using **system Python (no virtualenv)**:

```bash
python3 - <<'EOF'
import rich
import termcolor
import watchdog
import yaml
import requests
import pyVmomi

print("✅ All system RPM imports OK")
print("pyVmomi version:", pyVmomi.__version__)
EOF
```

Expected:

* ✔ no tracebacks
* ✔ `pyVmomi` reports `8.0.x`

---

## 🧭 5. Control Plane: `govc` (govmomi CLI)

`govc` is the preferred **open-source control-plane tool** for vSphere:

* 🔎 inventory and discovery
* 🗄️ datastore operations
* 🔁 VM lifecycle management
* ⚡ fast, scriptable CLI access

### 📥 Install govc

Download from:

👉 [https://github.com/vmware/govmomi/releases](https://github.com/vmware/govmomi/releases)

Example:

```bash
curl -LO https://github.com/vmware/govmomi/releases/download/v0.44.0/govc_Linux_x86_64.tar.gz
tar -xzf govc_Linux_x86_64.tar.gz
sudo install -m 0755 govc /usr/local/bin/govc
```

###  Verify

```bash
which govc
govc version
```

### 🤝 How it fits

* `govc` → fast CLI, bulk ops, visibility
* `pyvmomi` → Python orchestration and automation

They are complementary, not redundant.

---

##  6. Optional Tool: VMware OVF Tool (`ovftool`)

VMware **OVF Tool** is an **optional**, proprietary utility used for:

* exporting OVF / OVA directly from vCenter or ESXi
* vendor-supported packaging of VM metadata and disks

Policy in this project:

* 🟢 `govc` is the **default**
* 🟡 `ovftool` is **opt-in**
* 🔴 never required

---

### 📥 6.1 Download OVF Tool (ZIP)

Download the Linux ZIP archive from Broadcom:

👉 [https://developer.broadcom.com/tools/open-virtualization-format-ovf-tool/latest](https://developer.broadcom.com/tools/open-virtualization-format-ovf-tool/latest)

File name will resemble:

```text
VMware-ovftool-4.x.y-lin.x86_64.zip
```

---

### 🗂️ 6.2 Install ovftool (ZIP-based, Deterministic)

Extract directly under `/opt`:

```bash
sudo mkdir -p /opt/ovftool
sudo unzip VMware-ovftool-*-lin.x86_64.zip -d /opt/ovftool
sudo chmod -R a+rX /opt/ovftool
```

Resulting layout:

```text
/opt/ovftool/
  ├── ovftool
  ├── ovftool.bin
  ├── lib/
  └── env/
```

✔ No system pollution
✔ No installers
✔ Fully auditable

---

### 🔗 6.3 Add ovftool to PATH

```bash
sudo ln -s /opt/ovftool/ovftool /usr/local/bin/ovftool
```

Verify:

```bash
ovftool --version
```

Expected:

```text
VMware ovftool 4.x.y (build-xxxxxx)
```

Because compatibility libraries were installed first,
🟢 **no loader errors will occur**.

---

##  7. Data Plane: VMware VDDK (libvixDiskLib)

For **high-performance VMDK access** (snapshots, block-level reads),
install **VMware VDDK**.

> Fedora does not ship VDDK. This is expected.

### 📥 Download

👉 [https://developer.broadcom.com/sdks/vmware-virtual-disk-development-kit-vddk/latest](https://developer.broadcom.com/sdks/vmware-virtual-disk-development-kit-vddk/latest)
(Tested with **VDDK 9.0.0.0**)

---

### 🗂️ Install Layout

```bash
sudo mkdir -p /opt/vmware
sudo tar -xzf VMware-vix-disklib-*.tar.gz -C /opt/vmware
```

Result:

```text
/opt/vmware/vmware-vix-disklib/
  ├── bin/
  ├── lib64/
  │   ├── libvixDiskLib.so
  │   ├── libvixDiskLib.so.7
  │   ├── libvixDiskLib.so.6
  │   └── libvixDiskLib.so.5
```

---

### 🔗 Register Libraries

```bash
echo "/opt/vmware/vmware-vix-disklib/lib64" | sudo tee /etc/ld.so.conf.d/vmware-vddk.conf
sudo ldconfig
```

Verify:

```bash
ldconfig -p | grep vixDiskLib
```

---

## 🌍 8. Environment Variables (When Required)

Some workflows require explicit paths:

```bash
export VIXDISKLIB_DIR=/opt/vmware/vmware-vix-disklib
export LD_LIBRARY_PATH=/opt/vmware/vmware-vix-disklib/lib64:$LD_LIBRARY_PATH
```

Persist if needed:

```bash
sudo tee /etc/profile.d/vddk.sh <<'EOF'
export VIXDISKLIB_DIR=/opt/vmware/vmware-vix-disklib
export LD_LIBRARY_PATH=/opt/vmware/vmware-vix-disklib/lib64:$LD_LIBRARY_PATH
EOF
```

---

##  9. Design Rationale

*  **RPMs for Python** – ABI-safe, reproducible, SELinux-friendly
* 🧭 **govc** – open-source, fast, default control plane
*  **ovftool** – optional, proprietary, isolated under `/opt`
*  **VDDK** – explicit data-plane dependency
*  **compat libs first** – no runtime failures, no guesswork

This mirrors **real production VMware tooling layouts**.

---

## 🎉 10. Summary

✔ System compatibility libraries installed **first**
✔ Fedora RPMs for all Python dependencies
✔ `pyvmomi` verified on system Python
✔ `govc` installed for control-plane operations
✔ `ovftool` ZIP installed cleanly under `/opt`
✔ VDDK installed and registered for data-plane access
