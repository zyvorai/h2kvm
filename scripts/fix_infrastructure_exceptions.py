#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Fix exception handling in infrastructure code.
"""

from pathlib import Path


def fix_snapshot_manager():
    """Fix exceptions in snapshot_manager.py"""
    file_path = Path("hyper2kvm/infrastructure/rollback/snapshot_manager.py")
    content = file_path.read_text()

    # Fix source image not found
    content = content.replace(
        '            raise RuntimeError(f"Source image not found: {source_path}")',
        """            raise DiskConversionError(
                code=66,
                msg=f"Cannot create snapshot: source image not found at {source_path}"
            ).with_context(
                solutions=[
                    "Verify the disk image path is correct",
                    "Ensure the file exists before creating snapshot"
                ],
                source_path=str(source_path)
            )""",
    )

    # Fix NotImplementedError for unsupported snapshot types
    content = content.replace(
        '            raise NotImplementedError(f"Snapshot type {snapshot_type.value} not yet supported")',
        """            raise InfrastructureError(
                code=38,
                msg=f"Snapshot type '{snapshot_type.value}' is not yet supported"
            ).with_context(
                solutions=[
                    "Use snapshot_type=SnapshotType.QCOW2 for QCOW2 snapshots",
                    "Use snapshot_type=SnapshotType.FULL for full disk copies"
                ],
                requested_type=snapshot_type.value,
                supported_types=["qcow2", "full"]
            )""",
    )

    # Fix QCOW2 snapshot creation failure
    content = content.replace(
        '            raise RuntimeError(f"Failed to create QCOW2 snapshot: {e.stderr}")',
        """            raise DiskConversionError(
                code=73,
                msg=f"Failed to create QCOW2 snapshot for {source_path.name}"
            ).with_context(
                solutions=[
                    "Ensure qemu-img is installed: apt install qemu-utils",
                    "Verify sufficient disk space in snapshot directory",
                    "Check source image is a valid QCOW2 file"
                ],
                source_path=str(source_path),
                snapshot_id=snapshot_id,
                error=e.stderr
            ) from e""",
    )

    # Fix full snapshot creation failure
    content = content.replace(
        '            raise RuntimeError(f"Failed to create full snapshot: {e}")',
        """            raise DiskConversionError(
                code=73,
                msg=f"Failed to create full snapshot copy of {source_path.name}"
            ).with_context(
                solutions=[
                    "Verify sufficient disk space in snapshot directory",
                    "Check file permissions allow reading source and writing snapshot",
                    "Ensure snapshot directory is writable"
                ],
                source_path=str(source_path),
                snapshot_dir=str(snapshot_dir),
                snapshot_id=snapshot_id
            ) from e""",
    )

    # Fix snapshot not found errors
    content = content.replace(
        '            raise RuntimeError(f"Snapshot not found: {snapshot_id}")',
        """            raise InfrastructureError(
                code=2,
                msg=f"Snapshot '{snapshot_id}' not found"
            ).with_context(
                solutions=[
                    "List available snapshots with list_snapshots()",
                    "Verify the snapshot ID is correct",
                    f"Check snapshot directory: {self.snapshot_dir}"
                ],
                snapshot_id=snapshot_id
            )""",
    )

    # Fix restore not supported
    content = content.replace(
        '            raise NotImplementedError(f"Restore for {snapshot.snapshot_type.value} not supported")',
        """            raise InfrastructureError(
                code=38,
                msg=f"Snapshot restore for type '{snapshot.snapshot_type.value}' is not yet implemented"
            ).with_context(
                solutions=[
                    "Use QCOW2 or FULL snapshot types which support restore",
                    "Manually restore the snapshot file if needed"
                ],
                snapshot_type=snapshot.snapshot_type.value,
                snapshot_id=snapshot.snapshot_id
            )""",
    )

    file_path.write_text(content)
    print(f"✓ Fixed {file_path}")


def main():
    fix_snapshot_manager()
    print("\n✓ Infrastructure exception handling improved")


if __name__ == "__main__":
    main()
