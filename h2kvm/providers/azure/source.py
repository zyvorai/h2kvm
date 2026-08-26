# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Azure VM and disk source provider for h2kvm migration."""
# h2kvm/azure/source.py

from __future__ import annotations

import fnmatch
import json
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import cli
from .cleanup import make_tags
from .download import download_with_resume
from .exceptions import AzureCLIError
from .models import (
    AzureConfig,
    AzureDiskRef,
    AzureExportItem,
    AzureFetchReport,
    AzureVMRef,
    AzureVMReport,
    DiskArtifact,
)


def _now_tag() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _uniq6() -> str:
    return os.urandom(3).hex()


def _guest_hint(os_type: str | None) -> str | None:
    if not os_type:
        return None
    t = os_type.lower()
    if t == "windows":
        return "windows"
    if t == "linux":
        return "linux"
    return None


def _safe_vm_folder(root: Path, subscription: str, rg: str, vm: str, run_tag: str) -> Path:
    return root / "azure" / subscription / rg / vm / f"run-{run_tag}"


def _role_filename(vm: str, is_os: bool, lun: int | None) -> str:
    if is_os:
        return f"{vm}-os.vhd"
    if lun is not None:
        return f"{vm}-data-lun{lun}.vhd"
    return f"{vm}-data.vhd"


def _match_any(name: str, patterns: list[str]) -> bool:
    if not patterns:
        return True
    for p in patterns:
        if "*" in p or "?" in p or "[" in p:
            if fnmatch.fnmatchcase(name, p):
                return True
        elif name == p:
            return True
    return False


def _tags_match(vm_tags: dict[str, str], want: dict[str, str]) -> bool:
    if not want:
        return True
    return all(str(vm_tags.get(k)) == str(v) for k, v in want.items())


def _disk_size_gb(disk_json: dict) -> int:
    v = disk_json.get("diskSizeGb")
    if v is not None:
        try:
            return int(v)
        except (TypeError, ValueError):
            pass
    props = disk_json.get("properties") or {}
    v2 = props.get("diskSizeGB") or props.get("diskSizeGb")
    try:
        return int(v2) if v2 is not None else 0
    except (TypeError, ValueError):
        return 0


# maps many independent fields from the Azure VM/disk JSON response onto AzureDiskRef/AzureVMRef
def _resolve_vm_disks(vm_show: dict, *, power_state: str) -> AzureVMRef:  # pylint: disable=too-many-locals
    rg = vm_show.get("resourceGroup") or ""
    loc = vm_show.get("location") or ""
    vid = vm_show.get("id") or ""
    name = vm_show.get("name") or ""
    tags = vm_show.get("tags") or {}

    sp = vm_show.get("storageProfile") or {}
    osd = sp.get("osDisk") or {}
    os_type = osd.get("osType")

    disks: list[AzureDiskRef] = []

    md = osd.get("managedDisk") or {}
    os_disk_id = md.get("id")
    if os_disk_id:
        d = cli.disk_show_by_id(os_disk_id)
        disks.append(
            AzureDiskRef(
                id=os_disk_id,
                name=d.get("name") or osd.get("name") or "osdisk",
                resource_group=rg,
                location=d.get("location") or loc,
                size_gb=_disk_size_gb(d),
                sku=((d.get("sku") or {}).get("name") or ""),
                os_type=d.get("osType") or os_type,
                is_os_disk=True,
                lun=None,
            )
        )

    for dd in sp.get("dataDisks") or []:
        md2 = dd.get("managedDisk") or {}
        did = md2.get("id")
        if not did:
            continue
        d = cli.disk_show_by_id(did)
        disks.append(
            AzureDiskRef(
                id=did,
                name=d.get("name") or dd.get("name") or "datadisk",
                resource_group=rg,
                location=d.get("location") or loc,
                size_gb=_disk_size_gb(d),
                sku=((d.get("sku") or {}).get("name") or ""),
                os_type=d.get("osType"),
                is_os_disk=False,
                lun=dd.get("lun"),
            )
        )

    return AzureVMRef(
        id=vid,
        name=name,
        resource_group=rg,
        location=loc,
        power_state=power_state,
        os_type=os_type,
        tags=tags,
        disks=disks,
    )


class AzureSourceProvider:  # pylint: disable=too-few-public-methods  # single-entrypoint provider (fetch is the whole surface)
    """Azure VM/disk discovery and export provider used by the migration pipeline."""

    @staticmethod
    # discovers, selects, exports (snapshot/download), and reports on VMs/disks in one coordinated pass
    def fetch(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        logger, cfg: AzureConfig
    ) -> tuple[AzureFetchReport, list[DiskArtifact]]:
        """
        Discover Azure VMs/disks matching ``cfg.select``, optionally shut them down,
        export each disk (via snapshot and/or SAS download), and write per-VM and
        run-level JSON reports under ``cfg.output_dir``.

        Returns the run's AzureFetchReport plus the list of downloaded DiskArtifacts
        (empty when ``cfg.select.list_only`` is set).
        """
        run_tag = cfg.export.run_tag or _now_tag()
        rep = AzureFetchReport(run_tag=run_tag)
        rep.selection = {
            "resource_group": cfg.select.resource_group,
            "vm_names": list(cfg.select.vm_names),
            "tags": dict(cfg.select.tags),
            "power_state": cfg.select.power_state,
            "list_only": cfg.select.list_only,
            "allow_all_rgs": cfg.select.allow_all_rgs,
        }

        acct = cli.validate_account(subscription=cfg.subscription, tenant=cfg.tenant)
        rep.subscription = acct.get("id")
        rep.tenant = acct.get("tenantId")
        subscription = rep.subscription or "sub"

        if not cfg.select.resource_group and not cfg.select.allow_all_rgs:
            raise AzureCLIError(
                "Refusing to search whole subscription by default. Set resource_group or allow_all_rgs=true."
            )

        # Early exit for list_only mode to avoid any destructive operations
        if cfg.select.list_only:
            logger.info("List-only mode: discovering VMs without export")

        # Use --show-details to get power state in one batched call (optimization)
        raw_vms = cli.list_vms(cfg.select.resource_group, show_details=True)
        selected: list[AzureVMRef] = []

        for v in raw_vms:
            rg = v.get("resourceGroup") or ""
            name = v.get("name") or ""
            if not name or not rg:
                continue

            if cfg.select.resource_group and rg != cfg.select.resource_group:
                continue
            if not _match_any(name, cfg.select.vm_names):
                continue
            if not _tags_match(v.get("tags") or {}, cfg.select.tags):
                continue

            # Extract power state from list output (batched) instead of per-VM API call
            ps = cli.extract_power_state_from_vm_dict(v)
            if ps is None:
                # Fallback to individual call if not in list output
                logger.debug(f"Power state not in list output for {name}, fetching individually")
                ps = cli.get_vm_power_state(rg, name)

            if cfg.select.power_state and ps != cfg.select.power_state.lower():
                continue

            # Still need vm show for full disk details
            show = cli.get_vm_show(rg, name)
            selected.append(_resolve_vm_disks(show, power_state=ps))

        if not selected:
            raise AzureCLIError("No VMs matched selection criteria.")

        vm_reports: dict[tuple[str, str], AzureVMReport] = {}
        for vm in selected:
            vr = AzureVMReport(
                name=vm.name,
                resource_group=vm.resource_group,
                location=vm.location,
                power_state=vm.power_state,
                os_type=vm.os_type,
                tags=dict(vm.tags),
                disks=[
                    {
                        "name": d.name,
                        "id": d.id,
                        "is_os": d.is_os_disk,
                        "lun": d.lun,
                        "size_gb": d.size_gb,
                        "sku": d.sku,
                        "os_type": d.os_type,
                        "location": d.location,
                    }
                    for d in vm.disks
                ],
            )
            rep.vms.append(vr)
            vm_reports[(vm.resource_group, vm.name)] = vr

        if cfg.select.list_only:
            return rep, []

        # Check available disk space
        total_size_gb = sum(d.size_gb for vm in selected for d in vm.disks)
        try:
            disk_usage = shutil.disk_usage(cfg.output_dir)
            free_gb = disk_usage.free // (1024**3)
            if total_size_gb > free_gb * 0.9:  # Leave 10% margin
                logger.warning(
                    f"Low disk space: need ~{total_size_gb}GB for VHD downloads, "
                    f"have {free_gb}GB free at {cfg.output_dir}\n"
                    f"    Free space or use a larger partition with: --output-dir /path/to/larger/disk\n"
                    f"    Or use --conversion-dir to store intermediates elsewhere."
                )
        except OSError as e:
            logger.debug("Could not check disk space: %s", e)

        # Validate export configuration for running VMs
        if not cfg.export.use_snapshots:
            for vm in selected:
                if vm.power_state == "running" and cfg.shutdown.mode == "none":
                    raise AzureCLIError(
                        f"Cannot export running VM '{vm.name}' without snapshots. "
                        f"Enable use_snapshots or configure shutdown mode (stop/deallocate)."
                    )

        should_shutdown = cfg.shutdown.mode != "none" and (
            cfg.shutdown.force or not cfg.export.use_snapshots
        )
        if should_shutdown:
            for vm in selected:
                cli.vm_stop_or_deallocate(
                    rg=vm.resource_group, name=vm.name, mode=cfg.shutdown.mode, wait=cfg.shutdown.wait
                )

        artifacts: list[DiskArtifact] = []

        # Validate and limit chunk size (1-128 MB)
        chunk_mb = max(1, min(int(cfg.download.chunk_mb), 128))
        if chunk_mb != cfg.download.chunk_mb:
            logger.warning(
                f"Chunk size adjusted from {cfg.download.chunk_mb}MB to {chunk_mb}MB (valid range: 1-128)"
            )

        # pylint: disable-next=too-many-locals,too-many-branches,too-many-statements
        def _export_one(
            vm: AzureVMRef, d: AzureDiskRef
        ) -> tuple[AzureExportItem, DiskArtifact | None, list[str], list[str]]:
            """
            Export a single disk from Azure VM.

            Args:
                vm: Azure VM reference
                d: Azure disk reference

            Returns:
                Tuple of (export_item, disk_artifact, created_resource_ids, deleted_resource_ids)
            """
            created: list[str] = []
            deleted: list[str] = []

            item = AzureExportItem(
                vm_name=vm.name,
                vm_rg=vm.resource_group,
                disk_id=d.id,
                disk_name=d.name,
                is_os=d.is_os_disk,
                lun=d.lun,
            )

            tags = make_tags(enable=cfg.export.tag_resources, run_tag=run_tag, vm_name=vm.name)

            export_target_kind: str | None = None  # "disk"|"snapshot"
            export_id: str | None = None
            sas_url: str | None = None

            vm_root = _safe_vm_folder(cfg.output_dir, subscription, vm.resource_group, vm.name, run_tag)
            disks_dir = vm_root / "disks"
            disks_dir.mkdir(parents=True, exist_ok=True)

            local_vhd = disks_dir / _role_filename(vm.name, d.is_os_disk, d.lun)
            item.local_path = str(local_vhd)
            logger.info("📥 Exporting disk: %s: %s", vm.name, local_vhd.name)

            try:
                if cfg.export.consistency == "best_effort_quiesce" and vm.power_state == "running":
                    cli.best_effort_quiesce_vm(vm.resource_group, vm.name, _guest_hint(vm.os_type))

                stamp = _now_tag()
                uniq = _uniq6()
                snap_name = f"h2kvm-{vm.name}-{d.name}-{stamp}-{uniq}-snap"
                tmp_name = f"h2kvm-{vm.name}-{d.name}-{stamp}-{uniq}-tmpdisk"

                if cfg.export.use_snapshots:
                    snap = cli.snapshot_create(
                        rg=vm.resource_group,
                        name=snap_name,
                        source_disk_id=d.id,
                        location=vm.location,
                        tags=tags,
                    )
                    item.snapshot_id = snap.get("id")
                    if not item.snapshot_id:
                        raise AzureCLIError("Snapshot creation returned no id.")
                    created.append(item.snapshot_id)

                    if cfg.export.stage_disk_from_snapshot:
                        tmpd = cli.disk_create_from_snapshot(
                            rg=vm.resource_group,
                            name=tmp_name,
                            snapshot_id=item.snapshot_id,
                            location=vm.location,
                            tags=tags,
                        )
                        item.temp_disk_id = tmpd.get("id")
                        if not item.temp_disk_id:
                            raise AzureCLIError("Temp disk creation returned no id.")
                        created.append(item.temp_disk_id)

                        export_id = item.temp_disk_id
                        export_target_kind = "disk"
                    else:
                        export_id = item.snapshot_id
                        export_target_kind = "snapshot"
                else:
                    export_id = d.id
                    export_target_kind = "disk"

                if export_id is None or export_target_kind is None:
                    raise AzureCLIError("Internal error: export target not resolved.")

                if export_target_kind == "disk":
                    sas_url = cli.disk_grant_access_by_id(
                        disk_id=export_id, duration_s=cfg.export.sas_duration_s
                    )
                else:
                    sas_url = cli.snapshot_grant_access_by_id(
                        snapshot_id=export_id, duration_s=cfg.export.sas_duration_s
                    )

                item.sas_hash10 = rep.sas_hash10(sas_url)

                chunk = chunk_mb * 1024 * 1024
                res = download_with_resume(
                    url=sas_url,
                    dest=local_vhd,
                    resume=cfg.download.resume,
                    chunk_bytes=chunk,
                    verify_size=cfg.download.verify_size,
                    strict_verify=cfg.download.strict_verify,
                    temp_suffix=cfg.download.temp_suffix,
                    connect_timeout_s=cfg.download.connect_timeout_s,
                    read_timeout_s=cfg.download.read_timeout_s,
                    retries=cfg.download.retries,
                    backoff_base_s=cfg.download.backoff_base_s,
                    backoff_cap_s=cfg.download.backoff_cap_s,
                    progress=None,
                    task_id=None,
                )

                item.bytes_downloaded = res.bytes_written
                item.expected_bytes = res.expected_total

                if (
                    cfg.download.verify_size
                    and not cfg.download.strict_verify
                    and res.expected_total is not None
                ):
                    if res.bytes_written != res.expected_total:
                        item.warnings.append(
                            f"Size mismatch (kept file): expected={res.expected_total} actual={res.bytes_written}"
                        )

                item.ok = True

                art = DiskArtifact(
                    role="os" if d.is_os_disk else "data",
                    lun=d.lun,
                    src=d.id,
                    local_path=Path(local_vhd),
                    format="vhd",
                    guest_hint=_guest_hint(vm.os_type),
                )
                return item, art, created, deleted

            except Exception as e:
                item.errors.append(str(e))
                item.ok = False
                raise

            finally:
                # revoke + cleanup best-effort
                if sas_url and export_id and export_target_kind:
                    try:
                        if export_target_kind == "disk":
                            cli.disk_revoke_access_by_id(disk_id=export_id)
                        else:
                            cli.snapshot_revoke_access_by_id(snapshot_id=export_id)
                    # best-effort cleanup, must not mask the export result
                    except Exception as e:  # pylint: disable=broad-exception-caught
                        item.warnings.append(f"Failed to revoke access: {e}")

                if item.temp_disk_id and not cfg.export.keep_temp_disks:
                    try:
                        cli.resource_delete_by_id(resource_id=item.temp_disk_id)
                        deleted.append(item.temp_disk_id)
                    # best-effort cleanup, must not mask the export result
                    except Exception as e:  # pylint: disable=broad-exception-caught
                        item.warnings.append(f"Failed to delete temp disk: {e}")

                if item.snapshot_id and not cfg.export.keep_snapshots:
                    try:
                        cli.resource_delete_by_id(resource_id=item.snapshot_id)
                        deleted.append(item.snapshot_id)
                    # best-effort cleanup, must not mask the export result
                    except Exception as e:  # pylint: disable=broad-exception-caught
                        item.warnings.append(f"Failed to delete snapshot: {e}")

                status = "ok" if item.ok else "failed"
                logger.info(
                    "📦 %s: %s (%s, %s bytes)",
                    vm.name,
                    local_vhd.name,
                    status,
                    item.bytes_downloaded or 0,
                )

        jobs: list[tuple[AzureVMRef, AzureDiskRef]] = []
        for vm in selected:
            for d in vm.disks:
                if cfg.export.disks == "os" and not d.is_os_disk:
                    continue
                if cfg.export.disks == "data" and d.is_os_disk:
                    continue
                jobs.append((vm, d))

        # Limit max workers by configured parallel, hard cap of 16, and actual job count
        max_workers = min(max(1, int(cfg.download.parallel)), 16, len(jobs))

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(_export_one, vm, d): (vm, d) for (vm, d) in jobs}
            for f in as_completed(futs):
                vm, d = futs[f]
                vr = vm_reports[(vm.resource_group, vm.name)]
                try:
                    item, art, created, deleted = f.result()
                    vr.exports.append(item)
                    rep.created_resource_ids.extend(created)
                    rep.deleted_resource_ids.extend(deleted)
                    if art is not None:
                        artifacts.append(art)
                # one disk's export failure must not abort collecting the rest of the batch
                except Exception as e:  # pylint: disable=broad-exception-caught
                    vr.errors.append(f"Disk export failed for {d.name}: {e}")

        for vr in rep.vms:
            vr.exports.sort(key=lambda it: (0 if it.is_os else 1, it.lun if it.lun is not None else 9999))

        for vr in rep.vms:
            vm_root = _safe_vm_folder(cfg.output_dir, subscription, vr.resource_group, vr.name, run_tag)
            rp = vm_root / "azure-report.json"
            rp.parent.mkdir(parents=True, exist_ok=True)
            rp.write_text(
                json.dumps(vr.to_jsonable(), indent=2, sort_keys=True, default=str), encoding="utf-8"
            )

        summary = cfg.output_dir / "azure" / subscription / f"azure-run-{run_tag}.json"
        summary.parent.mkdir(parents=True, exist_ok=True)
        summary.write_text(
            json.dumps(rep.to_jsonable(), indent=2, sort_keys=True, default=str), encoding="utf-8"
        )

        return rep, artifacts
