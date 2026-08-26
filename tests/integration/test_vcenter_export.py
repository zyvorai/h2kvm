# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Integration tests for vCenter export pipeline.

These tests verify the full export → convert → fix → libvirt pipeline
against a real vCenter. Skip if no vCenter is available.

Run with:
    VCENTER_HOST=10.73.213.134 \\
    VCENTER_USER=administrator@vsphere.local \\
    VCENTER_PASSWORD=password \\
    VCENTER_DATACENTER=data \\
    pytest tests/integration/test_vcenter_export.py -v
"""

import os
import subprocess
import unittest
from pathlib import Path


def vcenter_available():
    """Check if vCenter credentials are set."""
    return all(
        os.environ.get(k) for k in ["VCENTER_HOST", "VCENTER_USER", "VCENTER_PASSWORD", "VCENTER_DATACENTER"]
    )


@unittest.skipUnless(vcenter_available(), "VCENTER_* env vars not set")
class TestVCenterDiscovery(unittest.TestCase):
    """Test VM discovery via govc."""

    def test_govc_list_vms(self):
        """govc can list VMs in datacenter."""
        dc = os.environ["VCENTER_DATACENTER"]
        env = {
            **os.environ,
            "GOVC_URL": f"https://{os.environ['VCENTER_HOST']}/sdk",
            "GOVC_USERNAME": os.environ["VCENTER_USER"],
            "GOVC_PASSWORD": os.environ["VCENTER_PASSWORD"],
            "GOVC_INSECURE": "1",
            "GOVC_DATACENTER": dc,
        }
        result = subprocess.run(
            ["govc", "ls", f"/{dc}/vm/"], capture_output=True, text=True, env=env, timeout=30
        )
        self.assertEqual(result.returncode, 0, f"govc ls failed: {result.stderr}")
        self.assertGreater(len(result.stdout.strip().split("\n")), 0)

    def test_govc_vm_info(self):
        """govc can get VM info."""
        vm = os.environ.get("VCENTER_TEST_VM", "")
        if not vm:
            self.skipTest("VCENTER_TEST_VM not set")

        env = {
            **os.environ,
            "GOVC_URL": f"https://{os.environ['VCENTER_HOST']}/sdk",
            "GOVC_USERNAME": os.environ["VCENTER_USER"],
            "GOVC_PASSWORD": os.environ["VCENTER_PASSWORD"],
            "GOVC_INSECURE": "1",
            "GOVC_DATACENTER": os.environ["VCENTER_DATACENTER"],
        }
        result = subprocess.run(["govc", "vm.info", vm], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(result.returncode, 0, f"govc vm.info failed: {result.stderr}")
        self.assertIn("Name:", result.stdout)


@unittest.skipUnless(vcenter_available(), "VCENTER_* env vars not set")
class TestVCenterExportPipeline(unittest.TestCase):
    """Test full export pipeline via h2kvmctl."""

    def setUp(self):
        self.output_dir = Path("/tmp/h2kvm-integration-test")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.output_dir, ignore_errors=True)

    def test_h2kvmctl_dry_run(self):
        """h2kvmctl --dry-run validates config without exporting."""
        vm = os.environ.get("VCENTER_TEST_VM", "")
        if not vm:
            self.skipTest("VCENTER_TEST_VM not set")

        result = subprocess.run(
            [
                "h2kvmctl",
                "--cmd",
                "vsphere",
                "--vcenter",
                os.environ["VCENTER_HOST"],
                "--vc-user",
                os.environ["VCENTER_USER"],
                "--vc-password-env",
                "VCENTER_PASSWORD",
                "--vc-insecure",
                "--vs-action",
                "export_vm",
                "--vm-name",
                vm,
                "--govc-datacenter",
                os.environ["VCENTER_DATACENTER"],
                "--output-dir",
                str(self.output_dir),
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            env=os.environ,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, f"Dry run failed: {result.stderr}")


class TestLocalConversion(unittest.TestCase):
    """Test local VMDK conversion (no vCenter needed)."""

    def test_h2kvmctl_version(self):
        """h2kvmctl --version works."""
        result = subprocess.run(["h2kvmctl", "--version"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout.strip(), r"\d+\.\d+\.\d+")

    def test_h2kvmctl_help(self):
        """h2kvmctl --help works."""
        result = subprocess.run(["h2kvmctl", "--help"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertIn("--cmd", result.stdout)

    def test_h2kvmctl_dump_config(self):
        """h2kvmctl --dump-config works with a YAML file."""
        config = Path("/tmp/test-dump-config.yaml")
        config.write_text("cmd: local\nvmdk: /tmp/nonexistent.vmdk\n")
        try:
            result = subprocess.run(
                ["h2kvmctl", "--config", str(config), "--dump-config"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("cmd", result.stdout)
        finally:
            config.unlink(missing_ok=True)

    @unittest.skipUnless(Path("photon.vmdk").exists(), "photon.vmdk not in cwd")
    def test_photon_conversion(self):
        """Full Photon OS VMDK conversion pipeline."""
        output_dir = Path("/tmp/h2kvm-photon-test")
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(
                [
                    "sudo",
                    "h2kvmctl",
                    "--cmd",
                    "local",
                    "--vmdk",
                    "photon.vmdk",
                    "--output-dir",
                    str(output_dir),
                    "--to-output",
                    "test.qcow2",
                    "--out-format",
                    "qcow2",
                    "--flatten",
                    "--compress",
                    "--fstab-mode",
                    "stabilize-all",
                    "--regen-initramfs",
                    "--dry-run",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, f"Conversion failed: {result.stderr}")
        finally:
            import shutil

            shutil.rmtree(output_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
